"""Geometria e conferências para preencher o volante com PyAutoGUI.

Este módulo não move o mouse ao ser importado. A calibração usa posições medidas
na tela do próprio usuário, nunca coordenadas copiadas de uma captura de tela.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable


class CoordinateAutomationError(RuntimeError):
    """Uma etapa não pôde ser confirmada; não repetir o clique cegamente."""


Point = tuple[int, int]


@dataclass(frozen=True)
class GridCalibration:
    columns: int
    first: Point
    last_first: Point
    first_last: Point
    screen_size: Point
    screen_origin: Point = (0, 0)
    last_last: Point | None = None

    @property
    def rows(self) -> int:
        return math.ceil(60 / self.columns)

    @property
    def first_number_last_row(self) -> int:
        return (self.rows - 1) * self.columns + 1

    @property
    def numbers_last_row(self) -> int:
        return 60 - (self.rows - 1) * self.columns


def calibrate_grid(
    first: Point,
    last_first: Point,
    first_last: Point,
    columns: int,
    screen_size: Point,
    *,
    screen_origin: Point = (0, 0),
    last_last: Point | None = None,
) -> GridCalibration:
    """Interpola os centros usando as extremidades das primeiras e últimas linhas."""
    if type(columns) is not int or not 10 <= columns <= 30:
        raise ValueError("Informe entre 10 e 30 dezenas na primeira linha.")
    if (
        not isinstance(screen_size, tuple)
        or len(screen_size) != 2
        or any(type(value) is not int or value <= 0 for value in screen_size)
    ):
        raise ValueError("Tamanho da tela inválido.")
    if (
        not isinstance(screen_origin, tuple)
        or len(screen_origin) != 2
        or any(type(value) is not int for value in screen_origin)
    ):
        raise ValueError("Origem da tela inválida.")
    left, top = screen_origin
    right, bottom = left + screen_size[0], top + screen_size[1]
    for point in (first, last_first, first_last, last_last):
        if point is None:
            continue
        if (
            not isinstance(point, tuple)
            or len(point) != 2
            or any(type(value) is not int for value in point)
            or not (left <= point[0] < right and top <= point[1] < bottom)
        ):
            raise ValueError("Um centro foi marcado fora da área dos monitores.")
    dx = (last_first[0] - first[0]) / (columns - 1)
    dy = (first_last[1] - first[1]) / (math.ceil(60 / columns) - 1)
    if not 20 <= dx <= 120 or not 25 <= dy <= 160:
        raise ValueError("Espaçamento das dezenas incompatível com um volante.")
    if abs(last_first[1] - first[1]) > min(12, dy * 0.15):
        raise ValueError("01 e o último número da primeira linha não estão alinhados.")
    if abs(first_last[0] - first[0]) > min(25, dx * 0.45):
        raise ValueError("O início da última linha não está alinhado com 01.")
    if last_last is not None:
        last_row_count = 60 - (math.ceil(60 / columns) - 1) * columns
        bottom_dx = (last_last[0] - first_last[0]) / (last_row_count - 1)
        expected_last_x = first_last[0] + (last_row_count - 1) * dx
        if (
            not 20 <= bottom_dx <= 120
            or abs(bottom_dx - dx) > dx * 0.2
            or abs(last_last[0] - expected_last_x) > max(15, dx * 0.3)
            or abs(last_last[1] - first_last[1]) > 12
        ):
            raise ValueError("A posição de 60 não combina com a grade; confira 45 e 60.")
    calibration = GridCalibration(columns, first, last_first, first_last,
                                  screen_size, screen_origin, last_last)
    validate_layout(calibration, screen_size, screen_origin)
    return calibration


def validate_layout(
    calibration: GridCalibration, screen_size: Point, screen_origin: Point = (0, 0)
) -> None:
    if tuple(screen_size) != calibration.screen_size:
        raise ValueError("A resolução mudou desde a calibração.")
    if tuple(screen_origin) != calibration.screen_origin:
        raise ValueError("A posição dos monitores mudou desde a calibração.")
    left, top = screen_origin
    for number in range(1, 61):
        x, y = number_center(calibration, number)
        if not (left + 20 <= x < left + screen_size[0] - 20
                and top + 20 <= y < top + screen_size[1] - 20):
            raise ValueError("Uma dezena calculada ficou perto demais da borda da tela.")


def number_center(calibration: GridCalibration, number: int) -> Point:
    if type(number) is not int or not 1 <= number <= 60:
        raise ValueError("Dezena inválida: use números de 01 a 60.")
    row, column = divmod(number - 1, calibration.columns)
    dx = (calibration.last_first[0] - calibration.first[0]) / (calibration.columns - 1)
    col_dy = (calibration.last_first[1] - calibration.first[1]) / (calibration.columns - 1)
    row_fraction = row / (calibration.rows - 1)
    row_x = calibration.first[0] + row_fraction * (calibration.first_last[0] - calibration.first[0])
    row_y = calibration.first[1] + row_fraction * (calibration.first_last[1] - calibration.first[1])
    if calibration.last_last is not None:
        bottom_dx = (calibration.last_last[0] - calibration.first_last[0]) / (
            calibration.numbers_last_row - 1
        )
        bottom_col_dy = (calibration.last_last[1] - calibration.first_last[1]) / (
            calibration.numbers_last_row - 1
        )
        dx += row_fraction * (bottom_dx - dx)
        col_dy += row_fraction * (bottom_col_dy - col_dy)
    return (
        round(row_x + column * dx),
        round(row_y + column * col_dy),
    )


def _is_selected_color(pixel: tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    return g >= 90 and g >= r * 1.3 and g >= b * 1.2 and r < 150


def selected_numbers(image, calibration: GridCalibration) -> tuple[int, ...]:
    """Lê o verde do interior dos 60 círculos em uma captura da tela."""
    validate_layout(calibration, image.size, getattr(image, "screen_origin", (0, 0)))
    selected: list[int] = []
    dx = (calibration.last_first[0] - calibration.first[0]) / (calibration.columns - 1)
    # O algarismo pode cobrir completamente uma amostra pequena (como ocorreu
    # com o 26). Leia pontos distribuídos ao redor dele, ainda dentro do círculo.
    radius = max(10, min(16, round(dx * 0.3)))
    short = round(radius * 0.55)
    long = round(radius * 0.83)
    offsets = (
        (0, -radius), (long, -short), (radius, 0), (long, short),
        (0, radius), (-long, short), (-radius, 0), (-long, -short),
        (short, -long), (short, long), (-short, long), (-short, -long),
    )
    for number in range(1, 61):
        x, y = number_center(calibration, number)
        green = sum(
            _is_selected_color(image.getpixel((x + sx, y + sy)))
            for sx, sy in offsets
        )
        if green >= 4:
            selected.append(number)
    return tuple(selected)


def layout_signature(image, calibration: GridCalibration) -> tuple[object, ...]:
    """Recorta alguns algarismos para detectar deslocamento ou quebra de linha."""
    validate_layout(calibration, image.size, getattr(image, "screen_origin", (0, 0)))
    anchors = (1, calibration.columns, calibration.columns + 1,
               calibration.first_number_last_row, 60)
    return tuple(
        image.crop((x - 13, y - 13, x + 14, y + 14)).convert("RGB")
        for number in anchors
        for x, y in (number_center(calibration, number),)
    )


def layout_matches(image, calibration: GridCalibration, signature: tuple[object, ...]) -> bool:
    """Aceita pequenas diferenças de renderização, mas não outro desenho do grid."""
    current = layout_signature(image, calibration)
    if len(current) != len(signature):
        return False
    for old, new in zip(signature, current):
        if old.size != new.size:
            return False
        # Os dígitos precisam continuar no mesmo lugar. Evita reutilizar uma
        # calibração de 22 colunas depois que o painel mudou o grid para 17.
        changed = sum(
            max(abs(a - b) for a, b in zip(p, q)) > 45
            for p, q in zip(old.getdata(), new.getdata())
        )
        if changed > old.width * old.height * 0.12:
            return False
    return True


def recent_tickets(page_text: str) -> list[tuple[int, ...]]:
    """Extrai as seis dezenas dos cartões 'Números selecionados' copiados da página."""
    results: list[tuple[int, ...]] = []
    pattern = re.compile(
        r"N[uú]meros\s+selecionados\s*:?\s*"
        r"((?:\b\d{2}\b\s*){6})(?=\bConcurso\b|\bValor\b|\n|$)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(page_text):
        numbers = tuple(sorted(int(value) for value in re.findall(r"\b\d{2}\b", match.group(1))))
        if len(numbers) == 6 and len(set(numbers)) == 6 and all(1 <= n <= 60 for n in numbers):
            results.append(numbers)
    return results


@dataclass(frozen=True)
class RecentCard:
    numbers: tuple[int, ...]
    contest: str
    price: Decimal


def recent_cards(page_text: str) -> list[RecentCard]:
    """Lê dezenas, concurso e preço dos cartões copiados do painel recente."""
    label = re.compile(r"N[uú]meros\s+selecionados", re.I)
    matches = list(label.finditer(page_text))
    cards: list[RecentCard] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_text)
        section = page_text[match.end():end][:250]
        numbers_match = re.match(r"\s*:?\s*((?:\b\d{2}\b\s*){6})", section)
        if not numbers_match:
            continue
        numbers = tuple(sorted(int(value) for value in re.findall(r"\b\d{2}\b", numbers_match.group(1))))
        if len(numbers) != 6 or len(set(numbers)) != 6 or not all(1 <= n <= 60 for n in numbers):
            continue
        contest_match = re.search(r"Concurso\s*:?\s*(\d{4,5})\b", section[numbers_match.end():], re.I)
        price_match = re.search(r"Valor\s*:?\s*R\$\s*([\d.]+,\d{2})", section[numbers_match.end():], re.I)
        if contest_match and price_match:
            cards.append(
                RecentCard(
                    numbers,
                    contest_match.group(1),
                    Decimal(price_match.group(1).replace(".", "").replace(",", ".")),
                )
            )
    return cards


def page_total(page_text: str) -> Decimal | None:
    match = re.search(r"Total\s+da\s+aposta\s*:\s*R\$\s*([\d.]+,\d{2})", page_text, re.I)
    return Decimal(match.group(1).replace(".", "").replace(",", ".")) if match else None


def current_contest_from_page(page_text: str) -> str | None:
    """Lê concurso no volante, desconsiderando cartões de apostas recentes."""
    prefix = re.split(r"Apostas\s+recentes", page_text, maxsplit=1, flags=re.I)[0]
    matches = set(
        re.findall(r"\bConcurso\s*(?:n[º°.]\s*)?:?\s*(\d{4,5})\b", prefix, re.I)
    )
    return next(iter(matches)) if len(matches) == 1 else None


def page_controls_ok(page_text: str) -> bool:
    """Confere que o navegador está no volante simples, com preço e opções esperadas."""
    return all(
        re.search(pattern, page_text, re.I)
        for pattern in (
            r"Preencha\s+sua\s+aposta",
            r"Quantidade\s+de\s+n[uú]meros\s+da\s+aposta[^0-9]{0,20}6\b",
            r"Teimosinhas[^0-9]{0,20}0\b",
            r"Valor\s+da\s+Aposta\s*:\s*R\$\s*6,00\b",
        )
    )


def fill_and_submit(
    gui,
    calibration: GridCalibration,
    ticket: tuple[int, ...],
    clear_point: Point,
    add_point: Point | Callable[[], Point],
    verify_callback,
    *,
    before_click=None,
    click_delay: float = 1.0,
) -> None:
    """Confere cada clique antes de tocar a próxima dezena ou Adicionar."""
    if (
        len(ticket) != 6
        or len(set(ticket)) != 6
        or any(type(n) is not int or not 1 <= n <= 60 for n in ticket)
    ):
        raise CoordinateAutomationError("O jogo precisa ter seis dezenas distintas de 01 a 60.")
    if not 0.7 <= click_delay <= 5:
        raise CoordinateAutomationError("A pausa entre cliques deve ficar entre 0,7 e 5 segundos.")
    validate_layout(calibration, tuple(gui.size()), getattr(gui, "screen_origin", (0, 0)))
    left, top = calibration.screen_origin
    initial_points = (clear_point,) if callable(add_point) else (clear_point, add_point)
    for point in initial_points:
        if not (left <= point[0] < left + calibration.screen_size[0]
                and top <= point[1] < top + calibration.screen_size[1]):
            raise CoordinateAutomationError("Um botão foi marcado fora da tela.")

    if before_click is not None:
        before_click("clear", None, clear_point)
    print(f"Limpar Volante: {clear_point}", flush=True)
    gui.click(*clear_point)
    time.sleep(click_delay)
    if not verify_callback("cleared", ticket):
        raise CoordinateAutomationError("O volante não ficou limpo; aposta não incluída.")
    clicked: list[int] = []
    for number in ticket:
        point = number_center(calibration, number)
        if before_click is not None:
            before_click("number", number, point)
        print(f"Dezena {number:02d}: {point}", flush=True)
        gui.click(*point)
        time.sleep(click_delay)
        clicked.append(number)
        if not verify_callback("number", tuple(sorted(clicked))):
            raise CoordinateAutomationError(
                f"A dezena {number:02d} não foi confirmada; interrompido antes do próximo clique."
            )
    if not verify_callback("selected", ticket):
        raise CoordinateAutomationError("As seis dezenas não foram confirmadas; aposta não incluída.")
    resolved_add_point = add_point() if callable(add_point) else add_point
    if (
        not isinstance(resolved_add_point, tuple)
        or len(resolved_add_point) != 2
        or any(type(value) is not int for value in resolved_add_point)
        or not (left <= resolved_add_point[0] < left + calibration.screen_size[0]
                and top <= resolved_add_point[1] < top + calibration.screen_size[1])
    ):
        raise CoordinateAutomationError("O botão Colocar no Carrinho foi marcado fora da tela.")
    if before_click is not None:
        before_click("add", None, resolved_add_point)
    print(f"Colocar no Carrinho: {resolved_add_point}", flush=True)
    gui.click(*resolved_add_point)
    time.sleep(click_delay)
    if not verify_callback("added", ticket):
        raise CoordinateAutomationError(
            "O clique em Colocar no Carrinho ocorreu, mas o volante não voltou "
            "ao estado vazio. Confira o carrinho antes de tentar novamente."
        )

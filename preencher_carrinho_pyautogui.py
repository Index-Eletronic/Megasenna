"""Preenche a carteira no navegador já aberto usando cliques do PyAutoGUI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from megasena.cart_automation import validate_tickets
from megasena.pyautogui_cart import (
    CoordinateAutomationError,
    calibrate_grid,
    fill_and_submit,
    layout_matches,
    layout_signature,
    number_center,
    selected_numbers,
)


ROOT = Path(__file__).resolve().parent
TICKETS_FILE = ROOT / "assets" / "carteira-25-2026-09-25.json"
PROGRESS_FILE = ROOT / "data" / "progresso-carrinho-pyautogui.json"


def _format_ticket(ticket: tuple[int, ...]) -> str:
    return " ".join(f"{value:02d}" for value in ticket)


def _portfolio_id(tickets: list[tuple[int, ...]]) -> str:
    return hashlib.sha256(json.dumps(tickets).encode("ascii")).hexdigest()


def _new_progress(tickets: list[tuple[int, ...]]) -> dict:
    return {"carteira": _portfolio_id(tickets), "confirmados": [], "pendente": None, "concurso": None}


def _load_progress(tickets: list[tuple[int, ...]], *, new_cart: bool) -> dict:
    if new_cart or not PROGRESS_FILE.exists():
        return _new_progress(tickets)
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CoordinateAutomationError("Arquivo de progresso ilegível. Confira o carrinho.") from exc
    if data.get("carteira") != _portfolio_id(tickets):
        raise CoordinateAutomationError(
            "O progresso pertence a outra carteira. Esvazie o carrinho e use --novo-carrinho."
        )
    confirmed = data.get("confirmados")
    pending = data.get("pendente")
    if (
        not isinstance(confirmed, list)
        or any(type(value) is not int for value in confirmed)
        or confirmed != list(range(1, len(confirmed) + 1))
        or len(confirmed) > 25
        or (pending is not None and pending != len(confirmed) + 1)
    ):
        raise CoordinateAutomationError("Progresso inconsistente. Confira o carrinho.")
    if pending is not None:
        raise CoordinateAutomationError(
            f"O clique do jogo {pending:02d} ficou sem confirmação. Confira o carrinho; "
            "se necessário, esvazie-o e reinicie com --novo-carrinho."
        )
    if data.get("concurso") is not None and not str(data["concurso"]).isdigit():
        raise CoordinateAutomationError("Concurso do progresso ilegível.")
    return data


def _save_progress(data: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = PROGRESS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, PROGRESS_FILE)


def _capture_point(gui, label: str) -> tuple[int, int]:
    gui.alert(
        f"Clique OK e mova o mouse para o CENTRO de {label}.\n"
        "Não clique no site. A posição será capturada em 4 segundos.",
        title="Calibração do volante",
    )
    time.sleep(4)
    point = tuple(gui.position())
    print(f"{label}: {point}", flush=True)
    return point


def _calibrate(gui):
    while True:
        answer = gui.prompt(
            "Quantas dezenas aparecem na PRIMEIRA linha?\n"
            "Nas imagens enviadas são 22; em tela menor podem ser 17.",
            title="Calibração do volante",
            default="22",
        )
        if answer is None:
            raise CoordinateAutomationError("Calibração cancelada.")
        try:
            columns = int(answer.strip())
            if not 10 <= columns <= 30:
                raise ValueError
        except ValueError:
            gui.alert("Informe um número entre 10 e 30.")
            continue
        rows = (59 // columns) + 1
        first_last_number = (rows - 1) * columns + 1
        first = _capture_point(gui, "01")
        last_first = _capture_point(gui, f"{columns:02d} (última dezena da primeira linha)")
        first_last = _capture_point(gui, f"{first_last_number:02d} (primeira dezena da última linha)")
        last_last = _capture_point(gui, "60 (última dezena da última linha)")
        clear_point = _capture_point(gui, "Limpar Volante")
        screen_size = tuple(gui.size())
        screen_origin = getattr(gui, "screen_origin", (0, 0))
        screenshot = gui.screenshot()
        if screenshot.size != screen_size or getattr(screenshot, "screen_origin", (0, 0)) != screen_origin:
            raise CoordinateAutomationError(
                "Captura e mouse usam resoluções diferentes. Verifique a escala e a posição dos monitores."
            )
        try:
            calibration = calibrate_grid(
                first, last_first, first_last, columns, screen_size,
                screen_origin=screen_origin, last_last=last_last,
            )
        except ValueError as exc:
            gui.alert(f"Posições incompatíveis: {exc}\nVamos calibrar novamente.")
            continue
        if not (
            all(screen_origin[0] <= point[0] < screen_origin[0] + screen_size[0]
                    and screen_origin[1] <= point[1] < screen_origin[1] + screen_size[1]
                    for point in (clear_point,))
            and first_last[1] + 30 < clear_point[1]
        ):
            gui.alert(
                "Limpar Volante parece fora da região esperada. Vamos calibrar novamente."
            )
            continue
        for number in (1, columns, columns + 1, first_last_number, 60):
            x, y = number_center(calibration, number)
            print(f"Prévia {number:02d} (calculada): ({x}, {y})", flush=True)
            gui.moveTo(x, y, duration=0.25)
            time.sleep(0.45)
        print(f"Prévia Limpar Volante: {clear_point}", flush=True)
        gui.moveTo(*clear_point, duration=0.25)
        time.sleep(1.2)
        choice = gui.confirm(
            "Observe a prévia no volante. O mouse passou pelo centro das dezenas?\n"
            "Também passou por Limpar Volante?\n"
            "Colocar no Carrinho será calibrado quando as seis dezenas estiverem marcadas.",
            title="Revisar calibração",
            buttons=["Usar", "Recalibrar", "Cancelar"],
        )
        if choice == "Usar":
            return calibration, clear_point
        if choice != "Recalibrar":
            raise CoordinateAutomationError("Calibração cancelada.")


def _capture_add_point(gui, calibration, clear_point):
    """Mede o botão ativo com as seis dezenas já selecionadas."""
    left, top = calibration.screen_origin
    width, height = calibration.screen_size
    while True:
        point = _capture_point(gui, "Colocar no Carrinho (botão ativo, após selecionar as seis dezenas)")
        if not (
            left <= point[0] < left + width
            and top <= point[1] < top + height
            and point[1] > clear_point[1] + 60
            and point[0] < calibration.last_first[0] + 110
        ):
            gui.alert("O ponto não parece ser Colocar no Carrinho. Vamos capturá-lo novamente.")
            continue
        print(f"Prévia Colocar no Carrinho (ativo): {point}", flush=True)
        gui.moveTo(*point, duration=0.25)
        time.sleep(0.8)
        choice = gui.confirm(
            "O mouse está no centro do botão ativo Colocar no Carrinho?\n"
            "Não use o botão Ir para pagamento.",
            title="Revisar botão do carrinho",
            buttons=["Usar", "Recalibrar", "Cancelar"],
        )
        if choice == "Usar":
            if hasattr(gui, "activate_window_at"):
                gui.activate_window_at(*number_center(calibration, 1))
            return point
        if choice != "Recalibrar":
            raise CoordinateAutomationError("Calibração do botão cancelada. Nenhum clique em Adicionar foi feito.")


def _wait_for_selection(gui, calibration, expected: tuple[int, ...]) -> bool:
    deadline = time.monotonic() + 4
    actual = ()
    while time.monotonic() < deadline:
        actual = selected_numbers(gui.screenshot(), calibration)
        if actual == expected:
            return True
        time.sleep(0.2)
    print(f"Seleção vista: {_format_ticket(actual)}; esperada: {_format_ticket(expected)}")
    return False


def _prepare_grid(gui, calibration, clear_point):
    gui.click(*clear_point)
    if not _wait_for_selection(gui, calibration, ()):
        raise CoordinateAutomationError("Não foi possível limpar o volante após calibrar.")
    return layout_signature(gui.screenshot(), calibration)


def _run(gui, tickets: list[tuple[int, ...]], *, new_cart: bool, through_game: int) -> None:
    progress = _load_progress(tickets, new_cart=new_cart)
    if len(progress["confirmados"]) == 25 and not new_cart:
        print("Os 25 jogos já foram enviados nesta execução. Use --novo-carrinho apenas após esvaziar o site.")
        return
    if len(progress["confirmados"]) >= through_game:
        print(f"Até o jogo {through_game:02d} já foi enviado nesta execução. Nenhum clique necessário.")
        return

    print("Deixe o volante da Mega-Sena visível em um monitor, sem rolar a página.")
    print("Para interromper: mova o mouse para o canto superior esquerdo do monitor principal.")
    gui.screenshot()  # Confere a captura de todos os monitores antes de pedir os pontos.
    calibration, clear_point = _calibrate(gui)
    add_point = None
    if hasattr(gui, "activate_window_at"):
        gui.activate_window_at(*number_center(calibration, 1))
    signature = _prepare_grid(gui, calibration, clear_point)

    for index in range(len(progress["confirmados"]) + 1, through_game + 1):
        ticket = tickets[index - 1]
        print(f"Iniciando jogo {index:02d}/25: {_format_ticket(ticket)}", flush=True)
        current_image = gui.screenshot()
        if not layout_matches(current_image, calibration, signature):
            print("O desenho do volante mudou. Vou pedir uma nova calibração antes do próximo clique.")
            calibration, clear_point = _calibrate(gui)
            add_point = None
            if hasattr(gui, "activate_window_at"):
                gui.activate_window_at(*number_center(calibration, 1))
            signature = _prepare_grid(gui, calibration, clear_point)

        def before_click(phase: str, number: int | None, point: tuple[int, int]) -> None:
            if phase == "add":
                if selected_numbers(gui.screenshot(), calibration) != ticket:
                    raise CoordinateAutomationError(
                        "As dezenas mudaram antes de Colocar no Carrinho. Nenhuma inclusão feita."
                    )
                # A partir daqui o clique pode acontecer; uma falha posterior
                # precisa impedir a repetição automática deste jogo.
                progress["pendente"] = index
                _save_progress(progress)

        def resolve_add_point():
            nonlocal add_point
            if add_point is None:
                add_point = _capture_add_point(gui, calibration, clear_point)
            return add_point

        def verify(phase: str, current_ticket: tuple[int, ...]) -> bool:
            if phase == "cleared":
                return _wait_for_selection(gui, calibration, ())
            if phase == "number":
                # O site pode aplicar outra cor ao círculo sob o cursor (:hover).
                # Afastar o mouse evita confundir esse efeito com falta de seleção.
                gui.moveTo(*clear_point, duration=0.2)
                return _wait_for_selection(gui, calibration, current_ticket)
            if phase == "selected":
                return _wait_for_selection(gui, calibration, current_ticket)
            if phase == "added":
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if selected_numbers(gui.screenshot(), calibration) == ():
                        progress["confirmados"].append(index)
                        progress["pendente"] = None
                        _save_progress(progress)
                        return True
                    time.sleep(0.35)
                return False
            raise AssertionError(f"Fase desconhecida: {phase}")

        fill_and_submit(
            gui, calibration, ticket, clear_point, resolve_add_point, verify,
            before_click=before_click, click_delay=1.3,
        )
        print(f"{index:02d}/25 enviado: {_format_ticket(ticket)}", flush=True)

    if len(progress["confirmados"]) == 25:
        print("Os 25 jogos foram enviados. Confira os 25 itens e o valor no carrinho do site.")
    else:
        print(
            f"Execução de teste encerrada após o jogo {through_game:02d}. "
            "Confira o carrinho; execute de novo para continuar."
        )
    print("Nenhum comando de pagamento foi executado.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preenche os 25 jogos pelo mouse na tela atual.")
    parser.add_argument("--conferir", action="store_true", help="Só mostra os jogos; não move o mouse.")
    parser.add_argument(
        "--novo-carrinho", action="store_true",
        help="Recomeça do jogo 01; esvazie o carrinho no site antes.",
    )
    parser.add_argument(
        "--ate-jogo", type=int, default=25, metavar="N",
        help="Para após enviar o jogo N (ex.: --ate-jogo 1 para testar).",
    )
    args = parser.parse_args()
    if not 1 <= args.ate_jogo <= 25:
        parser.error("--ate-jogo precisa ser um número de 1 a 25")
    try:
        tickets = validate_tickets(TICKETS_FILE)
    except ValueError as exc:
        print(f"Carteira inválida: {exc}", file=sys.stderr)
        return 2
    for index, ticket in enumerate(tickets, 1):
        print(f"{index:02d}. {_format_ticket(ticket)}")
    if args.conferir:
        return 0
    try:
        from megasena.virtual_desktop import VirtualDesktopGUI, enable_per_monitor_dpi

        enable_per_monitor_dpi()
        import pyautogui
    except ImportError:
        print(
            "Instale no interpretador deste projeto: python -m pip install -r requirements-pyautogui.txt",
            file=sys.stderr,
        )
        return 2
    except CoordinateAutomationError as exc:
        print(f"Não foi possível preparar os monitores: {exc}", file=sys.stderr)
        return 1
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.18
    try:
        gui = VirtualDesktopGUI(pyautogui)
    except CoordinateAutomationError as exc:
        print(f"Não foi possível preparar a captura: {exc}", file=sys.stderr)
        print("Nenhum clique foi feito no site.", file=sys.stderr)
        return 1
    try:
        _run(
            gui, tickets,
            new_cart=args.novo_carrinho, through_game=args.ate_jogo,
        )
    except (CoordinateAutomationError, ValueError, KeyboardInterrupt, pyautogui.FailSafeException) as exc:
        print(f"\nExecução interrompida: {exc}", file=sys.stderr)
        if gui.click_count == 0:
            print("Nenhum clique foi feito no site.", file=sys.stderr)
        else:
            print(
                "Confira o carrinho antes de executar novamente. Um jogo clicado sem "
                "confirmação nunca é repetido automaticamente.",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

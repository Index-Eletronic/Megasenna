"""Preenchimento conferido de apostas simples no portal Loterias CAIXA."""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse


class CartAutomationError(RuntimeError):
    """O site não permitiu confirmar uma etapa com segurança."""


def validate_tickets(path: str | Path) -> list[tuple[int, ...]]:
    """Carrega a carteira de 25 jogos distintos e valida cada dezena."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Não foi possível ler a carteira: {exc}") from exc

    if not isinstance(document, dict) or not isinstance(document.get("jogos"), list):
        raise ValueError("A carteira precisa conter uma lista 'jogos'.")
    raw_tickets = document["jogos"]
    if len(raw_tickets) != 25:
        raise ValueError(f"Esperados 25 jogos; encontrados {len(raw_tickets)}.")

    tickets: list[tuple[int, ...]] = []
    for index, raw in enumerate(raw_tickets, 1):
        if not isinstance(raw, list) or len(raw) != 6:
            raise ValueError(f"Jogo {index:02d}: são necessárias seis dezenas.")
        if any(type(value) is not int or not 1 <= value <= 60 for value in raw):
            raise ValueError(f"Jogo {index:02d}: use inteiros de 1 a 60.")
        if len(set(raw)) != 6:
            raise ValueError(f"Jogo {index:02d}: há dezenas repetidas.")
        tickets.append(tuple(sorted(raw)))

    if len(set(tickets)) != 25:
        raise ValueError("A carteira contém jogos repetidos.")
    return tickets


GRID = "ul.escolhe-numero.mega-sena"
RECENT_CARDS = ".volante.mega-sena"
RECENT_NUMBERS = ".numero-volante-aposta-incluida span.margemVolante"


def selected_numbers(page) -> tuple[int, ...]:
    """Lê a seleção real do volante, conferindo seus 60 controles."""
    grid = page.locator(GRID)
    if grid.count() != 1:
        raise CartAutomationError("Volante da Mega-Sena não encontrado ou ambíguo.")
    links = grid.locator("a[id^='n']")
    ids = links.evaluate_all("elements => elements.map(element => element.id)")
    expected_ids = {f"n{number:02d}" for number in range(1, 61)}
    if len(ids) != 60 or set(ids) != expected_ids:
        raise CartAutomationError("O volante não contém as 60 dezenas esperadas.")
    selected_ids = grid.locator("a.selected").evaluate_all(
        "elements => elements.map(element => element.id)"
    )
    if any(value not in expected_ids for value in selected_ids):
        raise CartAutomationError("Há uma seleção desconhecida no volante.")
    return tuple(sorted(int(value[1:]) for value in selected_ids))


def _check_ticket(ticket: tuple[int, ...]) -> tuple[int, ...]:
    if len(ticket) != 6 or len(set(ticket)) != 6 or any(
        type(value) is not int or not 1 <= value <= 60 for value in ticket
    ):
        raise CartAutomationError("Jogo inválido: use seis dezenas distintas de 01 a 60.")
    return tuple(sorted(ticket))


def _wait_for_selection(page, expected: tuple[int, ...], seconds: float = 3) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if selected_numbers(page) == expected:
            return
        page.wait_for_timeout(100)
    actual = selected_numbers(page)
    raise CartAutomationError(
        f"Seleção divergente: esperado {_format_ticket(expected)}, "
        f"encontrado {_format_ticket(actual)}. Nenhuma aposta foi incluída."
    )


def _format_ticket(ticket: tuple[int, ...]) -> str:
    return " ".join(f"{number:02d}" for number in ticket) or "nenhuma dezena"


def fill_ticket(page, ticket: tuple[int, ...]) -> None:
    """Limpa a seleção anterior, marca seis dezenas e confere o resultado."""
    ticket = _check_ticket(ticket)
    selected_numbers(page)
    clear_button = page.locator("button#limparvolante")
    if clear_button.count() != 1:
        raise CartAutomationError("Botão 'Limpar Volante' não encontrado.")
    clear_button.click()
    _wait_for_selection(page, ())
    for number in ticket:
        page.locator(f"{GRID} a#n{number:02d}").click()
    _wait_for_selection(page, ticket)


def _numeric_control(page, label: str) -> int:
    items = page.locator("#container-volante .numero-item").filter(has_text=label)
    if items.count() != 1:
        raise CartAutomationError(f"Controle '{label}' não encontrado de forma única.")
    value = items.locator(".input-mais-menos > span")
    if value.count() != 1:
        value = items.locator(":scope > span")
    if value.count() != 1:
        raise CartAutomationError(f"Não foi possível conferir '{label}'.")
    try:
        return int(value.inner_text().strip())
    except ValueError as exc:
        raise CartAutomationError(f"Valor inválido em '{label}'.") from exc


def _check_price(page, expected_price: Decimal) -> None:
    price_element = page.locator("#valoraposta")
    if price_element.count() == 1:
        text = "Valor da Aposta: " + price_element.inner_text()
    else:
        text = page.locator("#container-volante").inner_text()
    match = re.search(r"Valor\s+da\s+Aposta\s*:\s*R\$\s*([\d.]+,\d{2})", text, re.I)
    if not match:
        raise CartAutomationError("Não foi possível conferir o valor da aposta.")
    try:
        actual_price = Decimal(match.group(1).replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise CartAutomationError("Valor da aposta ilegível.") from exc
    if actual_price != expected_price:
        raise CartAutomationError(
            f"Valor da aposta {actual_price}; esperado {expected_price}. "
            "Confira preço, quantidade e teimosinha."
        )


def _recent_tickets(page) -> list[tuple[int, ...]]:
    recent: list[tuple[int, ...]] = []
    for card in page.locator(RECENT_CARDS).all():
        values = card.locator(RECENT_NUMBERS).all_text_contents()
        try:
            numbers = tuple(sorted(int(value.strip()) for value in values))
        except ValueError:
            continue
        if len(numbers) == 6:
            recent.append(numbers)
    return recent


def add_ticket_to_cart(
    page, ticket: tuple[int, ...], *, expected_price: Decimal = Decimal("6.00")
) -> None:
    """Clica uma única vez e só retorna após ver a aposta na lista recente."""
    ticket = _check_ticket(ticket)
    if selected_numbers(page) != ticket:
        raise CartAutomationError("As dezenas mudaram antes da inclusão; clique cancelado.")
    if _numeric_control(page, "Quantidade de números da aposta") != 6:
        raise CartAutomationError("A quantidade de dezenas não é 6; clique cancelado.")
    if _numeric_control(page, "Teimosinhas") != 0:
        raise CartAutomationError("Teimosinhas não está em 0; clique cancelado.")
    _check_price(page, expected_price)
    if ticket in _recent_tickets(page):
        raise CartAutomationError("Esse jogo já aparece nas apostas recentes.")
    add_button = page.locator("button#colocarnocarrinho")
    if add_button.count() != 1 or not add_button.is_enabled():
        raise CartAutomationError("Botão 'Colocar no Carrinho' indisponível.")

    add_button.click()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ticket in _recent_tickets(page):
            return
        page.wait_for_timeout(200)
    raise CartAutomationError(
        "O clique ocorreu, mas a aposta não apareceu na lista recente. "
        "Verifique o carrinho antes de tentar novamente."
    )


OFFICIAL_HOST = "www.loteriasonline.caixa.gov.br"
CART_ROWS = '#tabelaUnicaCarrinho tbody tr'
CART_NUMBERS = ".numeros-volante span.margemVolante"


@dataclass(frozen=True)
class CartEntry:
    numbers: tuple[int, ...]
    contest: str | None
    teimosinhas: int | None
    price: Decimal | None


def _check_official_site(page) -> None:
    if urlparse(page.url).hostname != OFFICIAL_HOST or not page.url.startswith("https://"):
        raise CartAutomationError(
            "A página aberta não é o portal oficial HTTPS das Loterias CAIXA."
        )


def _change_route(page, route: str) -> None:
    _check_official_site(page)
    page.evaluate("route => { window.location.hash = '#/' + route; }", route)
    page.wait_for_url(f"**/#/{route}", timeout=15000)
    if route == "mega-sena":
        page.locator(GRID).wait_for(state="visible", timeout=15000)
        page.wait_for_function(
            "() => document.querySelectorAll('ul.escolhe-numero.mega-sena a[id^=n]').length === 60",
            timeout=15000,
        )
        selected_numbers(page)
    else:
        page.locator('[id="CarrinhoView.html"]').wait_for(
            state="visible", timeout=15000
        )


def go_to_cart(page, *, require_sync: bool = False) -> bool:
    """Abre o carrinho e espera a sincronização HTTP, quando ela ocorrer."""
    started: set[object] = set()
    finished: set[object] = set()
    failed: set[object] = set()
    statuses: dict[object, int] = {}
    responses: list[object] = []

    def is_cart_get(request) -> bool:
        path = urlparse(request.url).path.rstrip("/")
        return request.method == "GET" and path.endswith("/carrinhos")

    def on_request(request) -> None:
        if is_cart_get(request):
            started.add(request)

    def on_response(response) -> None:
        if is_cart_get(response.request):
            started.add(response.request)
            statuses[response.request] = response.status
            responses.append(response)

    def on_finished(request) -> None:
        if is_cart_get(request):
            finished.add(request)

    def on_failed(request) -> None:
        if is_cart_get(request):
            failed.add(request)

    callbacks = {
        "request": on_request,
        "response": on_response,
        "requestfinished": on_finished,
        "requestfailed": on_failed,
    }
    for event, callback in callbacks.items():
        page.on(event, callback)
    try:
        _change_route(page, "carrinho")
        start_deadline = time.monotonic() + 4
        while not started and time.monotonic() < start_deadline:
            page.wait_for_timeout(100)
        if not started:
            if require_sync:
                raise CartAutomationError(
                    "A sincronização esperada do carrinho não ocorreu."
                )
            return False

        finish_deadline = time.monotonic() + 30
        while started - finished - failed and time.monotonic() < finish_deadline:
            page.wait_for_timeout(100)
        if failed or started - finished or any(
            not 200 <= statuses.get(request, 0) < 300 for request in started
        ):
            raise CartAutomationError(
                "A sincronização do carrinho com a CAIXA falhou ou expirou."
            )
        try:
            payload = responses[-1].json()
            individuals = payload["apostasIndividuais"]
            if individuals is None:
                individuals = []
            if not isinstance(individuals, list):
                raise TypeError("apostasIndividuais não é lista")
            expected: Counter[CartEntry] = Counter()
            for item in individuals:
                if not isinstance(item, dict):
                    raise TypeError("aposta não é objeto")
                if item.get("modalidade") != "MEGA_SENA" or item.get("surpresinha"):
                    continue
                raw = item.get("numerosSelecionados") or []
                if len(raw) == 6:
                    contest = (
                        item.get("numeroConcurso")
                        or item.get("concursoAlvo")
                        or item.get("concursoInicial")
                    )
                    if contest is None or item.get("valor") is None:
                        raise TypeError("metadados da aposta ausentes")
                    entry = CartEntry(
                        numbers=tuple(sorted(int(value) for value in raw)),
                        contest=str(contest),
                        teimosinhas=int(item.get("quantidadeTeimosinhas") or 0),
                        price=Decimal(str(item["valor"])),
                    )
                    expected[entry] += 1
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CartAutomationError(
                "A resposta do carrinho mudou de formato; não é seguro continuar."
            ) from exc

        # A resposta pode chegar antes de o Angular atualizar a tabela.
        render_deadline = time.monotonic() + 15
        while time.monotonic() < render_deadline:
            try:
                table = page.locator("#tabelaUnicaCarrinho table").first
                row_count = (
                    table.locator(":scope > tbody > tr").count() if table.count() else 0
                )
                if row_count == len(individuals) and Counter(
                    read_cart_entries(page)
                ) == expected:
                    return True
            except CartAutomationError:
                pass
            page.wait_for_timeout(150)
        raise CartAutomationError(
            "A tabela do carrinho não corresponde à resposta da CAIXA."
        )
    finally:
        for event, callback in callbacks.items():
            page.remove_listener(event, callback)


def go_to_megasena(page) -> None:
    _change_route(page, "mega-sena")


def current_contest(page) -> str:
    heading = page.locator("header-volante .titulo-pagina h3 span")
    if heading.count() != 1:
        raise CartAutomationError("Não foi possível identificar o concurso aberto.")
    match = re.search(r"\b\d{4,5}\b", heading.inner_text())
    if not match:
        raise CartAutomationError("Número do concurso atual ilegível.")
    return match.group(0)


def read_cart_entries(page) -> list[CartEntry]:
    """Lê dezenas, concurso, teimosinha e preço na tabela completa."""
    _check_official_site(page)
    if "#/carrinho" not in page.url:
        raise CartAutomationError("Abra o carrinho antes de ler as apostas.")
    root = page.locator('[id="CarrinhoView.html"]')
    if root.count() != 1 or not root.is_visible():
        raise CartAutomationError("A página do carrinho não carregou.")
    table = root.locator("#tabelaUnicaCarrinho")
    if table.count() == 0:
        # O componente com a tabela só é criado pelo portal quando há apostas.
        if root.locator("apostas-carrinho").count() == 0:
            return []
        try:
            table.wait_for(state="attached", timeout=5000)
        except Exception as exc:
            raise CartAutomationError(
                "Não foi possível ler a tabela do carrinho."
            ) from exc
    if table.count() != 1:
        raise CartAutomationError("Tabela do carrinho ambígua.")
    entries: list[CartEntry] = []
    outer_table = table.locator("table").first
    for row in outer_table.locator(":scope > tbody > tr").all():
        name = row.locator(".nome-modalidade-aposta-individual-carrinho")
        if name.count() != 1:
            raise CartAutomationError("Modalidade ilegível em uma linha do carrinho.")
        if "Mega-Sena" not in name.inner_text():
            continue
        raw = row.locator(CART_NUMBERS).all_text_contents()
        if raw and all(value.strip().upper() == "XX" for value in raw):
            # Surpresinha: dezenas ocultas até o registro e não comparáveis.
            continue
        if len(raw) < 6:
            raise CartAutomationError("Uma aposta da Mega-Sena está incompleta no carrinho.")
        try:
            values = tuple(sorted(int(value.strip()) for value in raw))
        except ValueError as exc:
            raise CartAutomationError("Dezenas ilegíveis no carrinho.") from exc
        if len(values) == 6 and len(set(values)) != 6:
            raise CartAutomationError("Uma aposta da Mega-Sena tem dezenas repetidas.")
        if len(values) == 6:
            contest_cell = row.locator("td.alterar-teimosinha-carrinho")
            contest: str | None = None
            teimosinhas: int | None = None
            if contest_cell.count() == 1:
                contest_text = contest_cell.evaluate(
                    "element => [...element.childNodes]"
                    ".filter(node => node.nodeType === Node.TEXT_NODE)"
                    ".map(node => node.textContent).join(' ')"
                )
                contest_match = re.search(r"\b\d{4,5}\b", contest_text)
                if contest_match:
                    contest = contest_match.group(0)
                count = contest_cell.locator(".qtde-teimosinha-carrinho")
                if count.count() == 1:
                    try:
                        teimosinhas = int(count.inner_text().strip())
                    except ValueError:
                        pass
            price_match = re.search(r"R\$\s*([\d.]+,\d{2})", row.inner_text())
            price = (
                Decimal(price_match.group(1).replace(".", "").replace(",", "."))
                if price_match
                else None
            )
            entries.append(CartEntry(values, contest, teimosinhas, price))
    return entries


def read_cart_tickets(page) -> Counter[tuple[int, ...]]:
    """Conta apostas simples da Mega-Sena na tabela completa do carrinho."""
    return Counter(entry.numbers for entry in read_cart_entries(page))


def _check_portfolio_entries(
    entries: list[CartEntry], tickets: list[tuple[int, ...]], contest: str | None
) -> str | None:
    target_tickets = set(tickets)
    for entry in entries:
        if entry.numbers not in target_tickets:
            continue
        if entry.price != Decimal("6.00") or entry.teimosinhas != 0:
            raise CartAutomationError(
                f"Jogo {_format_ticket(entry.numbers)} já está no carrinho "
                "com preço ou teimosinha diferente do esperado."
            )
        if entry.contest is None:
            raise CartAutomationError("Não foi possível conferir o concurso no carrinho.")
        if contest is None:
            contest = entry.contest
        elif entry.contest != contest:
            raise CartAutomationError(
                f"Há apostas em concursos diferentes ({contest} e {entry.contest})."
            )
    return contest


def wait_for_cart_ticket(page, ticket: tuple[int, ...], seconds: float = 20) -> None:
    """Confirma a linha exata na página completa do carrinho."""
    ticket = _check_ticket(ticket)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        count = read_cart_tickets(page)[ticket]
        if count == 1:
            return
        if count > 1:
            raise CartAutomationError(
                f"O jogo {_format_ticket(ticket)} aparece {count} vezes no carrinho."
            )
        page.wait_for_timeout(250)
    raise CartAutomationError(
        f"O jogo {_format_ticket(ticket)} não apareceu no carrinho. "
        "Não tente incluí-lo novamente sem conferir a página."
    )


def run_portfolio(page, tickets: list[tuple[int, ...]], confirm_cart_loaded=None) -> None:
    """Retoma pelos jogos já presentes e confere o carrinho após cada inclusão."""
    _check_official_site(page)
    requires_sync = go_to_cart(page)
    if not requires_sync:
        if confirm_cart_loaded is None or not confirm_cart_loaded():
            raise CartAutomationError(
                "Não foi possível confirmar que o carrinho terminou de carregar."
            )
    entries = read_cart_entries(page)
    contest = _check_portfolio_entries(entries, tickets, None)
    existing = Counter(entry.numbers for entry in entries)
    for index, ticket in enumerate(tickets, 1):
        if existing[ticket] > 1:
            raise CartAutomationError(
                f"Jogo {index:02d} já está duplicado no carrinho; execução interrompida."
            )
    go_to_megasena(page)
    current = current_contest(page)
    if contest is not None and contest != current:
        raise CartAutomationError(
            f"O carrinho contém concurso {contest}, mas o volante está no {current}."
        )
    contest = current
    for index, ticket in enumerate(tickets, 1):
        if existing[ticket] == 1:
            print(f"{index:02d}/25: já está no carrinho — {_format_ticket(ticket)}")
            continue
        go_to_megasena(page)
        if current_contest(page) != contest:
            raise CartAutomationError("O concurso mudou durante a execução.")
        fill_ticket(page, ticket)
        add_ticket_to_cart(page, ticket)
        requires_sync = go_to_cart(page, require_sync=requires_sync) or requires_sync
        wait_for_cart_ticket(page, ticket)
        entries = read_cart_entries(page)
        contest = _check_portfolio_entries(entries, tickets, contest)
        existing = Counter(entry.numbers for entry in entries)
        print(f"{index:02d}/25: incluído e conferido — {_format_ticket(ticket)}")

    final_entries = read_cart_entries(page)
    _check_portfolio_entries(final_entries, tickets, contest)
    final = Counter(entry.numbers for entry in final_entries)
    missing = [index for index, ticket in enumerate(tickets, 1) if final[ticket] != 1]
    if missing:
        raise CartAutomationError(f"Conferência final falhou nos jogos: {missing}.")

"""Adiciona e confere os 25 jogos no carrinho oficial da Mega-Sena."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from megasena.cart_automation import (
    CartAutomationError,
    GRID,
    OFFICIAL_HOST,
    run_portfolio,
    validate_tickets,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_TICKETS = ROOT / "assets" / "carteira-25-2026-09-25.json"
DEFAULT_PROFILE = ROOT / "data" / "perfil-navegador-carrinho"
MEGA_URL = f"https://{OFFICIAL_HOST}/silce-web/#/mega-sena"


def confirm_cart_loaded() -> bool:
    print(
        "\nO portal não solicitou sincronização de conta. "
        "Confira no navegador se o carrinho terminou de carregar."
    )
    answer = input("Digite CONFERIDO para iniciar os jogos: ")
    return answer.strip().upper() == "CONFERIDO"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preenche 25 apostas simples da Mega-Sena e confere o carrinho."
    )
    parser.add_argument("--arquivo", type=Path, default=DEFAULT_TICKETS)
    parser.add_argument(
        "--conferir",
        action="store_true",
        help="Mostra a carteira sem abrir o site nem adicionar apostas.",
    )
    parser.add_argument(
        "--navegador", choices=("msedge", "chrome"), default="msedge"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        tickets = validate_tickets(args.arquivo)
    except ValueError as exc:
        print(f"Carteira inválida: {exc}", file=sys.stderr)
        return 2

    print(f"Carteira: {args.arquivo}")
    for index, ticket in enumerate(tickets, 1):
        print(f"{index:02d}. {' '.join(f'{number:02d}' for number in ticket)}")
    print("25 jogos simples; valor esperado: R$ 150,00 para um concurso.")
    if args.conferir:
        return 0

    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        print(
            "Instale no interpretador atual: python -m pip install -r "
            "requirements-automation.txt",
            file=sys.stderr,
        )
        return 2

    DEFAULT_PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(DEFAULT_PROFILE),
                channel=args.navegador,
                headless=False,
                viewport={"width": 1320, "height": 900},
                accept_downloads=False,
            )
        except PlaywrightError as exc:
            print(f"Não foi possível abrir o navegador: {exc}", file=sys.stderr)
            return 1
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(MEGA_URL, wait_until="domcontentloaded", timeout=30000)
            print(
                "\nNo navegador, confirme a maioridade, acesse sua conta se quiser "
                "e abra o volante da Mega-Sena."
            )
            input("Quando as dezenas 01–60 estiverem visíveis, pressione Enter aqui: ")
            active_pages = [
                candidate
                for candidate in context.pages
                if candidate.url.startswith(f"https://{OFFICIAL_HOST}/silce-web/")
                and "#/mega-sena" in candidate.url
            ]
            if active_pages:
                page = active_pages[-1]
            if "#/mega-sena" not in page.url:
                raise CartAutomationError("Abra a página da Mega-Sena antes de continuar.")
            page.locator(GRID).wait_for(state="visible", timeout=10000)
            run_portfolio(page, tickets, confirm_cart_loaded=confirm_cart_loaded)
            print(
                "\nOs 25 jogos desta carteira aparecem uma vez cada no carrinho. "
                "Confira concurso e valor no site. A compra não foi finalizada."
            )
            result = 0
        except (CartAutomationError, KeyboardInterrupt, PlaywrightError, EOFError) as exc:
            print(f"\nExecução interrompida: {exc}", file=sys.stderr)
            print(
                "Confira o carrinho antes de executar de novo. Na próxima execução, "
                "os jogos já encontrados serão ignorados.",
                file=sys.stderr,
            )
            result = 1
        finally:
            try:
                input("O navegador ficará aberto para conferência. Enter para fechar: ")
            except EOFError:
                pass
            context.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())

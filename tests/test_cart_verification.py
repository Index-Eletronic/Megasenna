"""Confere apostas no carrinho por uma página local, sem acessar a CAIXA."""

from __future__ import annotations

import unittest
from collections import Counter
from decimal import Decimal

from megasena.cart_automation import (
    CartAutomationError,
    _check_portfolio_entries,
    read_cart_entries,
    read_cart_tickets,
    wait_for_cart_ticket,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


CART_URL = "https://www.loteriasonline.caixa.gov.br/silce-web/#/carrinho"
TICKET = (1, 5, 12, 13, 17, 31)
OTHER_TICKET = (2, 19, 23, 39, 41, 51)


def cart_row(
    ticket: tuple[int, ...],
    modality: str = "Mega-Sena",
    contest: str = "3073",
    teimosinhas: int = 0,
    price: str = "6,00",
) -> str:
    numbers = "".join(
        f'<span class="margemVolante">{number:02d}</span>' for number in ticket
    )
    return (
        "<tr><td>"
        f'<h6 class="nome-modalidade-aposta-individual-carrinho">{modality}</h6>'
        "</td><td>"
        f'<div class="numeros-volante">{numbers}</div>'
        '</td><td class="alterar-teimosinha-carrinho">'
        f'{contest}<span class="qtde-teimosinha-carrinho">{teimosinhas}</span>'
        f'</td><td>R$ {price}</td></tr>'
    )


@unittest.skipIf(sync_playwright is None, "Playwright não está instalado")
class CartVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            cls.playwright.stop()
            raise unittest.SkipTest(f"Edge não está disponível para Playwright: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        # Intercepta o endereço oficial antes da navegação: os testes não fazem
        # nenhuma chamada de rede ao portal de apostas.
        self.page.route(
            "https://www.loteriasonline.caixa.gov.br/silce-web/",
            lambda route: route.fulfill(status=200, content_type="text/html", body="<html></html>"),
        )
        self.page.goto(CART_URL)

    def tearDown(self):
        self.page.close()

    def show_rows(self, *rows: str) -> None:
        self.page.set_content(
            '<div id="CarrinhoView.html">'
            '<div id="tabelaUnicaCarrinho"><table><tbody>'
            + "".join(rows)
            + "</tbody></table></div></div>"
        )

    def test_le_jogo_exato_e_ignora_outra_modalidade(self):
        self.show_rows(cart_row(TICKET), cart_row(OTHER_TICKET, "Quina"))

        self.assertEqual(read_cart_tickets(self.page), Counter({TICKET: 1}))
        wait_for_cart_ticket(self.page, TICKET, seconds=0.1)

    def test_rejeita_jogo_ausente(self):
        self.show_rows(cart_row(OTHER_TICKET))

        self.assertEqual(read_cart_tickets(self.page)[TICKET], 0)
        with self.assertRaisesRegex(CartAutomationError, "não apareceu no carrinho"):
            wait_for_cart_ticket(self.page, TICKET, seconds=0.1)

    def test_detecta_jogo_duplicado(self):
        self.show_rows(cart_row(TICKET), cart_row(TICKET))

        self.assertEqual(read_cart_tickets(self.page)[TICKET], 2)
        with self.assertRaisesRegex(CartAutomationError, "aparece 2 vezes"):
            wait_for_cart_ticket(self.page, TICKET, seconds=0.1)

    def test_confere_concurso_teimosinha_e_preco(self):
        self.show_rows(cart_row(TICKET))
        entries = read_cart_entries(self.page)
        self.assertEqual(entries[0].contest, "3073")
        self.assertEqual(entries[0].teimosinhas, 0)
        self.assertEqual(entries[0].price, Decimal("6.00"))
        self.assertEqual(_check_portfolio_entries(entries, [TICKET], None), "3073")

        self.show_rows(cart_row(TICKET, teimosinhas=2))
        with self.assertRaises(CartAutomationError):
            _check_portfolio_entries(read_cart_entries(self.page), [TICKET], None)

        self.show_rows(cart_row(TICKET, price="12,00"))
        with self.assertRaises(CartAutomationError):
            _check_portfolio_entries(read_cart_entries(self.page), [TICKET], None)

        self.show_rows(cart_row(TICKET, contest="3074"))
        with self.assertRaisesRegex(CartAutomationError, "concursos diferentes"):
            _check_portfolio_entries(read_cart_entries(self.page), [TICKET], "3073")


if __name__ == "__main__":
    unittest.main()

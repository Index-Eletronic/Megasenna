"""Fluxo do volante em navegador real, usando somente uma página local de teste."""

from __future__ import annotations

import unittest
from pathlib import Path

from megasena.cart_automation import CartAutomationError, add_ticket_to_cart, fill_ticket

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


FIXTURE = Path(__file__).parent / "fixtures" / "caixa_volante.html"
TICKET = (1, 2, 3, 4, 5, 6)


@unittest.skipIf(sync_playwright is None, "Playwright não está instalado")
class CartBrowserTests(unittest.TestCase):
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
        self.page.goto(FIXTURE.resolve().as_uri())

    def tearDown(self):
        self.page.close()

    def selected_numbers(self):
        return tuple(
            int(value)
            for value in self.page.locator("ul.escolhe-numero.mega-sena a.selected").all_text_contents()
        )

    def cart_rows(self):
        return self.page.locator(".volante.mega-sena")

    def test_fill_clears_preexisting_selection_and_marks_exact_ticket(self):
        self.assertEqual(self.selected_numbers(), (58,))
        fill_ticket(self.page, TICKET)
        self.assertEqual(self.selected_numbers(), TICKET)
        self.assertEqual(self.page.evaluate("window.resetCount"), 1)
        self.assertEqual(self.cart_rows().count(), 0)

    def test_add_confirms_exact_ticket_in_new_cart_row(self):
        fill_ticket(self.page, TICKET)
        add_ticket_to_cart(self.page, TICKET)
        self.assertEqual(self.page.evaluate("window.addCount"), 1)
        self.assertEqual(self.cart_rows().count(), 1)
        row_numbers = self.cart_rows().first.locator(
            ".numero-volante-aposta-incluida span.margemVolante"
        ).all_text_contents()
        self.assertEqual(tuple(int(value) for value in row_numbers), TICKET)

    def test_fill_stops_when_site_marks_an_extra_number(self):
        self.page.evaluate("window.forceWrongSelection = true")
        with self.assertRaises(CartAutomationError):
            fill_ticket(self.page, TICKET)
        self.assertEqual(self.page.evaluate("window.addCount"), 0)
        self.assertEqual(self.cart_rows().count(), 0)

    def test_add_stops_before_click_when_selection_changed(self):
        fill_ticket(self.page, TICKET)
        self.page.locator("#n06").evaluate("element => element.classList.remove('selected')")
        with self.assertRaises(CartAutomationError):
            add_ticket_to_cart(self.page, TICKET)
        self.assertEqual(self.page.evaluate("window.addCount"), 0)
        self.assertEqual(self.cart_rows().count(), 0)

    def test_add_stops_when_cart_does_not_confirm_inclusion(self):
        fill_ticket(self.page, TICKET)
        self.page.evaluate("window.suppressCart = true")
        with self.assertRaises(CartAutomationError):
            add_ticket_to_cart(self.page, TICKET)
        self.assertEqual(self.page.evaluate("window.addCount"), 1)
        self.assertEqual(self.cart_rows().count(), 0)


if __name__ == "__main__":
    unittest.main()

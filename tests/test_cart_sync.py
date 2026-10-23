"""Espera a sincronização do carrinho antes de confiar no DOM local."""

from __future__ import annotations

import unittest

from megasena.cart_automation import CartAutomationError, go_to_cart

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


MEGA_URL = "https://www.loteriasonline.caixa.gov.br/silce-web/#/mega-sena"
HTML = """<!doctype html><html><body><div id="app"></div><script>
function render() {
  if (location.hash !== '#/carrinho') return;
  document.querySelector('#app').innerHTML = '<div id="CarrinhoView.html">Carrinho</div>';
  if (window.staleCart) {
    document.querySelector('[id="CarrinhoView.html"]').innerHTML =
      '<div id="tabelaUnicaCarrinho"><table><tbody><tr><td><h6 class="nome-modalidade-aposta-individual-carrinho">Mega-Sena</h6></td><td><div class="numeros-volante">'
      + [1,2,3,4,5,6].map(number => '<span class="margemVolante">' + number + '</span>').join('')
      + '</div></td><td class="alterar-teimosinha-carrinho">3072<span class="qtde-teimosinha-carrinho">1</span></td><td>R$ 12,00</td></tr></tbody></table></div>';
  }
  if (window.doFetch) {
    fetch('/api/carrinhos/').then(response => response.json()).then(data => {
      setTimeout(() => {
      const root = document.querySelector('[id="CarrinhoView.html"]');
      root.innerHTML = '<div id="tabelaUnicaCarrinho"><table><tbody>'
        + data.apostasIndividuais.map(item => '<tr><td><h6 class="nome-modalidade-aposta-individual-carrinho">Mega-Sena</h6></td><td><div class="numeros-volante">'
        + item.numerosSelecionados.map(number => '<span class="margemVolante">' + number + '</span>').join('')
        + '</div></td><td class="alterar-teimosinha-carrinho">' + item.concursoAlvo
        + '<span class="qtde-teimosinha-carrinho">' + item.quantidadeTeimosinhas + '</span></td>'
        + '<td>R$ ' + Number(item.valor).toFixed(2).replace('.', ',') + '</td></tr>').join('')
        + '</tbody></table></div>';
      root.dataset.synced = 'yes';
      }, window.renderDelay || 0);
    }).catch(() => {});
  }
}
window.addEventListener('hashchange', render);
render();
</script></body></html>"""


@unittest.skipIf(sync_playwright is None, "Playwright não está instalado")
class CartSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            cls.playwright.stop()
            raise unittest.SkipTest(f"Edge não está disponível: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.route(
            "https://www.loteriasonline.caixa.gov.br/silce-web/",
            lambda route: route.fulfill(status=200, content_type="text/html", body=HTML),
        )
        self.page.goto(MEGA_URL)

    def tearDown(self):
        self.page.close()

    def test_aguarda_get_bem_sucedido(self):
        self.page.route(
            "**/api/carrinhos/",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"apostasIndividuais":[{"modalidade":"MEGA_SENA",'
                '"surpresinha":false,"numerosSelecionados":[1,2,3,4,5,6],'
                '"concursoAlvo":3073,"quantidadeTeimosinhas":0,"valor":6}]}',
            ),
        )
        self.page.evaluate("window.doFetch = true; window.staleCart = true; window.renderDelay = 750")
        self.assertTrue(go_to_cart(self.page))
        self.assertEqual(
            self.page.locator('[id="CarrinhoView.html"]').get_attribute("data-synced"),
            "yes",
        )

    def test_rejeita_resposta_http_erro(self):
        self.page.route(
            "**/api/carrinhos/",
            lambda route: route.fulfill(
                status=500, content_type="application/json", body="{}"
            ),
        )
        self.page.evaluate("window.doFetch = true")
        with self.assertRaisesRegex(CartAutomationError, "sincronização"):
            go_to_cart(self.page)

    def test_sem_get_exige_conferencia_se_era_esperado(self):
        self.assertFalse(go_to_cart(self.page))
        self.page.evaluate("location.hash = '#/mega-sena'")
        with self.assertRaisesRegex(CartAutomationError, "sincronização esperada"):
            go_to_cart(self.page, require_sync=True)


if __name__ == "__main__":
    unittest.main()

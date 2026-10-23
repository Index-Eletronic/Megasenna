"""Calibração do volante por coordenadas, sem controlar o mouse de verdade."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import math
import tempfile
from types import SimpleNamespace
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import preencher_carrinho_pyautogui as desktop

from megasena.pyautogui_cart import (
    CoordinateAutomationError,
    calibrate_grid,
    current_contest_from_page,
    fill_and_submit,
    layout_matches,
    layout_signature,
    number_center,
    page_controls_ok,
    page_total,
    recent_cards,
    recent_tickets,
    selected_numbers,
    validate_layout,
)
from megasena.virtual_desktop import (
    VirtualDesktopGUI,
    VirtualScreenshot,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    SM_CXVIRTUALSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
)


class GridCalibrationTests(unittest.TestCase):
    def test_layout_de_22_colunas_mapeia_as_60_dezenas(self):
        calibration = calibrate_grid(
            first=(62, 156),
            last_first=(1106, 156),
            first_last=(62, 302),
            columns=22,
            screen_size=(1920, 1080),
        )
        dx = (1106 - 62) / 21
        expected = {
            1: (62, 156),
            22: (1106, 156),
            23: (62, 229),
            44: (1106, 229),
            45: (62, 302),
            60: (62 + 15 * dx, 302),
        }
        for number, (x, y) in expected.items():
            with self.subTest(number=number):
                actual = number_center(calibration, number)
                self.assertAlmostEqual(actual[0], x, delta=1)
                self.assertAlmostEqual(actual[1], y, delta=1)

    def test_layout_de_17_colunas_tambem_mapeia_quatro_linhas(self):
        calibration = calibrate_grid(
            first=(50, 175),
            last_first=(1042, 175),
            first_last=(50, 448),
            columns=17,
            screen_size=(1920, 1080),
        )
        expected = {
            1: (50, 175),
            17: (1042, 175),
            18: (50, 266),
            34: (1042, 266),
            35: (50, 357),
            51: (1042, 357),
            52: (50, 448),
            60: (546, 448),
        }
        for number, (x, y) in expected.items():
            with self.subTest(number=number):
                actual = number_center(calibration, number)
                self.assertAlmostEqual(actual[0], x, delta=1)
                self.assertAlmostEqual(actual[1], y, delta=1)

    def test_rejeita_dezenas_fora_do_volante(self):
        calibration = calibrate_grid(
            (62, 156), (1106, 156), (62, 302), 22, (1920, 1080)
        )
        for number in (0, 61, -1, True, 1.5, "01"):
            with self.subTest(number=number), self.assertRaises(ValueError):
                number_center(calibration, number)

    def test_rejeita_colunas_ou_referencias_geometricas_invalidas(self):
        cases = (
            ((62, 156), (1106, 156), (62, 302), 0, (1920, 1080)),
            ((62, 156), (1106, 156), (62, 302), 1, (1920, 1080)),
            ((62, 156), (62, 156), (62, 302), 22, (1920, 1080)),
            ((62, 156), (1106, 156), (62, 156), 22, (1920, 1080)),
            ((62, 156), (1106, 156), (62, 302), 22, (0, 1080)),
            ((-1, 156), (1106, 156), (62, 302), 22, (1920, 1080)),
            ((62, 156), (2000, 156), (62, 302), 22, (1920, 1080)),
        )
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calibrate_grid(*args)

    def test_rejeita_tela_diferente_da_calibrada(self):
        calibration = calibrate_grid(
            (62, 156), (1106, 156), (62, 302), 22, (1920, 1080)
        )
        validate_layout(calibration, (1920, 1080))
        with self.assertRaises(ValueError):
            validate_layout(calibration, (1366, 768))


class VirtualDesktopGeometryTests(unittest.TestCase):
    """Coordenadas do mouse são globais; pixels da captura começam na origem virtual."""

    def test_monitor_a_direita_aceita_coordenadas_reais_do_usuario_e_confere_60(self):
        calibration = calibrate_grid(
            (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
            screen_origin=(1920, 0), last_last=(3505, 593),
        )
        self.assertEqual(calibration.screen_origin, (1920, 0))
        self.assertEqual(number_center(calibration, 1), (2570, 411))
        self.assertEqual(number_center(calibration, 22), (3875, 409))
        self.assertEqual(number_center(calibration, 45), (2573, 594))
        self.assertEqual(number_center(calibration, 60), (3505, 593))
        validate_layout(calibration, (2240, 1350), screen_origin=(1920, 0))

    def test_origem_negativa_preserva_mapeamento_das_dezenas(self):
        calibration = calibrate_grid(
            (-1800, 200), (-756, 200), (-1800, 346), 22, (1920, 1080),
            screen_origin=(-1920, -200), last_last=(-1054, 346),
        )
        self.assertEqual(number_center(calibration, 60), (-1054, 346))
        validate_layout(calibration, (1920, 1080), screen_origin=(-1920, -200))
        with self.assertRaises(ValueError):
            validate_layout(calibration, (1920, 1080), screen_origin=(0, 0))

    def test_ponto_60_manual_detecta_grade_ou_zoom_incoerente(self):
        with self.assertRaises(ValueError):
            calibrate_grid(
                (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
                screen_origin=(1920, 0), last_last=(3670, 593),
            )
        with self.assertRaises(ValueError):
            calibrate_grid(
                (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
                screen_origin=(1920, 0), last_last=(3505, 680),
            )

    def test_ponto_60_fora_do_monitor_calibrado_e_rejeitado(self):
        with self.assertRaises(ValueError):
            calibrate_grid(
                (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
                screen_origin=(1920, 0), last_last=(4300, 593),
            )

    def test_60_em_quatro_linhas_quando_primeira_tem_17_dezenas(self):
        calibration = calibrate_grid(
            (2050, 175), (3042, 175), (2050, 448), 17, (1440, 1080),
            screen_origin=(1920, 0), last_last=(2546, 448),
        )
        self.assertEqual(calibration.first_number_last_row, 52)
        self.assertEqual(number_center(calibration, 60), (2546, 448))


class FakeWindowsFunction:
    def __init__(self, implementation):
        self.implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.implementation(*args)


class FakeUser32:
    def __init__(self, bounds=(0, 0, 4800, 1350)):
        self.bounds = list(bounds)
        self.cursor = (0, 0)
        self.mouse_events = []
        self.set_cursor_calls = []
        self.window_points = []
        self.window_child = 101
        self.window_root = 100
        self.window_class = "Chrome_WidgetWin_1"
        self.foreground_window = 100
        self.foreground_calls = []
        self.GetSystemMetrics = FakeWindowsFunction(self._get_metric)
        self.SetCursorPos = FakeWindowsFunction(self._set_cursor)
        self.mouse_event = FakeWindowsFunction(self._mouse_event)
        self.WindowFromPoint = FakeWindowsFunction(self._window_from_point)
        self.GetAncestor = FakeWindowsFunction(self._get_ancestor)
        self.GetClassNameW = FakeWindowsFunction(self._get_class_name)
        self.GetForegroundWindow = FakeWindowsFunction(lambda: self.foreground_window)
        self.SetForegroundWindow = FakeWindowsFunction(self._set_foreground_window)

    def _get_metric(self, code):
        return {
            SM_XVIRTUALSCREEN: self.bounds[0],
            SM_YVIRTUALSCREEN: self.bounds[1],
            SM_CXVIRTUALSCREEN: self.bounds[2],
            SM_CYVIRTUALSCREEN: self.bounds[3],
        }.get(code, 0)

    def _set_cursor(self, x, y):
        self.set_cursor_calls.append((x, y))
        self.cursor = (x, y)
        return True

    def _mouse_event(self, *args):
        self.mouse_events.append(args)

    def _window_from_point(self, point):
        self.window_points.append((point.x, point.y))
        return self.window_child

    def _get_ancestor(self, child, flag):
        assert child == self.window_child and flag == 2
        return self.window_root

    def _get_class_name(self, root, buffer, capacity):
        assert root == self.window_root
        buffer.value = self.window_class[: capacity - 1]
        return len(buffer.value)

    def _set_foreground_window(self, root):
        self.foreground_calls.append(root)
        self.foreground_window = root
        return True


class FakePixelImage:
    def __init__(self, size):
        self.size = size
        self.pixels_read = []
        self.crops = []

    def getpixel(self, point):
        self.pixels_read.append(point)
        return (12, 34, 56)

    def crop(self, box):
        self.crops.append(box)
        return box


class FakePyAutoGUI:
    PAUSE = 0

    def __init__(self, user32, screenshot_size):
        self.user32 = user32
        self.image = FakePixelImage(screenshot_size)
        self.screenshot_calls = []
        self.click_calls = []
        self.move_calls = []

    def screenshot(self, **kwargs):
        self.screenshot_calls.append(kwargs)
        return self.image

    def position(self):
        return self.user32.cursor

    def failSafeCheck(self):
        pass

    def click(self, *args):
        self.click_calls.append(args)

    def moveTo(self, x, y, **kwargs):
        self.move_calls.append((x, y, kwargs))
        self.user32.cursor = (x, y)


class VirtualDesktopAdapterTests(unittest.TestCase):
    def test_dpi_incompatível_bloqueia_inicio_do_script(self):
        import megasena.virtual_desktop as desktop_view

        user32 = SimpleNamespace(
            SetProcessDpiAwarenessContext=FakeWindowsFunction(lambda _target: False),
            GetThreadDpiAwarenessContext=FakeWindowsFunction(lambda: 123),
            AreDpiAwarenessContextsEqual=FakeWindowsFunction(lambda _a, _b: False),
        )
        with patch.object(desktop_view, "_user32", return_value=user32):
            with self.assertRaisesRegex(CoordinateAutomationError, "DPI"):
                desktop_view.enable_per_monitor_dpi()

    def test_captura_com_dpi_incompativel_falha_antes_de_qualquer_clique(self):
        import megasena.virtual_desktop as desktop_view

        user32 = FakeUser32(bounds=(0, 0, 4800, 1350))
        gui = FakePyAutoGUI(user32, screenshot_size=(3840, 1080))
        with patch.object(desktop_view, "_user32", return_value=user32):
            with self.assertRaisesRegex(CoordinateAutomationError, "Escalas incompatíveis"):
                VirtualDesktopGUI(gui)
        self.assertEqual(gui.screenshot_calls, [{"allScreens": True}])
        self.assertEqual(user32.set_cursor_calls, [])
        self.assertEqual(user32.mouse_events, [])

    def test_clique_no_monitor_direito_usa_cursor_global_e_eventos_sem_absoluto(self):
        import megasena.virtual_desktop as desktop_view

        user32 = FakeUser32(bounds=(0, 0, 4800, 1350))
        gui = FakePyAutoGUI(user32, screenshot_size=(4800, 1350))
        with patch.object(desktop_view, "_user32", return_value=user32):
            adapter = VirtualDesktopGUI(gui)
        adapter.click(3505, 593)
        self.assertEqual(user32.set_cursor_calls, [(3505, 593)])
        self.assertEqual(gui.move_calls, [(3505, 593, {"duration": 0.3})])
        self.assertEqual([event[0] for event in user32.mouse_events], [
            MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
        ])
        self.assertTrue(all(event[1:3] == (0, 0) for event in user32.mouse_events))
        self.assertEqual(gui.click_calls, [])

    def test_mudanca_de_layout_entre_calibracao_e_clique_bloqueia_o_mouse(self):
        import megasena.virtual_desktop as desktop_view

        user32 = FakeUser32(bounds=(0, 0, 4800, 1350))
        gui = FakePyAutoGUI(user32, screenshot_size=(4800, 1350))
        with patch.object(desktop_view, "_user32", return_value=user32):
            adapter = VirtualDesktopGUI(gui)
        user32.bounds[2] = 3840
        with self.assertRaises(CoordinateAutomationError):
            adapter.click(3505, 593)
        self.assertEqual(user32.set_cursor_calls, [])
        self.assertEqual(user32.mouse_events, [])

    def test_ativar_navegador_no_ponto_nao_clica_na_pagina(self):
        import megasena.virtual_desktop as desktop_view

        user32 = FakeUser32()
        user32.foreground_window = 99
        gui = FakePyAutoGUI(user32, screenshot_size=(4800, 1350))
        with patch.object(desktop_view, "_user32", return_value=user32):
            adapter = VirtualDesktopGUI(gui)
        with patch.object(desktop_view.time, "sleep", return_value=None):
            adapter.activate_window_at(3350, 299)
        self.assertEqual(user32.window_points, [(3350, 299)])
        self.assertEqual(user32.foreground_calls, [100])
        self.assertEqual(adapter.browser_hwnd, 100)
        self.assertEqual(user32.set_cursor_calls, [])
        self.assertEqual(user32.mouse_events, [])
        self.assertEqual(gui.click_calls, [])

    def test_ponto_coberto_por_outra_janela_bloqueia_sem_clique(self):
        import megasena.virtual_desktop as desktop_view

        user32 = FakeUser32()
        gui = FakePyAutoGUI(user32, screenshot_size=(4800, 1350))
        with patch.object(desktop_view, "_user32", return_value=user32):
            adapter = VirtualDesktopGUI(gui)
        adapter.activate_window_at(3350, 299)
        user32.window_root = 200
        with self.assertRaisesRegex(CoordinateAutomationError, "Outra janela"):
            adapter.activate_window_at(3350, 299)
        self.assertEqual(user32.set_cursor_calls, [])
        self.assertEqual(user32.mouse_events, [])

    def test_recorte_e_pixel_com_origem_negativa_traduzem_para_imagem_local(self):
        image = FakePixelImage((3840, 1200))
        capture = VirtualScreenshot(image, screen_origin=(-1920, -200))
        self.assertEqual(capture.getpixel((-1900, -180)), (12, 34, 56))
        self.assertEqual(image.pixels_read, [(20, 20)])
        self.assertEqual(capture.crop((-1900, -180, -1870, -150)), (20, 20, 50, 50))
        self.assertEqual(image.crops, [(20, 20, 50, 50)])
        with self.assertRaises(CoordinateAutomationError):
            capture.getpixel((-1921, -180))


class DesktopCalibrationFlowTests(unittest.TestCase):
    def test_calibracao_com_pontos_do_usuario_aceita_monitor_secundario_e_preve_60(self):
        class Gui:
            screen_origin = (1920, 0)

            def __init__(self):
                self.moves = []
                self.prompt_count = 0

            def prompt(self, *_args, **_kwargs):
                self.prompt_count += 1
                return "22"

            def size(self):
                return (2240, 1350)

            def screenshot(self):
                return SimpleNamespace(size=(2240, 1350), screen_origin=self.screen_origin)

            def moveTo(self, x, y, **_kwargs):
                self.moves.append((x, y))

            def confirm(self, *_args, **_kwargs):
                return "Usar"

            def alert(self, message, **_kwargs):
                raise AssertionError(f"Calibração válida foi rejeitada: {message}")

        gui = Gui()
        points = (
            (2570, 411), (3875, 409), (2573, 594), (3505, 593),
            (3494, 686),
        )
        with (
            patch.object(desktop, "_capture_point", side_effect=points) as capture,
            patch.object(desktop.time, "sleep", return_value=None),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            calibration, clear_point = desktop._calibrate(gui)
        self.assertEqual(gui.prompt_count, 1)
        self.assertIn("60 (última dezena da última linha)", [call.args[1] for call in capture.call_args_list])
        self.assertEqual(number_center(calibration, 60), (3505, 593))
        self.assertIn((3505, 593), gui.moves)
        self.assertEqual(clear_point, points[4])
        self.assertFalse(any("Colocar no Carrinho" in call.args[1] for call in capture.call_args_list))


class FakeGUI:
    def __init__(self, screen_size=(1920, 1080), screen_origin=(0, 0)):
        self.screen_size = screen_size
        self.screen_origin = screen_origin
        self.clicks = []

    def size(self):
        return self.screen_size

    def click(self, x, y):
        self.clicks.append((x, y))


class FakeScreenshot:
    """Desenha círculos e dezenas suficientes para exercitar a leitura de pixels."""

    def __init__(self, calibration, selected=()):
        self.calibration = calibration
        self.selected = set(selected)
        self.size = calibration.screen_size
        self.screen_origin = calibration.screen_origin
        self.centers = [number_center(calibration, n) for n in range(1, 61)]

    def getpixel(self, point):
        x, y = point
        for number, (cx, cy) in enumerate(self.centers, 1):
            dx, dy = x - cx, y - cy
            radius = math.hypot(dx, dy)
            if radius <= 22:
                if abs(dx) <= 8 and abs(dy) <= 8:
                    return (90, 90, 90)
                if number in self.selected:
                    return (0, 166, 80)
                if radius >= 20:
                    return (170, 170, 170)
                return (255, 255, 255)
        return (255, 255, 255)

    def crop(self, box):
        parent = self

        class Crop:
            width = box[2] - box[0]
            height = box[3] - box[1]
            size = (width, height)

            def convert(self, mode):
                assert mode == "RGB"
                return self

            def getdata(self):
                return (
                    parent.getpixel((x, y))
                    for y in range(box[1], box[3])
                    for x in range(box[0], box[2])
                )

        return Crop()


class FakeScreenshotWithDarkTopLeft(FakeScreenshot):
    """Simula um algarismo que cobre os antigos pixels amostrados da dezena 26."""

    def getpixel(self, point):
        x, y = point
        cx, cy = self.centers[25]
        if -13 <= x - cx <= -8 and -13 <= y - cy <= -8:
            return (55, 55, 55)
        return super().getpixel(point)


class ScreenshotGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.calibration = calibrate_grid(
            (62, 156), (1106, 156), (62, 302), 22, (1920, 1080)
        )

    def test_le_exatamente_as_dezenas_verdes_sem_pillow_real(self):
        ticket = (9, 21, 26, 39, 48, 56)
        image = FakeScreenshot(self.calibration, ticket)
        self.assertEqual(selected_numbers(image, self.calibration), ticket)
        self.assertEqual(selected_numbers(FakeScreenshot(self.calibration), self.calibration), ())

    def test_detecta_26_verde_quando_algarismo_cobre_antiga_amostra_superior_esquerda(self):
        ticket = (9, 21, 26)
        image = FakeScreenshotWithDarkTopLeft(self.calibration, ticket)
        cx, cy = number_center(self.calibration, 26)
        self.assertEqual(image.getpixel((cx - 10, cy - 10)), (55, 55, 55))
        self.assertEqual(selected_numbers(image, self.calibration), ticket)

    def test_nao_confunde_circulo_branco_com_verde_quando_algarismo_e_escuro(self):
        image = FakeScreenshotWithDarkTopLeft(self.calibration)
        self.assertEqual(selected_numbers(image, self.calibration), ())

    def test_detecta_refluxo_de_22_para_17_colunas_na_mesma_resolucao(self):
        before = FakeScreenshot(self.calibration)
        signature = layout_signature(before, self.calibration)
        self.assertTrue(layout_matches(FakeScreenshot(self.calibration), self.calibration, signature))
        reflowed = calibrate_grid(
            (62, 156), (1054, 156), (62, 429), 17, (1920, 1080)
        )
        self.assertFalse(layout_matches(FakeScreenshot(reflowed), self.calibration, signature))

    def test_le_verde_da_captura_virtual_em_monitor_a_direita(self):
        calibration = calibrate_grid(
            (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
            screen_origin=(1920, 0), last_last=(3505, 593),
        )
        ticket = (9, 21, 26, 39, 48, 60)
        image = FakeScreenshot(calibration, selected=ticket)
        self.assertEqual(selected_numbers(image, calibration), ticket)
        signature = layout_signature(FakeScreenshot(calibration), calibration)
        self.assertTrue(layout_matches(FakeScreenshot(calibration), calibration, signature))

    def test_extrai_apostas_recentes_e_total_sem_confundir_concurso(self):
        page_text = """Apostas recentes
Números selecionados
01 02 03 04 05 06
Concurso: 3074
Valor: R$ 6,00
Números selecionados
09 21 26 39 48 56
Concurso: 3074
Valor: R$ 6,00
Total da aposta: R$ 12,00
"""
        self.assertEqual(
            recent_tickets(page_text),
            [(1, 2, 3, 4, 5, 6), (9, 21, 26, 39, 48, 56)],
        )
        self.assertEqual(page_total(page_text), Decimal("12.00"))


class PageTextGuardrailTests(unittest.TestCase):
    PAGE = """Preencha sua aposta
Concurso: 3074
Quantidade de números da aposta ?
6
Teimosinhas ?
0
Valor da Aposta: R$ 6,00
Apostas recentes
Números selecionados
09 21 26 39 48 56
Concurso: 3074
Valor: R$ 6,00
Total da aposta: R$ 6,00
"""

    def test_conferencias_do_volante_aceitam_aposta_simples(self):
        self.assertTrue(page_controls_ok(self.PAGE))

    def test_conferencias_rejeitam_quantidade_teimosinha_preco_ou_pagina_errados(self):
        changed_pages = (
            self.PAGE.replace("Preencha sua aposta", "Outra loteria"),
            self.PAGE.replace("aposta ?\n6", "aposta ?\n7"),
            self.PAGE.replace("Teimosinhas ?\n0", "Teimosinhas ?\n1"),
            self.PAGE.replace("Valor da Aposta: R$ 6,00", "Valor da Aposta: R$ 42,00"),
        )
        for page_text in changed_pages:
            with self.subTest(page_text=page_text):
                self.assertFalse(page_controls_ok(page_text))

    def test_controles_com_botoes_mais_e_menos_copiados_sao_reconhecidos(self):
        page_text = self.PAGE.replace("aposta ?\n6", "aposta ?\n-\n6\n+")
        page_text = page_text.replace("Teimosinhas ?\n0", "Teimosinhas ?\n-\n0\n+")
        self.assertTrue(page_controls_ok(page_text))
        compact_text = self.PAGE.replace("aposta ?\n6", "aposta ?\n-6+")
        compact_text = compact_text.replace("Teimosinhas ?\n0", "Teimosinhas ?\n-0+")
        self.assertTrue(page_controls_ok(compact_text))

    def test_controles_aceitam_espacos_e_quebras_copiados_do_firefox(self):
        page_text = self.PAGE.replace("Preencha sua aposta", "Preencha\r\nsua aposta")
        page_text = page_text.replace("aposta ?\n6", "aposta ?\r\n−\r\n6\r\n+")
        page_text = page_text.replace("Teimosinhas ?\n0", "Teimosinhas ?\r\n−\r\n0\r\n+")
        page_text = page_text.replace("R$ 6,00", "R$\u00a06,00")
        self.assertTrue(page_controls_ok(page_text))

    def test_url_na_area_de_transferencia_nao_passa_por_volante(self):
        address = "https://www.loteriasonline.caixa.gov.br/silce-web/#/mega-sena"
        self.assertFalse(page_controls_ok(address))

    def test_concurso_atual_ignora_cartao_antigo_e_ambiguidade(self):
        self.assertEqual(current_contest_from_page(self.PAGE), "3074")
        old_card = self.PAGE.replace("Concurso: 3074\nValor:", "Concurso: 3073\nValor:")
        self.assertEqual(current_contest_from_page(old_card), "3074")
        only_old_card = self.PAGE.replace("Concurso: 3074\n", "", 1)
        self.assertIsNone(current_contest_from_page(only_old_card))
        contradictory = self.PAGE.replace(
            "Concurso: 3074", "Concurso: 3074\nConcurso: 3075", 1
        )
        self.assertIsNone(current_contest_from_page(contradictory))

    def test_cartoes_recentes_exigem_seis_dezenas_concurso_e_preco(self):
        self.assertEqual(
            recent_cards(self.PAGE)[0].numbers,
            (9, 21, 26, 39, 48, 56),
        )
        self.assertEqual(recent_cards(self.PAGE)[0].contest, "3074")
        self.assertEqual(recent_cards(self.PAGE)[0].price, Decimal("6.00"))
        for damaged in (
            self.PAGE.replace("Concurso: 3074", "Concurso: "),
            self.PAGE.replace("Valor: R$ 6,00", "Valor: R$ "),
            self.PAGE.replace("09 21 26 39 48 56", "09 21 26 39 48 48"),
        ):
            with self.subTest(damaged=damaged):
                self.assertEqual(recent_cards(damaged), [])


class ProgressTests(unittest.TestCase):
    TICKETS_FILE = Path(__file__).resolve().parents[1] / "assets" / "carteira-25-2026-09-25.json"

    def setUp(self):
        from megasena.cart_automation import validate_tickets

        self.tickets = validate_tickets(self.TICKETS_FILE)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.progress_path = Path(self.temporary.name) / "progresso.json"
        patcher = patch.object(desktop, "PROGRESS_FILE", self.progress_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_progresso_pendente_bloqueia_reexecucao_automatica(self):
        progress = desktop._new_progress(self.tickets)
        progress["pendente"] = 1
        desktop._save_progress(progress)
        with self.assertRaises(CoordinateAutomationError):
            desktop._load_progress(self.tickets, new_cart=False)

    def test_progresso_carteira_diferente_ou_fora_de_ordem_e_rejeitado(self):
        progress = desktop._new_progress(self.tickets)
        progress["carteira"] = "outra carteira"
        desktop._save_progress(progress)
        with self.assertRaises(CoordinateAutomationError):
            desktop._load_progress(self.tickets, new_cart=False)
        progress = desktop._new_progress(self.tickets)
        progress["confirmados"] = [2]
        desktop._save_progress(progress)
        with self.assertRaises(CoordinateAutomationError):
            desktop._load_progress(self.tickets, new_cart=False)

    def test_arquivo_ilegivel_e_rejeitado(self):
        self.progress_path.write_text("{json truncado", encoding="utf-8")
        with self.assertRaises(CoordinateAutomationError):
            desktop._load_progress(self.tickets, new_cart=False)

    def test_novo_carrinho_reinicia_estado_local(self):
        progress = desktop._new_progress(self.tickets)
        progress["pendente"] = 1
        desktop._save_progress(progress)
        self.assertEqual(desktop._load_progress(self.tickets, new_cart=True), desktop._new_progress(self.tickets))


class FakeCartGUI(FakeGUI):
    """Volante falso: só os cliques e os círculos verdes confirmam o estado."""

    def __init__(self, calibration, clear_point, add_point, *, retain_after_add=False):
        super().__init__(calibration.screen_size)
        self.calibration = calibration
        self.clear_point = clear_point
        self.add_point = add_point
        self.retain_after_add = retain_after_add
        self.selected = []
        self.additions = []
        self.position_calls = 0
        self.moves = []
        self.number_by_point = {number_center(calibration, n): n for n in range(1, 61)}

    def alert(self, *_args, **_kwargs):
        return None

    def position(self):
        self.position_calls += 1
        assert len(self.selected) == 6, "O botão deve ser capturado depois de selecionar as seis dezenas"
        return self.add_point

    def moveTo(self, x, y, **_kwargs):
        self.moves.append((x, y))

    def confirm(self, *_args, **_kwargs):
        return "Usar"

    def hotkey(self, *_keys):
        raise AssertionError("O fluxo por coordenadas não deve consultar a barra de endereço")

    def press(self, _key):
        raise AssertionError("O fluxo por coordenadas não deve consultar o teclado")

    def click(self, x, y):
        super().click(x, y)
        point = (x, y)
        if point == self.clear_point:
            self.selected.clear()
        elif point == self.add_point:
            assert len(self.selected) == 6
            self.additions.append(tuple(sorted(self.selected)))
            if not self.retain_after_add:
                self.selected.clear()
        elif point in self.number_by_point:
            self.selected.append(self.number_by_point[point])

    def screenshot(self):
        return FakeScreenshot(self.calibration, self.selected)


class RunnerProgressTests(unittest.TestCase):
    TICKETS_FILE = ProgressTests.TICKETS_FILE

    def setUp(self):
        ProgressTests.setUp(self)
        self.calibration = calibrate_grid(
            (62, 156), (1106, 156), (62, 302), 22, (1920, 1080)
        )
        self.clear_point = (790, 380)
        self.add_point = (1060, 692)

    def _run_fake(self, gui, *, new_cart, through_game=25):
        clock = itertools.count()
        with (
            patch.object(desktop, "_calibrate", return_value=(
                self.calibration, self.clear_point,
            )),
            patch.object(desktop.time, "monotonic", side_effect=lambda: next(clock)),
            patch.object(desktop.time, "sleep", return_value=None),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            desktop._run(gui, self.tickets, new_cart=new_cart, through_game=through_game)

    def test_25_jogos_uma_vez_cada_sem_consultar_url_ou_texto(self):
        gui = FakeCartGUI(self.calibration, self.clear_point, self.add_point)
        self._run_fake(gui, new_cart=True)
        self.assertEqual(gui.additions, self.tickets)
        self.assertEqual(gui.clicks.count(self.add_point), 25)
        saved = json.loads(self.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["confirmados"], list(range(1, 26)))
        self.assertIsNone(saved["pendente"])

    def test_retomada_com_um_jogo_confirmado_comeca_no_segundo(self):
        progress = desktop._new_progress(self.tickets)
        progress["confirmados"] = [1]
        desktop._save_progress(progress)
        gui = FakeCartGUI(self.calibration, self.clear_point, self.add_point)
        self._run_fake(gui, new_cart=False)
        self.assertEqual(gui.additions, self.tickets[1:])
        self.assertEqual(gui.clicks.count(self.add_point), 24)

    def test_ensaio_so_primeiro_jogo_persiste_e_retomada_completa(self):
        first_session = FakeCartGUI(self.calibration, self.clear_point, self.add_point)
        self._run_fake(first_session, new_cart=True, through_game=1)
        self.assertEqual(first_session.additions, [self.tickets[0]])
        saved = json.loads(self.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["confirmados"], [1])
        self.assertIsNone(saved["pendente"])

        second_session = FakeCartGUI(self.calibration, self.clear_point, self.add_point)
        self._run_fake(second_session, new_cart=False)
        self.assertEqual(second_session.additions, self.tickets[1:])
        saved = json.loads(self.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["confirmados"], list(range(1, 26)))

    def test_captura_botao_ativo_depois_das_seis_dezenas_e_reutiliza(self):
        # O botão pode mudar de lugar quando o site ativa a aposta. O ponto
        # antigo da tela vazia não deve ser usado para enviar o jogo.
        moved_add_point = (1000, 720)
        gui = FakeCartGUI(self.calibration, self.clear_point, moved_add_point)
        with patch.object(desktop, "_capture_point", wraps=desktop._capture_point) as capture:
            self._run_fake(gui, new_cart=True, through_game=2)
        self.assertEqual(gui.additions, self.tickets[:2])
        self.assertEqual(gui.clicks.count(moved_add_point), 2)
        self.assertNotIn(self.add_point, gui.clicks)
        self.assertEqual(gui.position_calls, 1)
        self.assertEqual(capture.call_count, 1)
        self.assertIn("Colocar no Carrinho", capture.call_args.args[1])
        self.assertIn(moved_add_point, gui.moves)

    def test_clique_sem_reset_visual_fica_pendente_e_bloqueia_retentativa(self):
        gui = FakeCartGUI(
            self.calibration, self.clear_point, self.add_point, retain_after_add=True,
        )
        with self.assertRaises(CoordinateAutomationError):
            self._run_fake(gui, new_cart=True, through_game=1)
        self.assertEqual(gui.clicks.count(self.add_point), 1)
        saved = json.loads(self.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["confirmados"], [])
        self.assertEqual(saved["pendente"], 1)
        with self.assertRaises(CoordinateAutomationError):
            self._run_fake(gui, new_cart=False, through_game=1)
        self.assertEqual(gui.clicks.count(self.add_point), 1)

    def test_erro_visual_na_primeira_dezena_para_antes_da_segunda(self):
        class InaccurateScreenshotGUI(FakeCartGUI):
            def screenshot(self):
                return FakeScreenshot(self.calibration)

        gui = InaccurateScreenshotGUI(self.calibration, self.clear_point, self.add_point)
        with self.assertRaises(CoordinateAutomationError):
            self._run_fake(gui, new_cart=True, through_game=1)
        self.assertIn(number_center(self.calibration, self.tickets[0][0]), gui.clicks)
        self.assertNotIn(number_center(self.calibration, self.tickets[0][1]), gui.clicks)
        self.assertNotIn(self.add_point, gui.clicks)
        self.assertEqual(gui.additions, [])

class FillAndSubmitTests(unittest.TestCase):
    TICKET = (9, 21, 26, 39, 48, 56)
    CLEAR = (790, 380)
    ADD = (1060, 692)

    def setUp(self):
        self.gui = FakeGUI()
        self.calibration = calibrate_grid(
            (62, 156), (1106, 156), (62, 302), 22, (1920, 1080)
        )

    def _run(self, verify_callback, *, ticket=None, clear_point=None,
             add_point=None, before_click=None, click_delay=1.0):
        with patch("time.sleep", return_value=None) as sleeper:
            result = fill_and_submit(
                self.gui,
                self.calibration,
                ticket if ticket is not None else self.TICKET,
                clear_point if clear_point is not None else self.CLEAR,
                add_point if add_point is not None else self.ADD,
                verify_callback,
                before_click=before_click,
                click_delay=click_delay,
            )
        self.sleep_calls = sleeper.call_args_list
        return result

    def test_clica_limpar_seis_dezenas_e_adicionar_na_ordem(self):
        phases = []

        def verify(phase, ticket):
            phases.append((phase, ticket, len(self.gui.clicks)))
            return True

        self._run(verify)
        self.assertEqual(
            phases,
            [
                ("cleared", self.TICKET, 1),
                *[
                    ("number", self.TICKET[:index], index + 1)
                    for index in range(1, 7)
                ],
                ("selected", self.TICKET, 7),
                ("added", self.TICKET, 8),
            ],
        )
        self.assertEqual(len(self.gui.clicks), 8)
        self.assertEqual(self.gui.clicks[0], self.CLEAR)
        self.assertEqual(self.gui.clicks[-1], self.ADD)
        for actual, number in zip(self.gui.clicks[1:7], self.TICKET):
            with self.subTest(number=number):
                expected = number_center(self.calibration, number)
                self.assertAlmostEqual(actual[0], expected[0], delta=1)
                self.assertAlmostEqual(actual[1], expected[1], delta=1)

    def test_falha_ao_conferir_limpeza_nao_clica_em_dezenas(self):
        phases = []

        def verify(phase, ticket):
            phases.append(phase)
            return False

        with self.assertRaises(CoordinateAutomationError):
            self._run(verify)
        self.assertEqual(phases, ["cleared"])
        self.assertEqual(self.gui.clicks, [self.CLEAR])

    def test_falha_na_selecao_nunca_adiciona_ao_carrinho(self):
        phases = []

        def verify(phase, ticket):
            phases.append(phase)
            return phase != "selected"

        with self.assertRaises(CoordinateAutomationError):
            self._run(verify)
        self.assertEqual(phases, ["cleared", *(["number"] * 6), "selected"])
        self.assertEqual(len(self.gui.clicks), 7)
        self.assertNotIn(self.ADD, self.gui.clicks)

    def test_pausa_entre_cliques_nao_permite_sequencia_instantanea(self):
        self._run(lambda *_: True)
        # Seis pausas obrigatórias após as dezenas; nenhuma deve ser curta.
        delays = [call.args[0] for call in self.sleep_calls]
        self.assertGreaterEqual(len(delays), 6)
        self.assertTrue(all(delay >= 0.7 for delay in delays))

    def test_guardia_confere_cada_destino_imediatamente_antes_do_clique(self):
        checked = []

        def before_click(phase, number, point):
            checked.append((phase, number, point, len(self.gui.clicks)))

        self._run(lambda *_: True, before_click=before_click)
        self.assertEqual(len(checked), 8)
        self.assertEqual(checked[0], ("clear", None, self.CLEAR, 0))
        for index, number in enumerate(self.TICKET, 1):
            self.assertEqual(
                checked[index],
                ("number", number, number_center(self.calibration, number), index),
            )
        self.assertEqual(checked[-1], ("add", None, self.ADD, 7))

    def test_destino_de_adicionar_e_resolvido_so_apos_seis_dezenas(self):
        moved_add_point = (1000, 720)
        phases = []
        resolved_at = []
        checked_add = []

        def verify(phase, _ticket):
            phases.append(phase)
            return True

        def resolve_add():
            resolved_at.append((len(self.gui.clicks), phases[-1]))
            return moved_add_point

        def before_click(phase, _number, point):
            if phase == "add":
                checked_add.append(point)

        self._run(verify, add_point=resolve_add, before_click=before_click)
        self.assertEqual(resolved_at, [(7, "selected")])
        self.assertEqual(checked_add, [moved_add_point])
        self.assertEqual(self.gui.clicks[-1], moved_add_point)
        self.assertNotIn(self.ADD, self.gui.clicks)

    def test_destino_dinamico_fora_da_tela_nao_clica_em_adicionar(self):
        with self.assertRaises(CoordinateAutomationError):
            self._run(lambda *_: True, add_point=lambda: (2500, 692))
        self.assertEqual(len(self.gui.clicks), 7)
        self.assertNotIn((2500, 692), self.gui.clicks)

    def test_endereco_mudou_antes_da_segunda_dezena_nao_clica_mais(self):
        def before_click(phase, number, point):
            if phase == "number" and number == self.TICKET[1]:
                raise CoordinateAutomationError("A aba navegou para outra página")

        with self.assertRaisesRegex(CoordinateAutomationError, "outra página"):
            self._run(lambda *_: True, before_click=before_click)
        self.assertEqual(
            self.gui.clicks,
            [self.CLEAR, number_center(self.calibration, self.TICKET[0])],
        )
        self.assertNotIn(self.ADD, self.gui.clicks)

    def test_desvio_na_primeira_dezena_interrompe_imediatamente(self):
        phases = []

        def verify(phase, numbers):
            phases.append((phase, numbers))
            return phase != "number"

        with self.assertRaises(CoordinateAutomationError):
            self._run(verify)
        self.assertEqual(
            self.gui.clicks,
            [self.CLEAR, number_center(self.calibration, self.TICKET[0])],
        )
        self.assertEqual(phases[-1], ("number", (self.TICKET[0],)))
        self.assertNotIn(self.ADD, self.gui.clicks)

    def test_falha_apos_terceira_dezena_interrompe_antes_das_demais(self):
        phases = []

        def verify(phase, numbers):
            phases.append((phase, numbers))
            return not (phase == "number" and len(numbers) == 3)

        with self.assertRaises(CoordinateAutomationError):
            self._run(verify)
        self.assertEqual(self.gui.clicks, [
            self.CLEAR,
            *[number_center(self.calibration, n) for n in self.TICKET[:3]],
        ])
        self.assertEqual(phases[-1], ("number", self.TICKET[:3]))
        self.assertNotIn(self.ADD, self.gui.clicks)

    def test_resposta_ambigua_apos_adicionar_nao_repete_o_clique(self):
        phases = []

        def verify(phase, ticket):
            phases.append(phase)
            return phase != "added"

        with self.assertRaises(CoordinateAutomationError):
            self._run(verify)
        self.assertEqual(phases, ["cleared", *(["number"] * 6), "selected", "added"])
        self.assertEqual(self.gui.clicks.count(self.ADD), 1)

    def test_rejeita_jogo_invalido_antes_de_qualquer_clique(self):
        invalid = (9, 21, 26, 39, 48, 48)
        with self.assertRaises(CoordinateAutomationError):
            self._run(lambda *_: True, ticket=invalid)
        self.assertEqual(self.gui.clicks, [])

    def test_rejeita_botao_fora_da_tela_antes_de_qualquer_clique(self):
        with self.assertRaises(CoordinateAutomationError):
            self._run(lambda *_: True, add_point=(2500, 692))
        self.assertEqual(self.gui.clicks, [])

    def test_rejeita_resolucao_alterada_antes_de_qualquer_clique(self):
        self.gui.screen_size = (1366, 768)
        with self.assertRaises((ValueError, CoordinateAutomationError)):
            self._run(lambda *_: True)
        self.assertEqual(self.gui.clicks, [])

    def test_clica_dezena_60_na_tela_secundaria(self):
        calibration = calibrate_grid(
            (2570, 411), (3875, 409), (2573, 594), 22, (2240, 1350),
            screen_origin=(1920, 0), last_last=(3505, 593),
        )
        gui = FakeGUI(calibration.screen_size, screen_origin=calibration.screen_origin)
        ticket = (15, 26, 28, 44, 58, 60)
        with patch("time.sleep", return_value=None):
            fill_and_submit(
                gui, calibration, ticket, (3494, 686), (3830, 1078),
                lambda *_: True,
            )
        self.assertEqual(gui.clicks[-2], (3505, 593))
        self.assertEqual(gui.clicks[-1], (3830, 1078))


if __name__ == "__main__":
    unittest.main()

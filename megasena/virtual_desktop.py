"""Coordenadas globais do desktop Windows para a automação do volante.

PyAutoGUI informa o tamanho apenas do monitor principal. Esta camada usa o
retângulo virtual do Windows e captura todos os monitores, sem presumir que o
monitor do navegador comece em (0, 0).
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Any

from megasena.pyautogui_cart import CoordinateAutomationError


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_SWAPBUTTON = 23
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4


def _user32():
    if sys.platform != "win32":
        raise CoordinateAutomationError("A automação por coordenadas exige Windows.")
    return ctypes.WinDLL("user32", use_last_error=True)


def enable_per_monitor_dpi() -> None:
    """Define DPI V2 antes de importar PyAutoGUI ou capturar a tela.

    O PyAutoGUI chama ``SetProcessDPIAware`` ao importar. Se isso ocorrer antes,
    o processo pode receber coordenadas do mouse e pixels da captura em escalas
    diferentes. A configuração aqui deve ser a primeira operação de UI.
    """
    user32 = _user32()
    set_awareness = user32.SetProcessDpiAwarenessContext
    set_awareness.argtypes = [ctypes.c_void_p]
    set_awareness.restype = ctypes.c_bool
    target = ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    if set_awareness(target):
        return

    # Uma configuração idêntica já aplicada também é válida; Windows não
    # permite chamar SetProcessDpiAwarenessContext duas vezes no processo.
    current_context = user32.GetThreadDpiAwarenessContext
    current_context.argtypes = []
    current_context.restype = ctypes.c_void_p
    equal = user32.AreDpiAwarenessContextsEqual
    equal.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    equal.restype = ctypes.c_bool
    if equal(current_context(), target):
        return
    raise CoordinateAutomationError(
        "O Windows não permitiu configurar DPI por monitor. Feche esta execução "
        "e abra o script novamente; não é seguro clicar com escalas diferentes."
    )


class VirtualScreenshot:
    """Imagem PIL que recebe pontos e recortes em coordenadas globais."""

    def __init__(self, image: Any, screen_origin: tuple[int, int]):
        self._image = image
        self.screen_origin = tuple(screen_origin)
        self.size = image.size

    def _local(self, point: tuple[int, int]) -> tuple[int, int]:
        return (point[0] - self.screen_origin[0], point[1] - self.screen_origin[1])

    def getpixel(self, point: tuple[int, int]):
        local_x, local_y = self._local(point)
        if not (0 <= local_x < self.size[0] and 0 <= local_y < self.size[1]):
            raise CoordinateAutomationError("Leitura de pixel fora do desktop virtual.")
        return self._image.getpixel((local_x, local_y))

    def crop(self, box: tuple[int, int, int, int]):
        left, top = self._local((box[0], box[1]))
        right, bottom = self._local((box[2], box[3]))
        if not (0 <= left < right <= self.size[0] and 0 <= top < bottom <= self.size[1]):
            raise CoordinateAutomationError("Recorte fora do desktop virtual.")
        return self._image.crop((left, top, right, bottom))


class VirtualDesktopGUI:
    """Adapta PyAutoGUI para o desktop virtual Windows com cliques seguros."""

    def __init__(self, pyautogui_module: Any):
        self._gui = pyautogui_module
        self._user32 = _user32()
        self._configure_mouse_api()
        self._configure_window_api()
        self.screen_bounds = self._read_bounds()
        self.screen_origin = self.screen_bounds[:2]
        self.click_count = 0
        self.browser_hwnd = None
        # Falha antes da calibração se o Windows e Pillow discordarem da escala.
        self.screenshot()

    def _configure_mouse_api(self) -> None:
        set_cursor = self._user32.SetCursorPos
        set_cursor.argtypes = [ctypes.c_int, ctypes.c_int]
        set_cursor.restype = ctypes.c_bool
        mouse_event = self._user32.mouse_event
        mouse_event.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_size_t]
        mouse_event.restype = None
        metrics = self._user32.GetSystemMetrics
        metrics.argtypes = [ctypes.c_int]
        metrics.restype = ctypes.c_int

    def _configure_window_api(self) -> None:
        point_window = self._user32.WindowFromPoint
        point_window.argtypes = [wintypes.POINT]
        point_window.restype = wintypes.HWND
        ancestor = self._user32.GetAncestor
        ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
        ancestor.restype = wintypes.HWND
        class_name = self._user32.GetClassNameW
        class_name.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        class_name.restype = ctypes.c_int
        foreground = self._user32.GetForegroundWindow
        foreground.argtypes = []
        foreground.restype = wintypes.HWND
        activate = self._user32.SetForegroundWindow
        activate.argtypes = [wintypes.HWND]
        activate.restype = ctypes.c_bool

    def activate_window_at(self, x: int, y: int) -> None:
        """Ativa o navegador sob o ponto calibrado sem clicar na página."""
        self._check_layout()
        self._check_point(x, y)
        child = self._user32.WindowFromPoint(wintypes.POINT(x, y))
        root = self._user32.GetAncestor(child, 2) if child else None
        if not root:
            raise CoordinateAutomationError("Não encontrei o navegador no ponto de foco.")
        buffer = ctypes.create_unicode_buffer(256)
        if not self._user32.GetClassNameW(root, buffer, len(buffer)):
            raise CoordinateAutomationError("Não foi possível identificar a janela do navegador.")
        if buffer.value not in ("Chrome_WidgetWin_1", "MozillaWindowClass"):
            raise CoordinateAutomationError(
                "O ponto de foco não está sobre Chrome, Edge ou Firefox. Confira o navegador."
            )
        if self.browser_hwnd is None:
            self.browser_hwnd = root
        elif root != self.browser_hwnd:
            raise CoordinateAutomationError(
                "Outra janela cobre o ponto calibrado ou o navegador mudou. Execução interrompida."
            )
        if self._user32.GetForegroundWindow() != root:
            self._user32.SetForegroundWindow(root)
            time.sleep(0.2)
            if self._user32.GetForegroundWindow() != root:
                raise CoordinateAutomationError(
                    "Não consegui ativar o navegador. Clique nele manualmente e execute novamente."
                )

    def _read_bounds(self) -> tuple[int, int, int, int]:
        metrics = self._user32.GetSystemMetrics
        left = metrics(SM_XVIRTUALSCREEN)
        top = metrics(SM_YVIRTUALSCREEN)
        width = metrics(SM_CXVIRTUALSCREEN)
        height = metrics(SM_CYVIRTUALSCREEN)
        if width <= 0 or height <= 0:
            raise CoordinateAutomationError("O Windows informou dimensões inválidas para o desktop.")
        return (left, top, width, height)

    def _check_layout(self) -> None:
        if self._read_bounds() != self.screen_bounds:
            raise CoordinateAutomationError(
                "A disposição ou resolução dos monitores mudou. Calibre novamente."
            )

    def _check_point(self, x: int, y: int) -> None:
        if type(x) is not int or type(y) is not int:
            raise CoordinateAutomationError("Coordenadas do mouse devem ser números inteiros.")
        left, top, width, height = self.screen_bounds
        if not (left <= x < left + width and top <= y < top + height):
            raise CoordinateAutomationError("Clique fora do desktop virtual.")

    def size(self) -> tuple[int, int]:
        self._check_layout()
        return self.screen_bounds[2:]

    def screenshot(self) -> VirtualScreenshot:
        self._check_layout()
        try:
            image = self._gui.screenshot(allScreens=True)
        except TypeError as exc:
            raise CoordinateAutomationError(
                "Esta versão do PyAutoGUI não captura todos os monitores."
            ) from exc
        expected = self.screen_bounds[2:]
        if tuple(image.size) != expected:
            raise CoordinateAutomationError(
                f"Escalas incompatíveis entre mouse e captura: desktop {expected[0]}x{expected[1]}, "
                f"imagem {image.size[0]}x{image.size[1]}. Reinicie o script."
            )
        return VirtualScreenshot(image, self.screen_origin)

    def moveTo(self, x: int, y: int, **kwargs: Any) -> None:
        self._check_layout()
        self._check_point(x, y)
        self._gui.failSafeCheck()
        self._gui.moveTo(x, y, **kwargs)
        if tuple(self._gui.position()) != (x, y):
            raise CoordinateAutomationError("O mouse não alcançou o ponto calibrado.")

    def click(self, x: int, y: int) -> None:
        self._check_layout()
        self._check_point(x, y)
        self._gui.failSafeCheck()
        self.moveTo(x, y, duration=0.3)
        if not self._user32.SetCursorPos(x, y):
            raise CoordinateAutomationError("O Windows não moveu o mouse até o ponto calibrado.")
        if tuple(self._gui.position()) != (x, y):
            raise CoordinateAutomationError("O mouse não alcançou o ponto calibrado.")
        self._gui.failSafeCheck()
        if self._user32.GetSystemMetrics(SM_SWAPBUTTON):
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        # Sem MOUSEEVENTF_MOVE/ABSOLUTE, dx=dy=0: o clique ocorre na posição
        # definida por SetCursorPos, inclusive no monitor secundário.
        self.click_count += 1
        self._user32.mouse_event(down, 0, 0, 0, 0)
        try:
            time.sleep(0.08)
        finally:
            self._user32.mouse_event(up, 0, 0, 0, 0)
        pause = getattr(self._gui, "PAUSE", 0)
        if pause:
            self._gui.sleep(pause)

    def __getattr__(self, name: str):
        return getattr(self._gui, name)

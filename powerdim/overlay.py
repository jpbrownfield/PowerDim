"""Per-monitor click-through dimming overlay window.

At alpha > 0 the window is a topmost, click-through, layered black rectangle
covering one monitor. At 100% brightness it is fully hidden (ShowWindow SW_HIDE)
rather than merely made transparent, so it drops out of DWM's occlusion/flip
eligibility checks and does not block hardware-independent flip.
"""
import ctypes

from .monitors import MonitorRect
from .win32defs import (
    GW_HWNDPREV,
    HWND_TOPMOST,
    LWA_ALPHA,
    SW_HIDE,
    SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    WNDCLASSW,
    WNDPROC,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    BLACK_BRUSH,
    gdi32,
    kernel32,
    user32,
)

_CLASS_NAME = "PowerDimOverlayWindowClass"
_class_registered = False


def _ensure_class_registered() -> None:
    global _class_registered
    if _class_registered:
        return
    hinstance = kernel32.GetModuleHandleW(None)
    # DefWindowProcW alone is enough: it paints the class background brush
    # (solid black) on WM_ERASEBKGND/WM_PAINT, so no custom paint code is needed.
    wndproc = ctypes.cast(user32.DefWindowProcW, WNDPROC)
    wc = WNDCLASSW()
    wc.style = 0
    wc.lpfnWndProc = wndproc
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = hinstance
    wc.hIcon = None
    wc.hCursor = None
    wc.hbrBackground = gdi32.GetStockObject(BLACK_BRUSH)
    wc.lpszMenuName = None
    wc.lpszClassName = _CLASS_NAME
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())
    _class_registered = True


class OverlayWindow:
    """A single monitor's dimming overlay."""

    def __init__(self, rect: MonitorRect):
        _ensure_class_registered()
        hinstance = kernel32.GetModuleHandleW(None)
        exstyle = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_NOACTIVATE
            | WS_EX_TOOLWINDOW
            | WS_EX_TOPMOST
        )
        self.hwnd = user32.CreateWindowExW(
            exstyle,
            _CLASS_NAME,
            "PowerDim",
            WS_POPUP,
            rect.left,
            rect.top,
            rect.width,
            rect.height,
            None,
            None,
            hinstance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.device_name = rect.device_name
        self._visible = False

    def set_alpha(self, alpha: int) -> None:
        """Set overlay opacity (0-255). Does not change visibility."""
        user32.SetLayeredWindowAttributes(self.hwnd, 0, max(0, min(255, alpha)), LWA_ALPHA)

    def show(self) -> None:
        """Make the overlay visible and topmost. Call set_alpha() first to avoid a flash."""
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        )
        self._visible = True

    def hide(self) -> None:
        """Fully hide the overlay so it drops out of DWM occlusion/flip checks."""
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self._visible = False

    def is_topmost_most(self) -> bool:
        """True if nothing sits above us in z-order (GW_HWNDPREV is null)."""
        return not user32.GetWindow(self.hwnd, GW_HWNDPREV)

    def assert_topmost(self) -> bool:
        """Re-assert topmost z-order, but only if something has actually displaced us.

        Skipping the SetWindowPos call when we're already on top prevents a
        mutual reassertion loop (flicker) with other topmost windows that
        also react to z-order/foreground events -- an unconditional
        reassert would fight them every time either side moves, even when
        nothing is actually wrong. Returns True only when a correction was
        actually performed, so callers can detect a fight (repeated True in
        quick succession) and switch to a windowless dimming mode instead.
        """
        if not self._visible or self.is_topmost_most():
            return False
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
        return True

    def destroy(self) -> None:
        user32.DestroyWindow(self.hwnd)

"""Hidden message-only window that owns global hotkeys and the app message loop."""
import ctypes
from dataclasses import dataclass
from typing import Callable

from .win32defs import (
    HWND_MESSAGE,
    MOD_NOREPEAT,
    WM_DESTROY,
    WM_HOTKEY,
    WM_TIMER,
    WNDCLASSW,
    WNDPROC,
    WS_POPUP,
    kernel32,
    user32,
)

_CLASS_NAME = "PowerDimControllerWindowClass"


@dataclass(frozen=True)
class HotkeySpec:
    id: int
    modifiers: int
    vk: int


class ControllerWindow:
    """Hidden window used purely as a message sink for hotkeys and WinEvent hooks."""

    def __init__(self, on_hotkey: Callable[[int], None]):
        self._on_hotkey = on_hotkey
        self._on_timer: Callable[[int], None] | None = None
        self._wndproc = WNDPROC(self._wnd_proc)
        hinstance = kernel32.GetModuleHandleW(None)

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = _CLASS_NAME
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())

        self.hwnd = user32.CreateWindowExW(
            0,
            _CLASS_NAME,
            "PowerDimController",
            WS_POPUP,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            hinstance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    def register_hotkey(self, spec: HotkeySpec) -> None:
        if not user32.RegisterHotKey(self.hwnd, spec.id, spec.modifiers | MOD_NOREPEAT, spec.vk):
            raise ctypes.WinError(ctypes.get_last_error())

    def unregister_hotkey(self, hotkey_id: int) -> None:
        user32.UnregisterHotKey(self.hwnd, hotkey_id)

    def set_timer_handler(self, on_timer: Callable[[int], None]) -> None:
        self._on_timer = on_timer

    def start_timer(self, timer_id: int, interval_ms: int) -> None:
        user32.SetTimer(self.hwnd, timer_id, interval_ms, None)

    def stop_timer(self, timer_id: int) -> None:
        user32.KillTimer(self.hwnd, timer_id)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY:
            self._on_hotkey(int(wparam))
            return 0
        if msg == WM_TIMER:
            if self._on_timer:
                self._on_timer(int(wparam))
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def destroy(self) -> None:
        user32.DestroyWindow(self.hwnd)


def run_message_loop() -> None:
    from ctypes import wintypes

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

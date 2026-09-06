"""Event-driven foreground/window-show hook.

This only tells the app *when to check* z-order (on EVENT_SYSTEM_FOREGROUND /
EVENT_OBJECT_SHOW) instead of polling on a timer. It does not by itself
prevent flicker: the caller must still verify it has actually been displaced
before reasserting topmost (see OverlayWindow.assert_topmost), otherwise an
unconditional reassert can ping-pong against any other window that reacts to
z-order changes the same way.
"""
import ctypes
from typing import Callable

from .win32defs import (
    EVENT_OBJECT_SHOW,
    EVENT_SYSTEM_FOREGROUND,
    WINEVENT_OUTOFCONTEXT,
    WINEVENT_SKIPOWNPROCESS,
    WINEVENTPROC,
    user32,
)


class ForegroundHook:
    def __init__(self, on_change: Callable[[], None]):
        self._on_change = on_change
        # Keep a reference so the ctypes callback isn't garbage collected.
        self._callback = WINEVENTPROC(self._raw_callback)
        self._hook_foreground = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            self._callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        self._hook_show = user32.SetWinEventHook(
            EVENT_OBJECT_SHOW,
            EVENT_OBJECT_SHOW,
            None,
            self._callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )

    def _raw_callback(self, _hook, _event, _hwnd, _id_object, _id_child, _thread, _time):
        self._on_change()

    def close(self) -> None:
        if self._hook_foreground:
            user32.UnhookWinEvent(self._hook_foreground)
            self._hook_foreground = None
        if self._hook_show:
            user32.UnhookWinEvent(self._hook_show)
            self._hook_show = None

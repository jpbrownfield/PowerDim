"""Physical monitor enumeration."""
import ctypes
from dataclasses import dataclass

from . import display_config
from .win32defs import MONITORENUMPROC, MONITORINFOEXW, user32


@dataclass(frozen=True)
class MonitorRect:
    left: int
    top: int
    right: int
    bottom: int
    device_name: str = ""
    friendly_name: str = ""
    is_probably_oled: bool = False

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def get_monitor_rects() -> list[MonitorRect]:
    """Enumerate all active monitors and return their full (non-clipped) rects."""
    rects: list[MonitorRect] = []

    def _callback(hmonitor, _hdc, _rect_ptr, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            device_name = info.szDevice
            friendly = display_config.get_friendly_name(device_name) or device_name
            rects.append(
                MonitorRect(
                    r.left,
                    r.top,
                    r.right,
                    r.bottom,
                    device_name,
                    friendly,
                    display_config.is_probably_oled(friendly),
                )
            )
        return True

    callback = MONITORENUMPROC(_callback)
    user32.EnumDisplayMonitors(None, None, callback, 0)
    return rects


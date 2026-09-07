"""Shared DisplayConfig helpers: active-path enumeration, GDI-device-name to
target lookup, and friendly monitor names. Used by hdr.py (HDR/SDR-white-level
control) and monitors.py (friendly names for the tray's per-monitor menu).
"""
import ctypes
from ctypes import wintypes

from .win32defs import (
    DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME,
    DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME,
    DISPLAYCONFIG_PATH_INFO,
    DISPLAYCONFIG_SOURCE_DEVICE_NAME,
    DISPLAYCONFIG_TARGET_DEVICE_NAME,
    QDC_ONLY_ACTIVE_PATHS,
    _DISPLAYCONFIG_MODE_INFO_SCRATCH,
    user32,
)

ERROR_SUCCESS = 0


def query_active_paths() -> list:
    num_paths = wintypes.UINT(0)
    num_modes = wintypes.UINT(0)
    if user32.GetDisplayConfigBufferSizes(
        QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_paths), ctypes.byref(num_modes)
    ):
        return []
    paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
    modes = (_DISPLAYCONFIG_MODE_INFO_SCRATCH * num_modes.value)()
    result = user32.QueryDisplayConfig(
        QDC_ONLY_ACTIVE_PATHS,
        ctypes.byref(num_paths),
        paths,
        ctypes.byref(num_modes),
        modes,
        None,
    )
    if result != ERROR_SUCCESS:
        return []
    return list(paths)[: num_paths.value]


def find_target_for_device(device_name: str):
    """Return the (adapterId, targetId) DisplayConfig path target matching a GDI device name."""
    for path in query_active_paths():
        info = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
        info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
        info.header.size = ctypes.sizeof(info)
        info.header.adapterId = path.sourceInfo.adapterId
        info.header.id = path.sourceInfo.id
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) != ERROR_SUCCESS:
            continue
        if info.viewGdiDeviceName.upper() == device_name.upper():
            return path.targetInfo.adapterId, path.targetInfo.id
    return None


def get_friendly_name(device_name: str) -> str | None:
    """Best-effort human-readable monitor name (e.g. "Dell U2720Q") pulled from
    EDID via DisplayConfig. Returns None if unavailable (virtual/RDP displays,
    generic drivers, etc.) -- callers should fall back to the GDI device name."""
    target = find_target_for_device(device_name)
    if target is None:
        return None
    adapter_id, target_id = target
    info = DISPLAYCONFIG_TARGET_DEVICE_NAME()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
    info.header.size = ctypes.sizeof(info)
    info.header.adapterId = adapter_id
    info.header.id = target_id
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) != ERROR_SUCCESS:
        return None
    name = info.monitorFriendlyDeviceName.strip()
    return name or None


def is_probably_oled(friendly_name: str | None) -> bool:
    """Heuristic only: Windows has no public API to query panel technology, so
    this just checks whether the monitor's EDID-reported name mentions OLED.
    Many real OLED monitors don't include it, so a False here is not conclusive."""
    return bool(friendly_name) and "oled" in friendly_name.lower()

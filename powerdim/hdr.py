"""HDR-aware dimming support via the DisplayConfig API.

Gamma ramps (gdi32 SetDeviceGammaRamp) only affect the legacy SDR 8-bit LUT
stage and are largely bypassed by the HDR color pipeline, so on an
HDR-enabled output we instead scale the "SDR content brightness" (SDR white
level) -- the same value Windows' own Settings > Display > HDR page controls
with its slider. Like gamma, this has no window and cannot interfere with
z-order/hardware flip.

Reading advanced-color state and the current SDR white level uses the public,
documented DisplayConfigGetDeviceInfo API. Writing the SDR white level uses an
info type that Microsoft has never published in official documentation --
it's reverse-engineered from Windows' own Settings app and used by community
tools (e.g. "HDR Tray"). It is not guaranteed to work on every driver/Windows
build, so every call here fails closed (returns False/None) and callers must
fall back to another dimming mode rather than assume success.
"""
import ctypes

from .win32defs import (
    DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL,
    DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME,
    DISPLAYCONFIG_DEVICE_INFO_SET_SDR_WHITE_LEVEL,
    DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_PATH_INFO,
    DISPLAYCONFIG_SDR_WHITE_LEVEL,
    DISPLAYCONFIG_SOURCE_DEVICE_NAME,
    QDC_ONLY_ACTIVE_PATHS,
    _DISPLAYCONFIG_MODE_INFO_SCRATCH,
    user32,
)
from ctypes import wintypes

ERROR_SUCCESS = 0
# SDRWhiteLevel is scaled such that 1000 == 80 nits (the SDR reference white).
_SDR_WHITE_LEVEL_RAW_PER_NIT = 1000 / 80
_MIN_SDR_WHITE_LEVEL_RAW = 40  # avoid driving the value to (near) zero


def _query_active_paths() -> list:
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


def _find_target_for_device(device_name: str):
    """Return the (adapterId, targetId) DisplayConfig path target matching a GDI device name."""
    for path in _query_active_paths():
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


def is_hdr_enabled(device_name: str) -> bool:
    target = _find_target_for_device(device_name)
    if target is None:
        return False
    adapter_id, target_id = target
    info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
    info.header.size = ctypes.sizeof(info)
    info.header.adapterId = adapter_id
    info.header.id = target_id
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) != ERROR_SUCCESS:
        return False
    return info.advanced_color_enabled


def get_sdr_white_level_raw(device_name: str) -> int | None:
    target = _find_target_for_device(device_name)
    if target is None:
        return None
    adapter_id, target_id = target
    info = DISPLAYCONFIG_SDR_WHITE_LEVEL()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL
    info.header.size = ctypes.sizeof(info)
    info.header.adapterId = adapter_id
    info.header.id = target_id
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) != ERROR_SUCCESS:
        return None
    return info.SDRWhiteLevel


def set_sdr_white_level_raw(device_name: str, raw_value: int) -> bool:
    target = _find_target_for_device(device_name)
    if target is None:
        return False
    adapter_id, target_id = target
    info = DISPLAYCONFIG_SDR_WHITE_LEVEL()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_SET_SDR_WHITE_LEVEL
    info.header.size = ctypes.sizeof(info)
    info.header.adapterId = adapter_id
    info.header.id = target_id
    info.SDRWhiteLevel = max(_MIN_SDR_WHITE_LEVEL_RAW, int(raw_value))
    return user32.DisplayConfigSetDeviceInfo(ctypes.byref(info.header)) == ERROR_SUCCESS


def scale_white_level_raw(baseline_raw: int, factor: float) -> int:
    factor = max(0.0, min(1.0, factor))
    return max(_MIN_SDR_WHITE_LEVEL_RAW, round(baseline_raw * factor))

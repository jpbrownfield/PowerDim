"""Per-monitor dimming backend that never creates a window.

Chooses gamma-ramp dimming (gamma.py) for SDR outputs, or SDR-white-level
dimming (hdr.py) for HDR-enabled outputs, since gamma ramps are unreliable
under HDR. Either path is immune to topmost/z-order fights and cannot block
hardware-independent flip, because neither one involves a window at all.
"""
from . import hdr
from .gamma import GammaChannel


class MonitorGammaDimmer:
    def __init__(self, device_name: str):
        self.device_name = device_name
        self.is_hdr = hdr.is_hdr_enabled(device_name)
        self._gamma: GammaChannel | None = None
        self._sdr_baseline_raw: int | None = None
        if self.is_hdr:
            self._sdr_baseline_raw = hdr.get_sdr_white_level_raw(device_name)
        else:
            self._gamma = GammaChannel(device_name)

    def set_brightness(self, brightness_percent: int) -> bool:
        if self.is_hdr:
            if self._sdr_baseline_raw is None:
                return False
            target = hdr.scale_white_level_raw(self._sdr_baseline_raw, brightness_percent / 100.0)
            return hdr.set_sdr_white_level_raw(self.device_name, target)
        return self._gamma.set_brightness(brightness_percent)

    def poll_external_change(self) -> bool:
        """Detect another app overwriting our dim curve and re-absorb it. SDR-only:
        there is no cheap change notification for SDR white level to poll."""
        if self.is_hdr or self._gamma is None:
            return False
        return self._gamma.resync_if_externally_changed()

    def restore(self) -> None:
        if self.is_hdr:
            if self._sdr_baseline_raw is not None:
                hdr.set_sdr_white_level_raw(self.device_name, self._sdr_baseline_raw)
        elif self._gamma is not None:
            self._gamma.restore()

    def close(self) -> None:
        self.restore()
        if self._gamma is not None:
            self._gamma.close()


def build_monitor_dimmers(device_names: list) -> list:
    """Build one MonitorGammaDimmer per device, skipping any that fail to initialize
    (e.g. a monitor without a controllable gamma ramp) rather than crashing the app."""
    dimmers = []
    for name in device_names:
        try:
            dimmers.append(MonitorGammaDimmer(name))
        except OSError:
            continue
    return dimmers

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
        self._sdr_last_known_raw: int | None = None
        self._sdr_last_write_ok = False
        self._current_brightness_percent = 100
        if self.is_hdr:
            self._sdr_baseline_raw = hdr.get_sdr_white_level_raw(device_name)
            self._sdr_last_known_raw = self._sdr_baseline_raw
        else:
            self._gamma = GammaChannel(device_name)

    def set_brightness(self, brightness_percent: int) -> bool:
        if self.is_hdr:
            if self._sdr_baseline_raw is None:
                self._sdr_last_write_ok = False
                return False
            target = hdr.scale_white_level_raw(self._sdr_baseline_raw, brightness_percent / 100.0)
            previous = self._sdr_last_known_raw
            if not hdr.set_sdr_white_level_raw(self.device_name, target):
                self._sdr_last_write_ok = False
                return False
            actual = hdr.get_sdr_white_level_raw(self.device_name)
            if actual is None:
                self._sdr_last_write_ok = False
                return False
            # Drivers round SDRWhiteLevel to their own step size, so don't demand
            # an exact match to our target -- only reject a write that left the
            # value completely unchanged despite asking for a real change (that's
            # the "reports success but silently no-ops" bug this replaced).
            if actual == previous and target != previous:
                self._sdr_last_write_ok = False
                return False
            self._sdr_last_known_raw = actual
            self._current_brightness_percent = brightness_percent
            self._sdr_last_write_ok = True
            return True
        ok = self._gamma.set_brightness(brightness_percent)
        if ok:
            self._current_brightness_percent = brightness_percent
        return ok

    def set_shadow_lift(self, percent: float) -> bool:
        """VRR black-flicker shadow lift: only meaningful on the gamma-ramp path --
        SDR white level is a single scalar with no per-level LUT to lift shadows in."""
        if self.is_hdr or self._gamma is None:
            return False
        return self._gamma.set_shadow_lift(percent)

    def verify_applied(self) -> bool:
        """Confirm the last set_brightness() call actually changed the physical
        output, not just that the Win32 call reported success. Both paths now read
        back and compare (see set_brightness's own readback check for HDR, and
        GammaChannel.readback_matches_last_applied for SDR gamma ramp)."""
        if self.is_hdr:
            return self._sdr_last_write_ok
        if self._gamma is None:
            return True
        return self._gamma.readback_matches_last_applied()

    def poll_external_change(self) -> bool:
        """Detect another app (or the user, e.g. moving Windows' own "SDR content
        brightness" slider) overwriting our dim curve, and re-absorb it by treating
        the new value as the undimmed baseline and reapplying our current dim
        factor on top of it."""
        if self.is_hdr:
            if self._sdr_baseline_raw is None or self._sdr_last_known_raw is None:
                return False
            current = hdr.get_sdr_white_level_raw(self.device_name)
            if current is None or current == self._sdr_last_known_raw:
                return False
            self._sdr_baseline_raw = current
            return self.set_brightness(self._current_brightness_percent)
        if self._gamma is None:
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

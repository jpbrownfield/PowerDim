"""SDR gamma-ramp based dimming.

SetDeviceGammaRamp scales the display's 8-bit LUT directly at the driver level --
there is no window involved at all, so this dimming path can never occlude,
block hardware-independent flip, or fight anything for z-order/topmost.

To coexist with another application that also writes the gamma ramp (some games
implement their own in-game brightness slider this way), we never blindly stomp
on it: we track what we last wrote, and if a poll finds the ramp no longer
matches, we treat the new ramp as the app's baseline and re-apply our dim on top
of it rather than overwriting their curve outright.
"""
import ctypes

from . import gamma_recovery
from .win32defs import GAMMARAMP, gdi32

_STEPS = 256
_MAX_CHANNEL = 65535


def identity_ramp() -> GAMMARAMP:
    ramp = GAMMARAMP()
    for i in range(_STEPS):
        value = min(_MAX_CHANNEL, i * 257)
        ramp.Red[i] = ramp.Green[i] = ramp.Blue[i] = value
    return ramp


def scale_ramp(baseline: GAMMARAMP, factor: float) -> GAMMARAMP:
    """Multiply every channel entry by factor (0..1), preserving the baseline's curve shape."""
    factor = max(0.0, min(1.0, factor))
    out = GAMMARAMP()
    for i in range(_STEPS):
        out.Red[i] = int(baseline.Red[i] * factor)
        out.Green[i] = int(baseline.Green[i] * factor)
        out.Blue[i] = int(baseline.Blue[i] * factor)
    return out


def ramps_equal(a: GAMMARAMP, b: GAMMARAMP) -> bool:
    return list(a.Red) == list(b.Red) and list(a.Green) == list(b.Green) and list(a.Blue) == list(b.Blue)


def apply_shadow_lift(ramp: GAMMARAMP, lift_percent: float, falloff: float = 2.5) -> GAMMARAMP:
    """Raise the display's near-black output floor, fading to no effect by the
    midtones, to counteract OLED VRR black-flicker. Works independent of any
    brightness dimming already baked into `ramp` -- lift_percent is expressed as
    a percentage of the full 16-bit channel range and never lowers a value.
    """
    lift_percent = max(0.0, min(100.0, lift_percent))
    if lift_percent <= 0:
        return ramp
    lift_raw = lift_percent / 100.0 * _MAX_CHANNEL
    out = GAMMARAMP()
    for i in range(_STEPS):
        floor = lift_raw * ((1.0 - i / (_STEPS - 1)) ** falloff)
        out.Red[i] = min(_MAX_CHANNEL, max(ramp.Red[i], round(floor)))
        out.Green[i] = min(_MAX_CHANNEL, max(ramp.Green[i], round(floor)))
        out.Blue[i] = min(_MAX_CHANNEL, max(ramp.Blue[i], round(floor)))
    return out


class GammaChannel:
    """Owns a per-monitor device context and the gamma-ramp dim state for it."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.hdc = gdi32.CreateDCW(device_name, None, None, None)
        if not self.hdc:
            raise ctypes.WinError(ctypes.get_last_error())
        self._factor = 1.0
        self._shadow_lift_percent = 0.0
        self._last_applied: GAMMARAMP | None = None
        self._baseline = self._recover_or_capture_baseline()

    def _recover_or_capture_baseline(self) -> GAMMARAMP:
        """Self-heal from an unclean previous exit: if a prior run crashed while
        dimmed, its saved pre-dim ramp is still on disk and the display is still
        showing the dim it never got to undo. Restore that ramp now, then use it
        (rather than the still-dimmed current ramp) as our baseline."""
        leftover = gamma_recovery.load_leftover_baseline(self.device_name)
        if leftover is None:
            return self._read_ramp() or identity_ramp()
        recovered = GAMMARAMP()
        for i in range(256):
            recovered.Red[i] = leftover["red"][i]
            recovered.Green[i] = leftover["green"][i]
            recovered.Blue[i] = leftover["blue"][i]
        if gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(recovered)):
            gamma_recovery.clear_baseline(self.device_name)
        # else: leave the record in place -- a still-dimmed monitor must keep its
        # safety net until a restore actually succeeds (retried on the next launch
        # or via the "100% (Disabled)" tray brightness preset).
        return recovered

    def _read_ramp(self) -> GAMMARAMP | None:
        ramp = GAMMARAMP()
        if gdi32.GetDeviceGammaRamp(self.hdc, ctypes.byref(ramp)):
            return ramp
        return None

    def set_brightness(self, brightness_percent: int) -> bool:
        self._factor = max(0.0, min(1.0, brightness_percent / 100.0))
        dimmed = scale_ramp(self._baseline, self._factor)
        if self._shadow_lift_percent > 0:
            dimmed = apply_shadow_lift(dimmed, self._shadow_lift_percent)
        # Persist the pre-dim baseline before dimming, so a crash while dimmed is
        # still recoverable the next time PowerDim starts (see _recover_or_capture_baseline).
        if self._factor < 1.0 or self._shadow_lift_percent > 0:
            gamma_recovery.save_baseline(
                self.device_name, self._baseline.Red, self._baseline.Green, self._baseline.Blue
            )
        else:
            gamma_recovery.clear_baseline(self.device_name)
        if not gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(dimmed)):
            return False
        self._last_applied = dimmed
        return True

    def set_shadow_lift(self, percent: float) -> bool:
        """Set (or clear, at 0) the near-black lift and reapply at the current
        brightness factor."""
        self._shadow_lift_percent = max(0.0, min(100.0, percent))
        return self.set_brightness(round(self._factor * 100))

    def resync_if_externally_changed(self) -> bool:
        """Detect another app overwriting our ramp and re-apply our dim on its curve.

        Returns True if an external change was absorbed.
        """
        current = self._read_ramp()
        if current is None or self._last_applied is None or ramps_equal(current, self._last_applied):
            return False
        self._baseline = current
        self.set_brightness(round(self._factor * 100))
        return True

    def readback_matches_last_applied(self) -> bool:
        """Some WDDM drivers accept SetDeviceGammaRamp and report success without
        actually changing the physical output -- notably common over HDMI on TVs
        and displays whose scaler ignores the legacy gamma-ramp IOCTL entirely.
        Read the ramp back and compare it to what we last wrote to catch that
        silent no-op, rather than trusting the API's return value alone."""
        if self._last_applied is None:
            return True
        current = self._read_ramp()
        return current is not None and ramps_equal(current, self._last_applied)

    def restore(self) -> bool:
        """Reapply the pre-dim baseline. Only clears the crash-recovery record on
        success -- if the ramp write fails, the monitor may still be dimmed, so the
        safety net must stay in place for a later retry. Also clears any shadow
        lift, since this is the "fully back to normal" path."""
        self._shadow_lift_percent = 0.0
        ok = bool(gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(self._baseline)))
        if ok:
            gamma_recovery.clear_baseline(self.device_name)
        return ok

    def close(self) -> None:
        self.restore()
        if self.hdc:
            gdi32.DeleteDC(self.hdc)
            self.hdc = None

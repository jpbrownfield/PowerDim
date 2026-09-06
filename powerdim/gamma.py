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


class GammaChannel:
    """Owns a per-monitor device context and the gamma-ramp dim state for it."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.hdc = gdi32.CreateDCW(device_name, None, None, None)
        if not self.hdc:
            raise ctypes.WinError(ctypes.get_last_error())
        self._baseline = self._read_ramp() or identity_ramp()
        self._factor = 1.0
        self._last_applied: GAMMARAMP | None = None

    def _read_ramp(self) -> GAMMARAMP | None:
        ramp = GAMMARAMP()
        if gdi32.GetDeviceGammaRamp(self.hdc, ctypes.byref(ramp)):
            return ramp
        return None

    def set_brightness(self, brightness_percent: int) -> bool:
        self._factor = max(0.0, min(1.0, brightness_percent / 100.0))
        dimmed = scale_ramp(self._baseline, self._factor)
        if not gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(dimmed)):
            return False
        self._last_applied = dimmed
        return True

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

    def restore(self) -> None:
        gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(self._baseline))

    def close(self) -> None:
        self.restore()
        if self.hdc:
            gdi32.DeleteDC(self.hdc)
            self.hdc = None

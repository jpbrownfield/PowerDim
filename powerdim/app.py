"""Wires monitors, overlays, hotkeys, and the foreground hook into one dim state machine."""
from .controller_window import ControllerWindow, HotkeySpec
from .dimming import clamp, compute_alpha, is_full_brightness
from .flicker import FlickerDetector
from .foreground_hook import ForegroundHook
from .gamma_backend import build_monitor_dimmers
from .monitors import get_monitor_rects
from .overlay import OverlayWindow
from .win32defs import MOD_ALT, MOD_CONTROL, VK_DOWN, VK_HOME, VK_UP

HOTKEY_BRIGHTNESS_UP = 1
HOTKEY_BRIGHTNESS_DOWN = 2
HOTKEY_RESET = 3
BRIGHTNESS_STEP = 5

GAMMA_POLL_TIMER_ID = 1
GAMMA_POLL_INTERVAL_MS = 500


class PowerDimApp:
    def __init__(self):
        self.brightness = 100
        monitor_rects = get_monitor_rects()
        self.overlays = [OverlayWindow(rect) for rect in monitor_rects]
        self._monitor_device_names = [rect.device_name for rect in monitor_rects]
        self._gamma_dimmers = None  # built lazily only if we ever need to fall back
        self._use_gamma = False
        self._flicker = FlickerDetector()
        self.controller = ControllerWindow(on_hotkey=self._on_hotkey)
        self.controller.register_hotkey(
            HotkeySpec(HOTKEY_BRIGHTNESS_UP, MOD_CONTROL | MOD_ALT, VK_UP)
        )
        self.controller.register_hotkey(
            HotkeySpec(HOTKEY_BRIGHTNESS_DOWN, MOD_CONTROL | MOD_ALT, VK_DOWN)
        )
        self.controller.register_hotkey(HotkeySpec(HOTKEY_RESET, MOD_CONTROL | MOD_ALT, VK_HOME))
        self.controller.set_timer_handler(self._on_timer)
        self.hook = ForegroundHook(on_change=self._reassert_topmost)

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == HOTKEY_BRIGHTNESS_UP:
            self.set_brightness(self.brightness + BRIGHTNESS_STEP)
        elif hotkey_id == HOTKEY_BRIGHTNESS_DOWN:
            self.set_brightness(self.brightness - BRIGHTNESS_STEP)
        elif hotkey_id == HOTKEY_RESET:
            self.set_brightness(100)

    def _on_timer(self, timer_id: int) -> None:
        if timer_id == GAMMA_POLL_TIMER_ID and self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                dimmer.poll_external_change()

    def set_brightness(self, value: int) -> None:
        self.brightness = clamp(value, 0, 100)
        if is_full_brightness(self.brightness):
            for overlay in self.overlays:
                overlay.hide()
            if self._gamma_dimmers:
                for dimmer in self._gamma_dimmers:
                    dimmer.restore()
            # A full-brightness cycle is a natural recovery point: retry the
            # overlay next time in case the offending app has since closed.
            self._use_gamma = False
            self._flicker.reset()
            self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
            return
        if self._use_gamma:
            self._ensure_gamma_dimmers()
            for dimmer in self._gamma_dimmers:
                dimmer.set_brightness(self.brightness)
            return
        alpha = compute_alpha(self.brightness)
        for overlay in self.overlays:
            # Set alpha before showing to avoid a flash of stale opacity.
            overlay.set_alpha(alpha)
            overlay.show()

    def _ensure_gamma_dimmers(self) -> None:
        if self._gamma_dimmers is None:
            self._gamma_dimmers = build_monitor_dimmers(self._monitor_device_names)
        self.controller.start_timer(GAMMA_POLL_TIMER_ID, GAMMA_POLL_INTERVAL_MS)

    def _reassert_topmost(self) -> None:
        if is_full_brightness(self.brightness) or self._use_gamma:
            return
        for overlay in self.overlays:
            if overlay.assert_topmost() and self._flicker.record_correction():
                self._switch_to_gamma()
                return

    def _switch_to_gamma(self) -> None:
        """Another topmost window is fighting us for z-order (flicker). Fall back to
        windowless gamma/SDR-white-level dimming, which can't be displaced in z-order
        at all -- but only commit to it if every monitor actually accepts the ramp
        (e.g. some virtual/RDP displays and some drivers reject it outright). Silently
        losing all dimming would be worse than keeping the occasional overlay flicker.
        """
        self._ensure_gamma_dimmers()
        results = [dimmer.set_brightness(self.brightness) for dimmer in self._gamma_dimmers]
        if not self._gamma_dimmers or not all(results):
            # Partial success is worse than no dimming inconsistency between monitors --
            # revert any that did apply before falling back to the overlay entirely.
            for dimmer in self._gamma_dimmers:
                dimmer.restore()
            self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
            self._flicker.reset()
            return
        self._use_gamma = True
        for overlay in self.overlays:
            overlay.hide()

    def shutdown(self) -> None:
        self.hook.close()
        self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
        for overlay in self.overlays:
            overlay.destroy()
        if self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                dimmer.close()
        self.controller.destroy()


"""Wires monitors, overlays, hotkeys, and the foreground hook into one dim state machine."""
import logging
from datetime import datetime

from . import hotkeys as hotkeys_mod
from . import schedule as schedule_mod
from . import startup
from .controller_window import ControllerWindow, HotkeySpec
from .dimming import clamp, compute_alpha, is_full_brightness
from .flicker import FlickerDetector
from .foreground_hook import ForegroundHook
from .gamma_backend import build_monitor_dimmers
from .monitors import get_monitor_rects
from .overlay import OverlayWindow

logger = logging.getLogger(__name__)

BRIGHTNESS_STEP = 10

GAMMA_POLL_TIMER_ID = 1
GAMMA_POLL_INTERVAL_MS = 500
OVERLAY_RETRY_TIMER_ID = 2
SCHEDULE_POLL_TIMER_ID = 3
SCHEDULE_POLL_INTERVAL_MS = 30_000

# Brightness used to actually exercise the gamma-ramp pipeline when probing/
# verifying support (see _probe_gamma_support / _verify_gamma_available):
# distinct enough from 100% that a driver silently ignoring non-identity ramp
# writes will be caught by the post-write readback check, not just trusted
# because the Win32 call itself reported success.
_GAMMA_PROBE_BRIGHTNESS_PERCENT = 80

# "Use Gamma if Flickering is Detected for" setting: minutes to stay in gamma mode
# before automatically re-testing the overlay, plus two sentinels.
GAMMA_DURATION_NEVER = 0  # never auto-switch to gamma at all, even if flicker is detected
GAMMA_DURATION_INDEFINITE = -1  # switch to gamma and never auto-retry the overlay
GAMMA_DURATION_DEFAULT_MINUTES = 120
GAMMA_DURATION_CHOICES_MINUTES = [
    GAMMA_DURATION_NEVER,
    15,
    30,
    60,
    GAMMA_DURATION_DEFAULT_MINUTES,
    GAMMA_DURATION_INDEFINITE,
]

# Dedicated dimming-mode selection: "overlay" behaves as before (auto-falls back
# to gamma on detected flicker, per GAMMA_DURATION); "gamma" always dims via the
# windowless gamma/SDR-white-level path and never creates/shows an overlay at all,
# so the flicker-fallback setting is irrelevant and hidden in that mode.
DIMMING_MODE_OVERLAY = "overlay"
DIMMING_MODE_GAMMA = "gamma"

# "OLED VRR Black Flicker Tool" shadow-lift: percentage of the full 16-bit
# channel range to raise near-black output by (see gamma.apply_shadow_lift).
# Only ever applied via the gamma-ramp path (not HDR SDR-white-level). Exposed
# in the tray as an "Active" checkbox plus a separate "Configure..." intensity
# picker, so the configured intensity persists across toggling active on/off.
SHADOW_LIFT_INTENSITY_CHOICES_PERCENT = [15, 30, 50]
SHADOW_LIFT_DEFAULT_INTENSITY_PERCENT = 30


class PowerDimApp:
    def __init__(self):
        self.brightness = 100
        monitor_rects = get_monitor_rects()
        self.overlays = [OverlayWindow(rect) for rect in monitor_rects]
        self._monitor_device_names = [rect.device_name for rect in monitor_rects]
        self.monitor_friendly_names = {rect.device_name: rect.friendly_name for rect in monitor_rects}
        self.monitor_is_probably_oled = {
            rect.device_name: rect.is_probably_oled for rect in monitor_rects
        }
        self.monitor_enabled = {rect.device_name: True for rect in monitor_rects}
        self._gamma_dimmers = None  # built lazily only if we ever need to fall back
        self.monitor_gamma_supported, self.monitor_shadow_lift_supported = self._probe_gamma_support()
        self.shadow_lift_active = False
        self.shadow_lift_intensity_percent = SHADOW_LIFT_DEFAULT_INTENSITY_PERCENT
        self._use_gamma = False
        self._flicker = FlickerDetector()
        self.controller = ControllerWindow(on_hotkey=self._on_hotkey)
        self.hotkey_bindings = []
        self._hotkey_id_map = {}
        failed = self.set_hotkey_bindings(hotkeys_mod.load_bindings())
        for binding in failed:
            logger.warning("Failed to register hotkey (already in use?): %s", binding)
        self.controller.set_timer_handler(self._on_timer)
        self.hook = ForegroundHook(on_change=self._reassert_topmost)
        self._shut_down = False
        self.gamma_duration_minutes = GAMMA_DURATION_DEFAULT_MINUTES
        self.on_flicker_fallback = None  # callable(), notified only on an actual gamma switch
        self.on_gamma_unavailable = None  # callable(), notified if an explicit gamma switch fails
        self.schedule_entries = schedule_mod.load_entries()
        self.schedule_enabled = True
        self._last_scheduled_brightness = None
        self.controller.start_timer(SCHEDULE_POLL_TIMER_ID, SCHEDULE_POLL_INTERVAL_MS)
        self.dimming_mode = DIMMING_MODE_OVERLAY
        self.run_on_startup = startup.is_enabled()

    def _probe_gamma_support(self) -> tuple[dict, dict]:
        """One-time per-monitor check of whether the windowless dimming path actually
        works (some virtual/RDP displays and drivers reject SetDeviceGammaRamp
        outright) -- used to decide whether gamma-only tray features (Gamma Mode,
        the VRR Black Flicker Tool) should even be offered. Shadow lift is tracked
        separately since it additionally requires the gamma-ramp path specifically
        (not the HDR SDR-white-level scalar).

        Probes with an actually-reduced brightness (not 100%) and reads the ramp
        back afterward: a same-value roundtrip at 100% is a no-op that many WDDM
        drivers accept and report success on even when they silently ignore real
        (non-identity) ramp writes, which would otherwise make this probe always
        pass regardless of whether dimming can really happen."""
        gamma_supported = {name: False for name in self._monitor_device_names}
        shadow_lift_supported = {name: False for name in self._monitor_device_names}
        for dimmer in build_monitor_dimmers(self._monitor_device_names):
            ok = dimmer.set_brightness(_GAMMA_PROBE_BRIGHTNESS_PERCENT) and dimmer.verify_applied()
            gamma_supported[dimmer.device_name] = ok
            shadow_lift_supported[dimmer.device_name] = ok and not dimmer.is_hdr
            dimmer.close()  # restores the probed monitor back to its baseline
        return gamma_supported, shadow_lift_supported

    def set_monitor_enabled(self, device_name: str, enabled: bool) -> None:
        if self.monitor_enabled.get(device_name) == enabled:
            return
        self.monitor_enabled[device_name] = enabled
        if not enabled:
            for overlay in self.overlays:
                if overlay.device_name == device_name:
                    overlay.hide()
            if self._gamma_dimmers:
                for dimmer in self._gamma_dimmers:
                    if dimmer.device_name == device_name:
                        dimmer.restore()
            return
        # Re-enabled: reapply whatever dimming/shadow-lift state is currently active.
        self.set_brightness(self.brightness)
        if self.shadow_lift_active and self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                if dimmer.device_name == device_name:
                    dimmer.set_shadow_lift(self.shadow_lift_intensity_percent)

    def set_shadow_lift_active(self, active: bool) -> None:
        self.shadow_lift_active = active
        self._apply_shadow_lift(self.shadow_lift_intensity_percent if active else 0)

    def set_shadow_lift_intensity(self, percent: int) -> None:
        self.shadow_lift_intensity_percent = max(0, min(100, percent))
        if self.shadow_lift_active:
            self._apply_shadow_lift(self.shadow_lift_intensity_percent)

    def _apply_shadow_lift(self, percent: int) -> None:
        self._ensure_gamma_dimmers()
        for dimmer in self._gamma_dimmers:
            if self.monitor_enabled.get(dimmer.device_name, True):
                dimmer.set_shadow_lift(percent)

    def set_gamma_duration(self, minutes: int) -> None:
        self.gamma_duration_minutes = minutes

    def set_dimming_mode(self, mode: str) -> None:
        if mode == self.dimming_mode:
            return
        if mode == DIMMING_MODE_GAMMA and not self._verify_gamma_available():
            logger.info("Gamma dimming unavailable on this display, staying on overlay mode")
            if self.on_gamma_unavailable:
                self.on_gamma_unavailable()
            return
        logger.info("Dimming mode changed: %s -> %s", self.dimming_mode, mode)
        self.dimming_mode = mode
        self._flicker.reset()
        # A fresh explicit mode choice overrides any pending auto-fallback retry
        # timer from before the switch.
        self.controller.stop_timer(OVERLAY_RETRY_TIMER_ID)
        self._use_gamma = mode == DIMMING_MODE_GAMMA
        self.set_brightness(self.brightness)

    def set_hotkey_bindings(self, bindings: list) -> list:
        """Replace all hotkey bindings, persist them, and return the subset that
        failed to register (e.g. already claimed by another application) so the
        editor UI can warn about them; those are simply dropped rather than
        blocking the rest from taking effect."""
        for hotkey_id in list(self._hotkey_id_map):
            self.controller.unregister_hotkey(hotkey_id)
        registered = []
        failed = []
        id_map = {}
        for i, binding in enumerate(bindings, start=1):
            try:
                self.controller.register_hotkey(HotkeySpec(i, binding.modifiers, binding.vk))
            except OSError:
                failed.append(binding)
                continue
            id_map[i] = binding
            registered.append(binding)
        self._hotkey_id_map = id_map
        self.hotkey_bindings = registered
        hotkeys_mod.save_bindings(registered)
        return failed

    def _on_hotkey(self, hotkey_id: int) -> None:
        binding = self._hotkey_id_map.get(hotkey_id)
        if binding is None:
            return
        if binding.action == hotkeys_mod.ACTION_BRIGHTNESS_UP:
            self.set_brightness(self.brightness + BRIGHTNESS_STEP)
        elif binding.action == hotkeys_mod.ACTION_BRIGHTNESS_DOWN:
            self.set_brightness(self.brightness - BRIGHTNESS_STEP)
        elif binding.action == hotkeys_mod.ACTION_RESET:
            self.set_brightness(100)
        elif binding.action == hotkeys_mod.ACTION_SET_VALUE:
            self.set_brightness(hotkeys_mod.next_brightness_for_set_value(self.brightness, binding.value))

    def _on_timer(self, timer_id: int) -> None:
        if timer_id == GAMMA_POLL_TIMER_ID and self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                if self.monitor_enabled.get(dimmer.device_name, True):
                    dimmer.poll_external_change()
        elif timer_id == OVERLAY_RETRY_TIMER_ID:
            self._retry_overlay()
        elif timer_id == SCHEDULE_POLL_TIMER_ID:
            self._check_schedule()

    def _check_schedule(self) -> None:
        if not self.schedule_enabled:
            return
        target = schedule_mod.active_brightness(self.schedule_entries, datetime.now())
        # Only act on a transition to a *different* scheduled level, so manual
        # brightness changes in between scheduled times are never overridden.
        if target is not None and target != self._last_scheduled_brightness:
            self.set_brightness(target)
        self._last_scheduled_brightness = target

    def set_schedule_enabled(self, enabled: bool) -> None:
        self.schedule_enabled = enabled
        self._last_scheduled_brightness = None  # force re-apply on the next check

    def reload_schedule(self) -> None:
        """Pick up entries just written to disk (e.g. by the schedule editor UI)."""
        self.schedule_entries = schedule_mod.load_entries()
        self._last_scheduled_brightness = None

    def set_run_on_startup(self, enabled: bool) -> None:
        startup.set_enabled(enabled)
        self.run_on_startup = enabled

    def effective_dimming_mode_for_monitor(self, device_name: str) -> str:
        """Which mechanism actually drives this specific monitor right now --
        can differ from self.dimming_mode, since a monitor gamma can't control
        always falls back to the overlay even while Gamma Mode is selected."""
        gamma_mode_selected = self.dimming_mode == DIMMING_MODE_GAMMA or self._use_gamma
        if gamma_mode_selected and self.monitor_gamma_supported.get(device_name, False):
            return DIMMING_MODE_GAMMA
        return DIMMING_MODE_OVERLAY

    def set_brightness(self, value: int) -> None:
        self.brightness = clamp(value, 0, 100)
        logger.info(
            "Setting brightness to %d%% (mode=%s)",
            self.brightness,
            "gamma" if self._use_gamma else "overlay",
        )
        overlays_by_name = {overlay.device_name: overlay for overlay in self.overlays}
        if is_full_brightness(self.brightness):
            for overlay in self.overlays:
                if self.monitor_enabled.get(overlay.device_name, True):
                    overlay.hide()
            if self._gamma_dimmers:
                # Every monitor, including disabled ones, so 100% is always a
                # genuine "back to normal" regardless of per-monitor selection.
                # set_brightness(100) rather than restore() so an active shadow
                # lift is preserved -- that's only ever toggled from the VRR
                # Black Flicker Tool menu.
                for dimmer in self._gamma_dimmers:
                    dimmer.set_brightness(100)
            # A full-brightness cycle is a natural recovery point: retry the
            # overlay next time in case the offending app has since closed -- but
            # only in overlay mode; dedicated gamma mode never touches the overlay.
            if self.dimming_mode == DIMMING_MODE_OVERLAY:
                self._use_gamma = False
            self._flicker.reset()
            self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
            self.controller.stop_timer(OVERLAY_RETRY_TIMER_ID)
            return
        alpha = compute_alpha(self.brightness)
        if self.dimming_mode == DIMMING_MODE_GAMMA or self._use_gamma:
            self._ensure_gamma_dimmers()
            gamma_by_name = {dimmer.device_name: dimmer for dimmer in self._gamma_dimmers}
            for name in self._monitor_device_names:
                if not self.monitor_enabled.get(name, True):
                    continue
                overlay = overlays_by_name.get(name)
                if self.monitor_gamma_supported.get(name, False):
                    gamma_by_name[name].set_brightness(self.brightness)
                    if overlay is not None:
                        overlay.hide()
                elif overlay is not None:
                    # Fallback for a monitor gamma can't control, so nothing is
                    # ever left undimmed just because Gamma Mode was selected.
                    overlay.set_alpha(alpha)
                    overlay.show()
            return
        for overlay in self.overlays:
            if not self.monitor_enabled.get(overlay.device_name, True):
                continue
            # Set alpha before showing to avoid a flash of stale opacity.
            overlay.set_alpha(alpha)
            overlay.show()

    def _ensure_gamma_dimmers(self) -> None:
        if self._gamma_dimmers is None:
            self._gamma_dimmers = build_monitor_dimmers(self._monitor_device_names)
        self.controller.start_timer(GAMMA_POLL_TIMER_ID, GAMMA_POLL_INTERVAL_MS)

    def _verify_gamma_available(self) -> bool:
        """Actually attempt to apply a genuinely-reduced brightness via gamma on
        each monitor before committing to gamma dimming -- some virtual/RDP
        displays and drivers reject SetDeviceGammaRamp outright, and some accept
        it but silently ignore non-identity curves (see _probe_gamma_support), so
        testing at the current brightness alone would pass trivially whenever it
        happens to be 100%. Gamma Mode is allowed to activate as long as at least
        one enabled monitor actually works -- monitors that don't are reverted and
        simply left undimmed (see monitor_gamma_supported / the tray's "No Gamma
        Control" label), rather than blocking the whole mode.
        """
        self._ensure_gamma_dimmers()
        enabled_dimmers = [
            d for d in self._gamma_dimmers if self.monitor_enabled.get(d.device_name, True)
        ]
        if not enabled_dimmers:
            self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
            return False
        working = []
        for d in enabled_dimmers:
            ok = d.set_brightness(_GAMMA_PROBE_BRIGHTNESS_PERCENT) and d.verify_applied()
            # Keep the tray's per-monitor support state (and future set_brightness
            # calls) in sync with what this live check just found.
            self.monitor_gamma_supported[d.device_name] = ok
            if ok:
                working.append(d)
            else:
                d.restore()
        if not working:
            self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
            return False
        for d in working:
            d.set_brightness(self.brightness)
        return True

    def _reassert_topmost(self) -> None:
        # _use_gamma is permanently True in dedicated gamma mode, so this also
        # naturally skips all overlay/flicker handling in that mode.
        if is_full_brightness(self.brightness) or self._use_gamma:
            return
        if self.gamma_duration_minutes == GAMMA_DURATION_NEVER:
            for overlay in self.overlays:
                if self.monitor_enabled.get(overlay.device_name, True):
                    overlay.assert_topmost()
            return
        for overlay in self.overlays:
            if not self.monitor_enabled.get(overlay.device_name, True):
                continue
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
        logger.info("Flicker detected, switching to gamma dimming")
        if not self._verify_gamma_available():
            # Partial success is worse than dimming inconsistency between monitors --
            # _verify_gamma_available already reverted any that did apply.
            logger.info("Gamma switch rejected by one or more monitors, staying on overlay")
            self._flicker.reset()
            return
        self._use_gamma = True
        if self.gamma_duration_minutes != GAMMA_DURATION_INDEFINITE:
            self.controller.start_timer(
                OVERLAY_RETRY_TIMER_ID, self.gamma_duration_minutes * 60 * 1000
            )
        for overlay in self.overlays:
            if self.monitor_enabled.get(overlay.device_name, True):
                overlay.hide()
        if self.on_flicker_fallback:
            self.on_flicker_fallback()

    def _retry_overlay(self) -> None:
        """Periodically re-test whether the overlay can be used again (the app that
        was fighting us for topmost may have since closed). If it starts flickering
        again, _reassert_topmost's normal path falls back to gamma once more."""
        if self.dimming_mode == DIMMING_MODE_GAMMA:
            return  # dedicated gamma mode never retries the overlay
        if not self._use_gamma or is_full_brightness(self.brightness):
            return
        logger.info("Retrying overlay dimming after gamma fallback timeout")
        if self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                if self.monitor_enabled.get(dimmer.device_name, True):
                    # set_brightness(100) rather than restore() so an active
                    # shadow lift (independent of brightness) is preserved.
                    dimmer.set_brightness(100)
        self._use_gamma = False
        self._flicker.reset()
        alpha = compute_alpha(self.brightness)
        for overlay in self.overlays:
            if not self.monitor_enabled.get(overlay.device_name, True):
                continue
            overlay.set_alpha(alpha)
            overlay.show()

    def shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        self.hook.close()
        self.controller.stop_timer(GAMMA_POLL_TIMER_ID)
        self.controller.stop_timer(OVERLAY_RETRY_TIMER_ID)
        self.controller.stop_timer(SCHEDULE_POLL_TIMER_ID)
        for overlay in self.overlays:
            overlay.destroy()
        if self._gamma_dimmers:
            for dimmer in self._gamma_dimmers:
                dimmer.close()
        self.controller.destroy()


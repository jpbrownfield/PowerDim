"""System tray icon: brightness presets + exit, running on its own thread."""
import threading

from PIL import Image, ImageDraw
import pystray

from .app import (
    DIMMING_MODE_GAMMA,
    DIMMING_MODE_OVERLAY,
    GAMMA_DURATION_INDEFINITE,
    GAMMA_DURATION_NEVER,
    PowerDimApp,
)
from .schedule_editor import open_schedule_editor
from .shadow_lift_editor import open_shadow_lift_editor

_PRESETS = [100, 90, 80, 70, 60, 50, 40, 30, 20]

_DIMMING_MODE_LABELS = {
    DIMMING_MODE_OVERLAY: "Overlay Mode",
    DIMMING_MODE_GAMMA: "Gamma Mode",
}

_GAMMA_DURATION_LABELS = {
    GAMMA_DURATION_NEVER: "Never",
    15: "15 minutes",
    30: "30 minutes",
    60: "1 hour",
    120: "2 hours",
    GAMMA_DURATION_INDEFINITE: "Indefinitely",
}


def _make_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(20, 20, 20, 255), outline=(220, 220, 220, 255), width=3)
    return img


def build_tray_icon(app: PowerDimApp, on_exit) -> pystray.Icon:
    def make_set_brightness(value):
        def handler(icon, item):
            app.set_brightness(value)

        return handler

    def make_set_gamma_duration(minutes):
        def handler(icon, item):
            app.set_gamma_duration(minutes)

        return handler

    def make_set_dimming_mode(mode):
        def handler(icon, item):
            app.set_dimming_mode(mode)

        return handler

    def make_toggle_monitor(device_name):
        def handler(icon, item):
            app.set_monitor_enabled(device_name, not app.monitor_enabled.get(device_name, True))

        return handler

    def handle_toggle_shadow_lift_active(icon, item):
        app.set_shadow_lift_active(not app.shadow_lift_active)

    def handle_configure_shadow_lift(icon, item):
        threading.Thread(target=open_shadow_lift_editor, args=(app,), daemon=True).start()

    def handle_exit(icon, item):
        icon.stop()
        on_exit()

    def handle_reset_gamma(icon, item):
        app.force_reset_gamma()

    def handle_toggle_schedule(icon, item):
        app.set_schedule_enabled(not app.schedule_enabled)

    def handle_edit_schedule(icon, item):
        threading.Thread(target=open_schedule_editor, args=(app,), daemon=True).start()

    def handle_toggle_run_on_startup(icon, item):
        app.set_run_on_startup(not app.run_on_startup)

    menu_items = [
        pystray.MenuItem(
            app.monitor_friendly_names.get(name, name),
            make_toggle_monitor(name),
            checked=lambda item, name=name: app.monitor_enabled.get(name, True),
        )
        for name in app.monitor_friendly_names
    ]
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.extend(
        pystray.MenuItem(
            label,
            make_set_dimming_mode(mode),
            checked=lambda item, mode=mode: app.dimming_mode == mode,
            radio=True,
        )
        for mode, label in _DIMMING_MODE_LABELS.items()
    )
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.extend(
        pystray.MenuItem(
            "100% (Disabled)" if p == 100 else f"{p}%",
            make_set_brightness(p),
            checked=lambda item, p=p: app.brightness == p,
        )
        for p in _PRESETS
    )
    menu_items.append(pystray.Menu.SEPARATOR)
    gamma_duration_items = [
        pystray.MenuItem(
            label,
            make_set_gamma_duration(minutes),
            checked=lambda item, minutes=minutes: app.gamma_duration_minutes == minutes,
            radio=True,
        )
        for minutes, label in _GAMMA_DURATION_LABELS.items()
    ]
    menu_items.append(
        pystray.MenuItem(
            "Use Gamma Mode if Z-Fighting is Detected for",
            pystray.Menu(*gamma_duration_items),
            # Irrelevant once gamma is the dedicated mode (no overlay to flicker) or
            # if no active display even accepts a gamma-ramp/SDR-white-level write.
            visible=lambda item: (
                app.dimming_mode == DIMMING_MODE_OVERLAY and any(app.monitor_gamma_supported.values())
            ),
        )
    )
    menu_items.append(
        pystray.MenuItem(
            "Schedule",
            pystray.Menu(
                pystray.MenuItem(
                    "Enabled",
                    handle_toggle_schedule,
                    checked=lambda item: app.schedule_enabled,
                ),
                pystray.MenuItem("Edit Schedule...", handle_edit_schedule),
            ),
        )
    )
    menu_items.append(
        pystray.MenuItem(
            "Run on Startup",
            handle_toggle_run_on_startup,
            checked=lambda item: app.run_on_startup,
        )
    )
    menu_items.append(pystray.MenuItem("Reset display to normal", handle_reset_gamma))
    menu_items.append(
        pystray.MenuItem(
            "OLED VRR Black Flicker Tool",
            pystray.Menu(
                pystray.MenuItem(
                    "Active",
                    handle_toggle_shadow_lift_active,
                    checked=lambda item: app.shadow_lift_active,
                ),
                pystray.MenuItem("Configure...", handle_configure_shadow_lift),
            ),
            # Raising near-black output requires an actual writable gamma ramp --
            # pointless to show if no active display accepts it.
            visible=lambda item: any(app.monitor_gamma_supported.values()),
        )
    )
    menu_items.append(pystray.MenuItem("Exit", handle_exit))
    # Disabled blank row so the menu's last real item doesn't sit flush against
    # the taskbar edge / get obscured by it.
    menu_items.append(pystray.MenuItem(" ", None, enabled=False))

    icon = pystray.Icon("PowerDim", _make_icon_image(), "PowerDim", pystray.Menu(*menu_items))
    app.on_flicker_fallback = lambda: icon.notify(
        "Switching to gamma dimming due to detected flicker", "PowerDim"
    )
    app.on_gamma_unavailable = lambda: icon.notify(
        "Gamma dimming is unavailable on this display. Staying on overlay mode.", "PowerDim"
    )
    return icon


def run_tray_in_background(app: PowerDimApp, on_exit) -> threading.Thread:
    icon = build_tray_icon(app, on_exit)
    thread = threading.Thread(target=icon.run, daemon=True)
    thread.start()
    return thread

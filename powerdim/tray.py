"""System tray icon: brightness presets + exit, running on its own thread."""
import ctypes
import logging
import re
import threading
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox

import pystray

from . import updater
from .app import (
    DIMMING_MODE_GAMMA,
    DIMMING_MODE_OVERLAY,
    GAMMA_DURATION_INDEFINITE,
    GAMMA_DURATION_NEVER,
    PowerDimApp,
)
from .app_icon import make_icon_image
from .hotkey_editor import open_hotkey_editor
from .schedule_editor import open_schedule_editor
from .shadow_lift_editor import open_shadow_lift_editor
from .win32defs import (
    MONITOR_DEFAULTTONEAREST,
    MONITORINFO,
    TPM_BOTTOMALIGN,
    TPM_LEFTALIGN,
    TPM_RETURNCMD,
    TPM_RIGHTALIGN,
    TPM_TOPALIGN,
    user32,
)

# pystray's own custom message code for tray icon notifications (WM_USER + 11),
# used below to override its default popup-menu positioning.
_WM_NOTIFY = 0x400 + 11
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONUP = 0x0205

logger = logging.getLogger(__name__)

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


def _menu_anchor(cursor_x, cursor_y):
    """Clamp the popup point to the work area of the monitor under the cursor
    (i.e. excluding the taskbar) and pick which corner to anchor from, so the
    menu is always drawn fully above/beside the taskbar rather than under it.
    """
    monitor = user32.MonitorFromPoint(wintypes.POINT(cursor_x, cursor_y), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return cursor_x, cursor_y, TPM_RIGHTALIGN | TPM_BOTTOMALIGN

    work, mon = info.rcWork, info.rcMonitor
    x, y = cursor_x, cursor_y

    if work.bottom < mon.bottom:
        y, valign = min(y, work.bottom), TPM_BOTTOMALIGN
    elif work.top > mon.top:
        y, valign = max(y, work.top), TPM_TOPALIGN
    else:
        valign = TPM_BOTTOMALIGN

    if work.right < mon.right:
        x, halign = min(x, work.right), TPM_RIGHTALIGN
    elif work.left > mon.left:
        x, halign = max(x, work.left), TPM_LEFTALIGN
    else:
        halign = TPM_RIGHTALIGN

    return x, y, halign | valign


def _install_taskbar_aware_menu(icon) -> None:
    """Replace pystray's default right-click handler (which anchors the menu
    to the raw cursor position) with one that anchors to the monitor's work
    area instead, so the menu never renders underneath the taskbar.

    Relies on pystray's private _menu_handle/_hwnd/_menu_hwnd attributes --
    if a future pystray version renames these, we just fall back silently to
    its own (still functional) default positioning.
    """

    def on_notify(wparam, lparam):
        if lparam == _WM_LBUTTONUP:
            icon()
            return
        if lparam != _WM_RBUTTONUP or not icon._menu_handle:
            return

        user32.SetForegroundWindow(icon._hwnd)
        cursor = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        x, y, align = _menu_anchor(cursor.x, cursor.y)

        hmenu, descriptors = icon._menu_handle
        index = user32.TrackPopupMenuEx(hmenu, align | TPM_RETURNCMD, x, y, icon._menu_hwnd, None)
        if index > 0:
            descriptors[index - 1](icon)

    try:
        icon._message_handlers[_WM_NOTIFY] = on_notify
    except AttributeError:
        logger.warning("Could not install taskbar-aware menu positioning; using pystray's default.")


def _ask_install_update(version: str) -> bool:
    root = tk.Tk()
    root.withdraw()
    answer = messagebox.askyesno(
        "PowerDim Update", f"Version {version} is available. Download and install now?"
    )
    root.destroy()
    return answer


def _check_for_update_flow(icon, on_exit) -> None:
    info = updater.check_for_update()
    if info is None:
        icon.notify("You're already on the latest version.", "PowerDim")
        return
    if not _ask_install_update(info.version):
        return
    try:
        new_exe = updater.download_update(info)
        updater.apply_update(new_exe)
    except updater.UpdateError as exc:
        icon.notify(f"Update failed: {exc}", "PowerDim")
        return
    except Exception:
        logger.exception("Unexpected error while applying update")
        icon.notify("Update failed unexpectedly. Check the log for details.", "PowerDim")
        return
    icon.notify(f"Installing PowerDim {info.version}; restarting now.", "PowerDim")
    icon.stop()
    on_exit()


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

    def handle_toggle_schedule(icon, item):
        app.set_schedule_enabled(not app.schedule_enabled)

    def handle_edit_schedule(icon, item):
        threading.Thread(target=open_schedule_editor, args=(app,), daemon=True).start()

    def handle_toggle_run_on_startup(icon, item):
        app.set_run_on_startup(not app.run_on_startup)

    def handle_configure_hotkeys(icon, item):
        threading.Thread(target=open_hotkey_editor, args=(app,), daemon=True).start()

    def handle_check_for_update(icon, item):
        threading.Thread(target=_check_for_update_flow, args=(icon, on_exit), daemon=True).start()

    # Best-effort match to the number Windows itself shows in Display Settings:
    # device names are of the form "\\.\DISPLAYn"; fall back to enumeration
    # order for anything that doesn't fit that shape. Re-ranked to consecutive
    # 1, 2, 3... so a gap in the underlying numbers (e.g. left behind by a
    # monitor that's since been unplugged) doesn't show up as a confusing
    # non-consecutive index.
    raw_display_numbers = {}
    for position, name in enumerate(app.monitor_friendly_names, start=1):
        match = re.search(r"(\d+)$", name)
        raw_display_numbers[name] = int(match.group(1)) if match else position
    rank_by_raw_number = {
        raw: rank for rank, raw in enumerate(sorted(set(raw_display_numbers.values())), start=1)
    }
    monitor_indices = {name: rank_by_raw_number[raw] for name, raw in raw_display_numbers.items()}

    def _monitor_label(name):
        label = f"{monitor_indices.get(name, '?')}: {app.monitor_friendly_names.get(name, name)}"
        if not app.monitor_gamma_supported.get(name, False):
            label += " (No Gamma Control)"
        return label

    def _enabled_monitor_names():
        return [name for name in app.monitor_friendly_names if app.monitor_enabled.get(name, True)]

    def _monitors_in_mode(mode):
        return sorted(
            monitor_indices.get(name, 0)
            for name in _enabled_monitor_names()
            if app.effective_dimming_mode_for_monitor(name) == mode
        )

    def _mode_is_split():
        enabled_names = _enabled_monitor_names()
        if not enabled_names:
            return False
        effective_modes = {app.effective_dimming_mode_for_monitor(name) for name in enabled_names}
        return len(effective_modes) > 1

    def _mode_label(mode):
        base = _DIMMING_MODE_LABELS[mode]
        if not _mode_is_split():
            return base
        indices = _monitors_in_mode(mode)
        if not indices:
            return base
        if len(indices) == 1:
            return f"{base} (Monitor {indices[0]})"
        return f"{base} (Monitors {', '.join(str(i) for i in indices)})"

    def _mode_checked(mode):
        if _mode_is_split():
            return True
        return app.dimming_mode == mode

    def _mode_radio(mode):
        # A dot when monitors are split across both modes, a checkmark when
        # they all agree -- same distinction Windows draws between radio-style
        # and regular checkable menu items.
        return _mode_is_split()

    menu_items = [
        pystray.MenuItem(
            lambda item, name=name: _monitor_label(name),
            make_toggle_monitor(name),
            checked=lambda item, name=name: app.monitor_enabled.get(name, True),
        )
        for name in app.monitor_friendly_names
    ]
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.extend(
        pystray.MenuItem(
            lambda item, mode=mode: _mode_label(mode),
            make_set_dimming_mode(mode),
            checked=lambda item, mode=mode: _mode_checked(mode),
            radio=lambda item, mode=mode: _mode_radio(mode),
        )
        for mode in _DIMMING_MODE_LABELS
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
            "Use Gamma Mode when Z-Fighting is Detected for:",
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
    menu_items.append(pystray.MenuItem("Configure Hotkeys...", handle_configure_hotkeys))
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
    menu_items.append(pystray.MenuItem("Check for Updates...", handle_check_for_update))
    menu_items.append(pystray.MenuItem("Exit", handle_exit))

    icon = pystray.Icon("PowerDim", make_icon_image(), "PowerDim", pystray.Menu(*menu_items))
    _install_taskbar_aware_menu(icon)
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

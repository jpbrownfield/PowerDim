"""System tray icon: brightness presets + exit, running on its own thread."""
import threading

from PIL import Image, ImageDraw
import pystray

from .app import PowerDimApp

_PRESETS = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]


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

    def handle_exit(icon, item):
        icon.stop()
        on_exit()

    menu_items = [
        pystray.MenuItem(f"{p}%", make_set_brightness(p), checked=lambda item, p=p: app.brightness == p)
        for p in _PRESETS
    ]
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.append(pystray.MenuItem("Exit", handle_exit))

    return pystray.Icon("PowerDim", _make_icon_image(), "PowerDim", pystray.Menu(*menu_items))


def run_tray_in_background(app: PowerDimApp, on_exit) -> threading.Thread:
    icon = build_tray_icon(app, on_exit)
    thread = threading.Thread(target=icon.run, daemon=True)
    thread.start()
    return thread

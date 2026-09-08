"""Shared icon artwork: a dark circle with a blue ring, used for both the tray
icon and the application's own .exe/window icon (see scripts/generate_icon.py),
so PowerDim never falls back to the generic Python icon.
"""
from PIL import Image, ImageDraw

_FILL_COLOR = (20, 20, 20, 255)
_BORDER_COLOR = (40, 120, 220, 255)


def make_icon_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, round(size * 0.0625))
    width = max(1, round(size * 0.047))
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=_FILL_COLOR,
        outline=_BORDER_COLOR,
        width=width,
    )
    return img

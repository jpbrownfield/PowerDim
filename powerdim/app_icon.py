"""Shared icon artwork: a dark circle with a blue ring, used for both the tray
icon and the application's own .exe/window icon (see scripts/generate_icon.py),
so PowerDim never falls back to the generic Python icon.
"""
from PIL import Image, ImageDraw

_FILL_COLOR = (20, 20, 20, 255)
_BORDER_COLOR = (40, 120, 220, 255)
_BORDER_COLOR_PULSE_PEAK = (140, 210, 255, 255)


def make_icon_image(size: int = 64, pulse: float = 0.0) -> Image.Image:
    """Draw the tray icon. `pulse` (0.0-1.0) blends the ring towards a lighter
    highlight color and thickens it, used by the tray to animate a pronounced
    "breathing" pulse while dimming is active.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, round(size * 0.0625))
    width = max(1, round(size * (0.047 + 0.11 * pulse)))
    border = _blend(_BORDER_COLOR, _BORDER_COLOR_PULSE_PEAK, pulse)
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=_FILL_COLOR,
        outline=border,
        width=width,
    )
    return img


def _blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))

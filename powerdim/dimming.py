"""Pure brightness/alpha math -- no Win32 dependency, fully unit-testable."""

MIN_BRIGHTNESS = 0
MAX_BRIGHTNESS = 100
MAX_ALPHA = 255


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def compute_alpha(brightness_percent: int) -> int:
    """Map 0-100 brightness (100 = full brightness, no overlay) to a 0-255 overlay alpha."""
    b = clamp(brightness_percent, MIN_BRIGHTNESS, MAX_BRIGHTNESS)
    return round((MAX_BRIGHTNESS - b) / MAX_BRIGHTNESS * MAX_ALPHA)


def is_full_brightness(brightness_percent: int) -> bool:
    return brightness_percent >= MAX_BRIGHTNESS

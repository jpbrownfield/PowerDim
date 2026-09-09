"""User-configurable global hotkey bindings, persisted as JSON.

Stored under %LOCALAPPDATA%\\PowerDim\\hotkeys.json, analogous to
powerdim.schedule (which persists time-based brightness rules instead of key
bindings). Also holds the display-name tables used by the hotkey editor UI so
that both app.py and hotkey_editor.py share one source of truth for which
keys/modifiers are selectable.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .win32defs import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    VK_DELETE,
    VK_DOWN,
    VK_END,
    VK_HOME,
    VK_INSERT,
    VK_LEFT,
    VK_NEXT,
    VK_PRIOR,
    VK_RIGHT,
    VK_UP,
)

_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PowerDim"
_STATE_FILE = _STATE_DIR / "hotkeys.json"

ACTION_BRIGHTNESS_UP = "brightness_up"
ACTION_BRIGHTNESS_DOWN = "brightness_down"
ACTION_RESET = "reset"
# Jumps to `value`, or back to 100% if brightness is already at `value` --
# lets one hotkey act as a toggle between "dim to X" and "undo".
ACTION_SET_VALUE = "set_value"

ACTION_LABELS = {
    ACTION_BRIGHTNESS_UP: "Brightness Up",
    ACTION_BRIGHTNESS_DOWN: "Brightness Down",
    ACTION_RESET: "Reset to 100%",
    ACTION_SET_VALUE: "Set Brightness To...",
}

# Ordered so the editor's modifier checkboxes always appear the same way.
MODIFIER_FLAGS = [
    ("Ctrl", MOD_CONTROL),
    ("Alt", MOD_ALT),
    ("Shift", MOD_SHIFT),
    ("Win", MOD_WIN),
]

_NAV_KEYS = {
    "Up": VK_UP,
    "Down": VK_DOWN,
    "Left": VK_LEFT,
    "Right": VK_RIGHT,
    "Home": VK_HOME,
    "End": VK_END,
    "Page Up": VK_PRIOR,
    "Page Down": VK_NEXT,
    "Insert": VK_INSERT,
    "Delete": VK_DELETE,
}
_LETTER_KEYS = {chr(ord("A") + i): 0x41 + i for i in range(26)}
_DIGIT_KEYS = {str(i): 0x30 + i for i in range(10)}
_FUNCTION_KEYS = {f"F{i}": 0x70 + (i - 1) for i in range(1, 13)}

# Display order for the key picker combobox.
KEY_NAME_TO_VK = {**_NAV_KEYS, **_LETTER_KEYS, **_DIGIT_KEYS, **_FUNCTION_KEYS}
VK_TO_KEY_NAME = {vk: name for name, vk in KEY_NAME_TO_VK.items()}
KEY_CHOICES = list(KEY_NAME_TO_VK)


def modifiers_label(modifiers: int) -> str:
    return "+".join(name for name, flag in MODIFIER_FLAGS if modifiers & flag)


def key_label(vk: int) -> str:
    return VK_TO_KEY_NAME.get(vk, f"VK 0x{vk:02X}")


def hotkey_label(modifiers: int, vk: int) -> str:
    mods = modifiers_label(modifiers)
    key = key_label(vk)
    return f"{mods}+{key}" if mods else key


@dataclass
class HotkeyBinding:
    action: str
    modifiers: int
    vk: int
    value: int = 100  # only meaningful for ACTION_SET_VALUE


def next_brightness_for_set_value(current: int, value: int) -> int:
    """The ACTION_SET_VALUE toggle: jump to `value`, or back to 100% if we're
    already there."""
    return 100 if current == value else value


def default_bindings() -> list[HotkeyBinding]:
    return []


def load_bindings() -> list[HotkeyBinding]:
    try:
        raw = json.loads(_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default_bindings()
    try:
        return [HotkeyBinding(**b) for b in raw["bindings"]]
    except (KeyError, TypeError):
        return default_bindings()


def save_bindings(bindings: list[HotkeyBinding]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump({"bindings": [asdict(b) for b in bindings]}, f)

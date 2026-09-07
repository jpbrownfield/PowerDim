"""Crash-recovery persistence for gamma ramp baselines.

If PowerDim's process dies uncleanly (crash, kill, power loss) while gamma
dimming is active, the display's LUT stays wherever we last left it -- there is
no OS-level "restore point" to fall back on; SetDeviceGammaRamp doesn't
distinguish an OS default from any other curve. To avoid leaving a monitor
dimmed indefinitely after an unclean exit, we persist the pre-dim baseline for
each monitor to disk before every dim, and self-heal the next time PowerDim
starts by restoring any baseline left over from a run that never cleaned up.
"""
import json
import os
import tempfile
from pathlib import Path

_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PowerDim"
_STATE_FILE = _STATE_DIR / "gamma_recovery.json"


def save_baseline(device_name: str, red, green, blue) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = _read_all()
    state[device_name] = {"red": list(red), "green": list(green), "blue": list(blue)}
    _write_all(state)


def clear_baseline(device_name: str) -> None:
    state = _read_all()
    if device_name in state:
        del state[device_name]
        _write_all(state)


def load_leftover_baseline(device_name: str):
    """Return {"red": [...], "green": [...], "blue": [...]} left over from an
    unclean previous exit, or None if nothing was left for this device."""
    return _read_all().get(device_name)


def _read_all() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_all(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())  # survive a power loss right after this write
        os.replace(tmp_path, _STATE_FILE)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

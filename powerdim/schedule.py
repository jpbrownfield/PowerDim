"""Time-of-day dimming schedule.

Windows has no lightweight calendar-trigger primitive worth wiring up for this,
so we just poll the wall clock on a normal timer and compare it against a
sorted list of "at this time of day, use this brightness" entries -- a tiny
cron. Only entry-point transitions (the active entry changing) trigger a
brightness change, so a manual override between two scheduled times is never
fought until the next transition.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PowerDim"
_STATE_FILE = _STATE_DIR / "schedule.json"


@dataclass
class ScheduleEntry:
    hour: int
    minute: int
    brightness: int
    enabled: bool = True

    @property
    def minutes_of_day(self) -> int:
        return self.hour * 60 + self.minute


def load_entries() -> list[ScheduleEntry]:
    try:
        raw = json.loads(_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return [ScheduleEntry(**item) for item in raw.get("entries", [])]


def save_entries(entries: list[ScheduleEntry]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"entries": [asdict(e) for e in entries]}, f)
            f.flush()
            os.fsync(f.fileno())  # survive a power loss right after this write
        os.replace(tmp_path, _STATE_FILE)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def active_entry(entries: list[ScheduleEntry], now: datetime) -> ScheduleEntry | None:
    """Return the entry that should be active right now, or None if no enabled
    entry applies (e.g. the schedule is empty). The active entry is the most
    recent enabled one at or before the current time, wrapping to the latest
    entry of the previous day if none qualify yet today (e.g. it's 2am and the
    last entry was set for 11pm)."""
    enabled = sorted((e for e in entries if e.enabled), key=lambda e: e.minutes_of_day)
    if not enabled:
        return None
    now_minutes = now.hour * 60 + now.minute
    candidate = None
    for entry in enabled:
        if entry.minutes_of_day <= now_minutes:
            candidate = entry
    if candidate is None:
        candidate = enabled[-1]  # wrap to yesterday's last entry
    return candidate


def active_brightness(entries: list[ScheduleEntry], now: datetime) -> int | None:
    """Return the brightness that should be active right now, or None if no
    enabled entry applies. See active_entry() for the selection rule."""
    entry = active_entry(entries, now)
    return entry.brightness if entry is not None else None

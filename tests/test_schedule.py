from datetime import datetime

from powerdim.schedule import ScheduleEntry, active_brightness


def _dt(hour, minute):
    return datetime(2026, 9, 6, hour, minute)


def test_active_brightness_picks_most_recent_entry_today():
    entries = [
        ScheduleEntry(hour=8, minute=0, brightness=100),
        ScheduleEntry(hour=20, minute=0, brightness=40),
    ]
    assert active_brightness(entries, _dt(9, 0)) == 100
    assert active_brightness(entries, _dt(21, 0)) == 40


def test_active_brightness_wraps_to_previous_day_before_first_entry():
    entries = [
        ScheduleEntry(hour=8, minute=0, brightness=100),
        ScheduleEntry(hour=22, minute=0, brightness=30),
    ]
    assert active_brightness(entries, _dt(2, 0)) == 30


def test_active_brightness_ignores_disabled_entries():
    entries = [
        ScheduleEntry(hour=8, minute=0, brightness=100),
        ScheduleEntry(hour=9, minute=0, brightness=50, enabled=False),
    ]
    assert active_brightness(entries, _dt(10, 0)) == 100


def test_active_brightness_returns_none_when_no_enabled_entries():
    assert active_brightness([], _dt(10, 0)) is None
    assert active_brightness([ScheduleEntry(hour=8, minute=0, brightness=100, enabled=False)], _dt(10, 0)) is None


def test_active_brightness_exact_boundary_time():
    entries = [ScheduleEntry(hour=8, minute=0, brightness=70)]
    assert active_brightness(entries, _dt(8, 0)) == 70


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    import powerdim.schedule as schedule_mod

    monkeypatch.setattr(schedule_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(schedule_mod, "_STATE_FILE", tmp_path / "schedule.json")

    entries = [ScheduleEntry(hour=7, minute=30, brightness=80, enabled=True)]
    schedule_mod.save_entries(entries)
    loaded = schedule_mod.load_entries()

    assert loaded == entries


def test_load_entries_missing_file_returns_empty(tmp_path, monkeypatch):
    import powerdim.schedule as schedule_mod

    monkeypatch.setattr(schedule_mod, "_STATE_FILE", tmp_path / "does_not_exist.json")

    assert schedule_mod.load_entries() == []

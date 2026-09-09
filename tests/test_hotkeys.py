from powerdim.hotkeys import (
    HotkeyBinding,
    default_bindings,
    hotkey_label,
    load_bindings,
    next_brightness_for_set_value,
    save_bindings,
)


def test_next_brightness_for_set_value_jumps_to_target():
    assert next_brightness_for_set_value(current=100, value=40) == 40


def test_next_brightness_for_set_value_toggles_back_to_full_when_already_there():
    assert next_brightness_for_set_value(current=40, value=40) == 100


def test_default_bindings_is_empty():
    assert default_bindings() == []


def test_hotkey_label_joins_modifiers_and_key():
    from powerdim.win32defs import MOD_ALT, MOD_CONTROL, VK_UP

    assert hotkey_label(MOD_CONTROL | MOD_ALT, VK_UP) == "Ctrl+Alt+Up"


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    import powerdim.hotkeys as hotkeys_mod

    monkeypatch.setattr(hotkeys_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(hotkeys_mod, "_STATE_FILE", tmp_path / "hotkeys.json")

    bindings = [HotkeyBinding(action="set_value", modifiers=3, vk=0x35, value=50)]
    save_bindings(bindings)
    loaded = load_bindings()

    assert loaded == bindings


def test_load_bindings_missing_file_returns_defaults(tmp_path, monkeypatch):
    import powerdim.hotkeys as hotkeys_mod

    monkeypatch.setattr(hotkeys_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(hotkeys_mod, "_STATE_FILE", tmp_path / "missing.json")

    assert load_bindings() == default_bindings()

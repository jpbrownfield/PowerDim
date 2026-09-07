from powerdim import gamma_recovery


class TestGammaRecovery:
    def test_no_leftover_baseline_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gamma_recovery, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(gamma_recovery, "_STATE_FILE", tmp_path / "gamma_recovery.json")
        assert gamma_recovery.load_leftover_baseline(r"\\.\DISPLAY1") is None

    def test_save_then_load_roundtrips(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gamma_recovery, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(gamma_recovery, "_STATE_FILE", tmp_path / "gamma_recovery.json")
        red, green, blue = [1] * 256, [2] * 256, [3] * 256
        gamma_recovery.save_baseline(r"\\.\DISPLAY1", red, green, blue)
        loaded = gamma_recovery.load_leftover_baseline(r"\\.\DISPLAY1")
        assert loaded == {"red": red, "green": green, "blue": blue}

    def test_clear_removes_only_that_device(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gamma_recovery, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(gamma_recovery, "_STATE_FILE", tmp_path / "gamma_recovery.json")
        gamma_recovery.save_baseline(r"\\.\DISPLAY1", [1] * 256, [1] * 256, [1] * 256)
        gamma_recovery.save_baseline(r"\\.\DISPLAY2", [2] * 256, [2] * 256, [2] * 256)
        gamma_recovery.clear_baseline(r"\\.\DISPLAY1")
        assert gamma_recovery.load_leftover_baseline(r"\\.\DISPLAY1") is None
        assert gamma_recovery.load_leftover_baseline(r"\\.\DISPLAY2") is not None

    def test_clear_nonexistent_device_is_a_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gamma_recovery, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(gamma_recovery, "_STATE_FILE", tmp_path / "gamma_recovery.json")
        gamma_recovery.clear_baseline(r"\\.\DISPLAY1")  # should not raise

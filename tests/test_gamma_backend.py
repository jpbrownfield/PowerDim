"""HDR/SDR-white-level path of MonitorGammaDimmer, exercised without real hardware
by monkeypatching the powerdim.hdr calls it makes."""
from powerdim import gamma_backend


def _make_hdr_dimmer(monkeypatch, baseline_raw=1000):
    monkeypatch.setattr(gamma_backend.hdr, "is_hdr_enabled", lambda name: True)
    monkeypatch.setattr(gamma_backend.hdr, "get_sdr_white_level_raw", lambda name: baseline_raw)
    dimmer = gamma_backend.MonitorGammaDimmer("DISPLAY1")
    assert dimmer.is_hdr
    return dimmer


class TestHdrSetBrightnessVerification:
    def test_successful_write_is_verified(self, monkeypatch):
        dimmer = _make_hdr_dimmer(monkeypatch)
        monkeypatch.setattr(gamma_backend.hdr, "set_sdr_white_level_raw", lambda name, value: True)
        monkeypatch.setattr(gamma_backend.hdr, "get_sdr_white_level_raw", lambda name: 500)

        assert dimmer.set_brightness(50) is True
        assert dimmer.verify_applied() is True

    def test_write_reporting_success_but_not_taking_effect_fails(self, monkeypatch):
        dimmer = _make_hdr_dimmer(monkeypatch)
        monkeypatch.setattr(gamma_backend.hdr, "set_sdr_white_level_raw", lambda name, value: True)
        # Driver claims success but the readback still shows the old, undimmed value.
        monkeypatch.setattr(gamma_backend.hdr, "get_sdr_white_level_raw", lambda name: 1000)

        assert dimmer.set_brightness(50) is False
        assert dimmer.verify_applied() is False

    def test_set_call_failure_is_propagated(self, monkeypatch):
        dimmer = _make_hdr_dimmer(monkeypatch)
        monkeypatch.setattr(gamma_backend.hdr, "set_sdr_white_level_raw", lambda name, value: False)

        assert dimmer.set_brightness(50) is False


class TestHdrExternalChangeResync:
    def _make_stateful_hdr(self, monkeypatch, initial_raw):
        state = {"raw": initial_raw}

        def fake_set(name, value):
            state["raw"] = value
            return True

        monkeypatch.setattr(gamma_backend.hdr, "set_sdr_white_level_raw", fake_set)
        monkeypatch.setattr(gamma_backend.hdr, "get_sdr_white_level_raw", lambda name: state["raw"])
        return state

    def test_no_change_reports_false(self, monkeypatch):
        dimmer = _make_hdr_dimmer(monkeypatch)
        self._make_stateful_hdr(monkeypatch, 1000)
        dimmer.set_brightness(50)

        assert dimmer.poll_external_change() is False

    def test_external_change_is_reabsorbed_as_new_baseline(self, monkeypatch):
        dimmer = _make_hdr_dimmer(monkeypatch)
        state = self._make_stateful_hdr(monkeypatch, 1000)
        dimmer.set_brightness(50)

        # Something external (e.g. the user moving Windows' own slider) bumps the
        # raw value to 800 without going through us.
        state["raw"] = 800
        assert dimmer.poll_external_change() is True
        assert dimmer._sdr_baseline_raw == 800

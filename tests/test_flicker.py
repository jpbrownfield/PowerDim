from powerdim.flicker import FlickerDetector


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t

    def __call__(self) -> float:
        return self.t


class TestFlickerDetector:
    def test_no_flicker_below_threshold(self):
        clock = _FakeClock()
        detector = FlickerDetector(window_seconds=2.0, threshold=4, now_fn=clock)
        for _ in range(3):
            triggered = detector.record_correction()
            clock.advance(0.1)
        assert triggered is False

    def test_flicker_detected_when_threshold_reached_within_window(self):
        clock = _FakeClock()
        detector = FlickerDetector(window_seconds=2.0, threshold=4, now_fn=clock)
        results = []
        for _ in range(4):
            results.append(detector.record_correction())
            clock.advance(0.1)
        assert results == [False, False, False, True]

    def test_old_events_fall_out_of_window(self):
        clock = _FakeClock()
        detector = FlickerDetector(window_seconds=1.0, threshold=3, now_fn=clock)
        detector.record_correction()
        clock.advance(0.5)
        detector.record_correction()
        clock.advance(0.6)  # first event now outside the 1s window
        triggered = detector.record_correction()
        assert triggered is False

    def test_reset_clears_history(self):
        clock = _FakeClock()
        detector = FlickerDetector(window_seconds=2.0, threshold=2, now_fn=clock)
        detector.record_correction()
        detector.reset()
        triggered = detector.record_correction()
        assert triggered is False

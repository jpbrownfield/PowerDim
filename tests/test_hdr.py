from powerdim.hdr import _MIN_SDR_WHITE_LEVEL_RAW, scale_white_level_raw


class TestScaleWhiteLevelRaw:
    def test_full_brightness_returns_baseline(self):
        assert scale_white_level_raw(1000, 1.0) == 1000

    def test_half_brightness_halves_value(self):
        assert scale_white_level_raw(1000, 0.5) == 500

    def test_floor_prevents_near_zero_value(self):
        assert scale_white_level_raw(1000, 0.0) == _MIN_SDR_WHITE_LEVEL_RAW

    def test_factor_is_clamped_to_valid_range(self):
        assert scale_white_level_raw(1000, 2.0) == 1000
        assert scale_white_level_raw(1000, -1.0) == _MIN_SDR_WHITE_LEVEL_RAW

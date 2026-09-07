from powerdim.hdr import _MIN_SDR_WHITE_LEVEL_RAW, scale_white_level_raw
from powerdim.win32defs import (
    DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE,
)


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


class TestAdvancedColorInfoBits:
    def test_all_bits_clear(self):
        info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        info.value = 0
        assert not info.advanced_color_supported
        assert not info.advanced_color_enabled
        assert not info.advanced_color_force_disabled

    def test_supported_but_not_enabled(self):
        info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        info.value = 0x1
        assert info.advanced_color_supported
        assert not info.advanced_color_enabled

    def test_supported_and_enabled(self):
        info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        info.value = 0x1 | 0x2
        assert info.advanced_color_supported
        assert info.advanced_color_enabled

    def test_force_disabled_bit(self):
        info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        info.value = 0x8
        assert info.advanced_color_force_disabled
        assert not info.advanced_color_enabled


class TestSetAdvancedColorState:
    def test_enable_sets_bit(self):
        info = DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE()
        info.set_enable_advanced_color(True)
        assert info.value == 1

    def test_disable_clears_bit(self):
        info = DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE()
        info.set_enable_advanced_color(False)
        assert info.value == 0


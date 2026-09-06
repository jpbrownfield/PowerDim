import pytest

from powerdim.dimming import clamp, compute_alpha, is_full_brightness


class TestClamp:
    def test_within_range_unchanged(self):
        assert clamp(50, 0, 100) == 50

    def test_below_range_clamped_to_lo(self):
        assert clamp(-10, 0, 100) == 0

    def test_above_range_clamped_to_hi(self):
        assert clamp(150, 0, 100) == 100


class TestComputeAlpha:
    def test_full_brightness_is_zero_alpha(self):
        assert compute_alpha(100) == 0

    def test_zero_brightness_is_max_alpha(self):
        assert compute_alpha(0) == 255

    def test_half_brightness_is_half_alpha(self):
        assert compute_alpha(50) == 128  # round(127.5)

    def test_out_of_range_low_is_clamped(self):
        assert compute_alpha(-20) == 255

    def test_out_of_range_high_is_clamped(self):
        assert compute_alpha(150) == 0

    @pytest.mark.parametrize("brightness", [0, 10, 25, 50, 75, 90, 100])
    def test_alpha_within_byte_range(self, brightness):
        assert 0 <= compute_alpha(brightness) <= 255


class TestIsFullBrightness:
    def test_100_is_full(self):
        assert is_full_brightness(100) is True

    def test_above_100_is_full(self):
        assert is_full_brightness(120) is True

    def test_99_is_not_full(self):
        assert is_full_brightness(99) is False

    def test_zero_is_not_full(self):
        assert is_full_brightness(0) is False

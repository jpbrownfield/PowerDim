from powerdim.gamma import apply_shadow_lift, identity_ramp, ramps_equal, scale_ramp


class TestIdentityRamp:
    def test_spans_full_range(self):
        ramp = identity_ramp()
        assert ramp.Red[0] == 0
        assert ramp.Red[255] == 65535
        assert ramp.Green[128] == ramp.Blue[128] == ramp.Red[128]


class TestScaleRamp:
    def test_full_factor_matches_baseline(self):
        baseline = identity_ramp()
        scaled = scale_ramp(baseline, 1.0)
        assert ramps_equal(baseline, scaled)

    def test_zero_factor_is_all_black(self):
        baseline = identity_ramp()
        scaled = scale_ramp(baseline, 0.0)
        assert list(scaled.Red) == [0] * 256
        assert list(scaled.Green) == [0] * 256
        assert list(scaled.Blue) == [0] * 256

    def test_half_factor_halves_every_channel(self):
        baseline = identity_ramp()
        scaled = scale_ramp(baseline, 0.5)
        assert scaled.Red[255] == int(65535 * 0.5)

    def test_factor_is_clamped_to_valid_range(self):
        baseline = identity_ramp()
        over = scale_ramp(baseline, 2.0)
        under = scale_ramp(baseline, -1.0)
        assert ramps_equal(over, baseline)
        assert list(under.Red) == [0] * 256


class TestRampsEqual:
    def test_identical_ramps_are_equal(self):
        a = identity_ramp()
        b = identity_ramp()
        assert ramps_equal(a, b)

    def test_different_ramps_are_not_equal(self):
        a = identity_ramp()
        b = scale_ramp(a, 0.5)
        assert not ramps_equal(a, b)


class TestApplyShadowLift:
    def test_zero_percent_is_a_no_op(self):
        dimmed = scale_ramp(identity_ramp(), 0.5)
        lifted = apply_shadow_lift(dimmed, 0.0)
        assert ramps_equal(dimmed, lifted)

    def test_raises_near_black_output(self):
        dimmed = scale_ramp(identity_ramp(), 0.0)  # fully black
        lifted = apply_shadow_lift(dimmed, 10.0)
        assert lifted.Red[0] > dimmed.Red[0]
        assert lifted.Red[0] == lifted.Green[0] == lifted.Blue[0]

    def test_fades_out_toward_the_top_of_the_range(self):
        dimmed = scale_ramp(identity_ramp(), 0.0)
        lifted = apply_shadow_lift(dimmed, 10.0)
        assert lifted.Red[255] == dimmed.Red[255]

    def test_never_lowers_an_existing_value(self):
        baseline = identity_ramp()
        lifted = apply_shadow_lift(baseline, 50.0)
        assert all(lifted.Red[i] >= baseline.Red[i] for i in range(256))

    def test_percent_is_clamped_to_valid_range(self):
        dimmed = scale_ramp(identity_ramp(), 0.0)
        over = apply_shadow_lift(dimmed, 500.0)
        assert over.Red[0] <= 65535

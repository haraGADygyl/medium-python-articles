import pytest

from trailhead.elevation import gain_and_loss, highest_and_lowest, steepest_grade


def test_simple_climb_and_descent():
    assert gain_and_loss([100, 150, 120]) == (50.0, 30.0)


def test_jitter_below_the_threshold_is_ignored():
    assert gain_and_loss([500, 501, 499, 500.5, 501.5, 500]) == (0.0, 0.0)


def test_long_climb_in_small_steps_still_counts():
    assert gain_and_loss([float(step) for step in range(1000, 1301)]) == (300.0, 0.0)


def test_empty_and_single_elevation():
    assert gain_and_loss([]) == (0.0, 0.0)
    assert gain_and_loss([812]) == (0.0, 0.0)


def test_negative_threshold_is_rejected():
    with pytest.raises(ValueError):
        gain_and_loss([1, 2], threshold=-1)


def test_highest_and_lowest(make_track):
    track = make_track((0, 0, 900), (0, 0.01, 1450), (0, 0.02, 700))
    assert highest_and_lowest(track) == (1450, 700)


def test_steepest_grade_in_percent(make_track):
    # 0.01 degrees of longitude on the equator is about 1112 m.
    track = make_track((0, 0, 1000), (0, 0.01, 1100), (0, 0.02, 1050))
    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)

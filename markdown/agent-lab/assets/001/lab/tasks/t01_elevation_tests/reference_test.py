import pytest

from trailhead.elevation import (
    DEFAULT_THRESHOLD_M,
    gain_and_loss,
    highest_and_lowest,
    steepest_grade,
)


def test_simple_climb_and_descent():
    assert gain_and_loss([100, 150, 120]) == (50.0, 30.0)


def test_default_threshold_is_three_metres():
    assert DEFAULT_THRESHOLD_M == 3.0
    assert gain_and_loss([100, 102.5, 100]) == (0.0, 0.0)


def test_change_equal_to_the_threshold_counts():
    assert gain_and_loss([100, 103, 100]) == (3.0, 3.0)


def test_jitter_is_ignored():
    assert gain_and_loss([500, 501, 499, 500.5, 501.5, 500]) == (0.0, 0.0)


def test_climb_in_small_steps_counts():
    assert gain_and_loss([float(h) for h in range(1000, 1301)]) == (300.0, 0.0)


def test_loss_is_positive():
    gain, loss = gain_and_loss([900, 800, 700])
    assert (gain, loss) == (0.0, 200.0)


def test_empty_and_single():
    assert gain_and_loss([]) == (0.0, 0.0)
    assert gain_and_loss([5]) == (0.0, 0.0)


def test_negative_threshold_rejected():
    with pytest.raises(ValueError):
        gain_and_loss([1, 2, 3], threshold=-0.5)


def test_highest_and_lowest(make_track):
    assert highest_and_lowest(make_track((0, 0, 900), (0, 0.01, 1450), (0, 0.02, 700))) == (1450, 700)


def test_steepest_grade_counts_descents(make_track):
    track = make_track((0, 0, 1000), (0, 0.01, 1050), (0, 0.02, 950))
    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)


def test_steepest_grade_skips_repeated_points(make_track):
    track = make_track((0, 0, 1000), (0, 0, 1000), (0, 0.01, 1100))
    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)

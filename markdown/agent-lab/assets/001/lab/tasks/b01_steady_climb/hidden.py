import pytest

from trailhead.elevation import gain_and_loss
from trailhead.report import summarise


def test_steady_climb_in_one_metre_steps():
    assert gain_and_loss([float(h) for h in range(1000, 1301)]) == (300.0, 0.0)


def test_steady_descent_in_half_metre_steps():
    assert gain_and_loss([1000 - 0.5 * i for i in range(401)]) == (0.0, 198.0)


def test_jitter_still_ignored():
    assert gain_and_loss([500, 501, 499, 500.5, 501.5, 500, 502, 500]) == (0.0, 0.0)


def test_threshold_boundary_counts():
    assert gain_and_loss([100, 103, 100]) == (3.0, 3.0)
    assert gain_and_loss([100, 101, 102, 103]) == (3.0, 0.0)


def test_summary_of_a_finely_sampled_climb(make_track):
    track = make_track(*[(0, i * 0.0001, 1000 + i) for i in range(301)])
    assert summarise(track).gain_m == 300.0

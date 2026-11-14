import pytest

from trailhead.elevation import steepest_grade
from trailhead.report import format_summary, summarise

RIDGE = ((0, 0, 1000), (0, 0.01, 1100), (0, 0.02, 1050))


def test_steepest_grade_is_a_percentage(make_track):
    assert steepest_grade(make_track(*RIDGE)) == pytest.approx(9.0, abs=0.05)


def test_eighteen_metres_over_a_hundred(make_track):
    # 0.0008993 degrees of latitude is 100 m.
    track = make_track((42.0, 23.0, 500), (42.0008993, 23.0, 518))
    assert steepest_grade(track) == pytest.approx(18.0, abs=0.05)


def test_summary_shows_the_same_percentage(make_track):
    summary = summarise(make_track(*RIDGE))
    assert summary.steepest_pct == pytest.approx(9.0, abs=0.05)
    assert "  steepest  9.0%\n" in format_summary(summary)

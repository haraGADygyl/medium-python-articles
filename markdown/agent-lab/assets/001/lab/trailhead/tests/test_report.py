import pytest

from trailhead.report import format_summary, summarise

RIDGE = ((0, 0, 1000), (0.01, 0.01, 1100), (0.02, 0.02, 1050))


def test_summary_of_a_north_east_climb(make_track):
    summary = summarise(make_track(*RIDGE, name="North-East Ridge"))
    assert summary.length_km == 3.1
    assert (summary.gain_m, summary.loss_m) == (100.0, 50.0)
    assert (summary.highest_m, summary.lowest_m) == (1100, 1000)
    assert summary.hours == pytest.approx(3.14507 / 5 + 100 / 600, abs=1e-3)
    assert summary.heading == "NE"


def test_format_summary(make_track):
    assert format_summary(summarise(make_track(*RIDGE, name="North-East Ridge"))) == "\n".join(
        [
            "North-East Ridge",
            "  distance  3.1 km",
            "  ascent    +100 m / -50 m",
            "  altitude  1000-1100 m",
            "  steepest  6.4%",
            "  time      0h 48m",
            "  heading   NE",
        ]
    )

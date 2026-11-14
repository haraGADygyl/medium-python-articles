import pytest

from trailhead.report import format_summary, summarise

EAST = ((0, 0, 1000), (0, 0.01, 1100), (0, 0.02, 1050))
NORTH_EAST = ((0, 0, 1000), (0.01, 0.01, 1100), (0.02, 0.02, 1050))


def test_summary_fields(make_track):
    summary = summarise(make_track(*EAST, name="East"))
    assert summary.name == "East"
    assert summary.length_km == 2.2
    assert (summary.gain_m, summary.loss_m) == (100.0, 50.0)
    assert summary.hours == pytest.approx(2.2239 / 5 + 100 / 600, abs=1e-3)
    assert summary.heading == "E"


def test_fitness_and_threshold(make_track):
    track = make_track(*EAST)
    assert summarise(track, fitness=2).hours == pytest.approx(summarise(track).hours / 2)
    jitter = make_track((0, 0, 1000), (0, 0.01, 1002), (0, 0.02, 1000))
    assert summarise(jitter).gain_m == 0.0
    assert summarise(jitter, threshold=1).gain_m == 2.0


def test_loop_and_near_loop(make_track):
    assert summarise(make_track((0, 0, 0), (0, 0.01, 0), (0, 0.0004, 0))).heading == "loop"
    assert summarise(make_track((0, 0, 0), (0, 0.01, 0), (0, 0.005, 0))).heading == "E"


def test_format_summary(make_track):
    assert format_summary(summarise(make_track(*EAST, name="East"))) == "\n".join([
        "East",
        "  distance  2.2 km",
        "  ascent    +100 m / -50 m",
        "  altitude  1000-1100 m",
        "  steepest  9.0%",
        "  time      0h 37m",
        "  heading   E",
    ])


def test_steepest_keeps_one_decimal(make_track):
    assert "  steepest  6.4%" in format_summary(summarise(make_track(*NORTH_EAST)))

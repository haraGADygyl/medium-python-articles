import pytest

from trailhead.cli import main
from trailhead.elevation import highest_and_lowest, steepest_grade
from trailhead.pace import leg_hours
from trailhead.report import summarise

GAPS = ((0, 0, 1000), (0, 0.01, None), (0, 0.02, 1100), (0, 0.03, None))
LEADING = ((0, 0, None), (0, 0.01, 1000), (0, 0.02, 1100))


def test_gaps_take_the_previous_elevation(make_track):
    summary = summarise(make_track(*GAPS))
    assert (summary.gain_m, summary.loss_m) == (100.0, 0.0)
    assert highest_and_lowest(make_track(*GAPS)) == (1100, 1000)


def test_a_leading_gap_takes_the_next_elevation(make_track):
    summary = summarise(make_track(*LEADING))
    assert (summary.lowest_m, summary.highest_m) == (1000, 1100)
    assert summary.gain_m == 100.0


def test_steepest_grade_with_a_gap(make_track):
    # filled: 1000, 1000, 1100 -> the second leg climbs 100 m over 1112 m
    track = make_track((0, 0, 1000), (0, 0.01, None), (0, 0.02, 1100))
    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)


def test_walking_time_with_a_gap(make_track):
    legs = leg_hours(make_track((0, 0, 1000), (0, 0.01, None), (0, 0.02, 1100)))
    assert legs == pytest.approx([1.11195 / 5, 1.11195 / 5 + 100 / 600], abs=1e-4)


def test_summary_command_with_a_gap(write_track, capsys):
    path = write_track("lat,lon,ele\n0,0,1000\n0,0.01,\n0,0.02,1100\n")
    assert main(["summary", str(path)]) == 0
    out = capsys.readouterr().out
    assert "  altitude  1000-1100 m\n" in out
    assert "  ascent    +100 m / -0 m\n" in out

import pytest

from trailhead.cli import main
from trailhead.plan import split_days

STEP = 4.99 / 111.19508  # just under one flat hour per leg


def test_split_days_uses_fitness(make_track):
    track = make_track(*[(0, index * STEP, 0) for index in range(7)])
    assert [hours for *_, hours in split_days(track, 3, fitness=2.0)] == pytest.approx([2.99])
    assert len(split_days(track, 3)) == 2


def test_plan_command_passes_fitness(write_track, capsys):
    path = write_track("lat,lon,ele\n0,0,1000\n0,0.01,1100\n0,0.02,1050\n")
    assert main(["plan", str(path), "--max-hours", "0.4", "--fitness", "2"]) == 0
    assert capsys.readouterr().out == "Day 1: points 0-2, 0h 19m\n"


def test_summary_still_uses_fitness(write_track, capsys):
    path = write_track("lat,lon,ele\n0,0,1000\n0,0.01,1100\n0,0.02,1050\n")
    assert main(["summary", str(path), "--fitness", "2"]) == 0
    assert "  time      0h 18m\n" in capsys.readouterr().out

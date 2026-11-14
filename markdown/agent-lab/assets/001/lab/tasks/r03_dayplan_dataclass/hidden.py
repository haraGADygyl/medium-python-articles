import dataclasses

import pytest

from trailhead.cli import main
from trailhead.plan import DayPlan, describe_plan, split_days


@pytest.fixture
def five_flat_hours(make_track):
    step = 5 / 111.19508
    return make_track(*[(0, index * step, 0) for index in range(6)])


def test_dayplan_is_a_frozen_dataclass():
    assert dataclasses.is_dataclass(DayPlan)
    assert [f.name for f in dataclasses.fields(DayPlan)] == [
        "day", "first_point", "last_point", "hours"]
    plan = DayPlan(1, 0, 3, 2.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.day = 2


def test_split_days_returns_dayplans(five_flat_hours):
    days = split_days(five_flat_hours, max_hours_per_day=2.5)
    assert all(isinstance(day, DayPlan) for day in days)
    assert [(d.day, d.first_point, d.last_point) for d in days] == [(1, 0, 2), (2, 2, 4), (3, 4, 5)]
    assert [d.hours for d in days] == pytest.approx([2.0, 2.0, 1.0])


def test_single_day_and_long_leg(five_flat_hours, make_track):
    (only,) = split_days(five_flat_hours)
    assert (only.day, only.first_point, only.last_point) == (1, 0, 5)
    long = split_days(make_track((0, 0, 0), (0, 0.5, 0), (0, 0.51, 0)), max_hours_per_day=3)
    assert [(d.first_point, d.last_point) for d in long] == [(0, 1), (1, 2)]


def test_invalid_limit(five_flat_hours):
    with pytest.raises(ValueError):
        split_days(five_flat_hours, max_hours_per_day=0)


def test_describe_plan_takes_dayplans():
    assert describe_plan([DayPlan(1, 0, 14, 6.0833), DayPlan(2, 14, 31, 0.75)]) == [
        "Day 1: points 0-14, 6h 05m",
        "Day 2: points 14-31, 0h 45m",
    ]


def test_plan_command_output_unchanged(write_track, capsys):
    path = write_track("# name: Ridge\nlat,lon,ele\n0,0,1000\n0,0.01,1100\n0,0.02,1050\n")
    assert main(["plan", str(path), "--max-hours", "0.3"]) == 0
    assert capsys.readouterr().out == "Day 1: points 0-1, 0h 23m\nDay 2: points 1-2, 0h 13m\n"

import pytest

import trailhead.plan
from trailhead.plan import describe_plan, split_days


@pytest.fixture
def five_points(make_track):
    return make_track(*[(0, i * 0.01, 0) for i in range(5)])


@pytest.fixture
def legs(monkeypatch):
    def use(hours):
        monkeypatch.setattr(trailhead.plan, "leg_hours", lambda track, fitness=1.0: list(hours))

    return use


def test_days_fill_the_limit_exactly(five_points, legs):
    legs([1.0, 1.0, 1.0, 1.0])
    assert split_days(five_points, max_hours_per_day=2.0) == [(1, 0, 2, 2.0), (2, 2, 4, 2.0)]


def test_one_long_leg_is_its_own_day(five_points, legs):
    legs([0.5, 9.0, 0.5, 0.5])
    assert split_days(five_points, max_hours_per_day=2.0) == [
        (1, 0, 1, 0.5), (2, 1, 2, 9.0), (3, 2, 4, 1.0)]


def test_hours_are_rounded_to_hundredths(five_points, legs):
    legs([0.333, 0.333, 0.0, 0.0])
    assert split_days(five_points) == [(1, 0, 4, 0.67)]


def test_limit_must_be_positive(five_points):
    for bad in (0, -1):
        with pytest.raises(ValueError):
            split_days(five_points, max_hours_per_day=bad)


def test_fitness_divides_time(make_track):
    step = 5 / 111.19508
    track = make_track(*[(0, i * step, 0) for i in range(6)])
    assert split_days(track, max_hours_per_day=10, fitness=2.0) == [(1, 0, 5, 2.5)]


def test_describe_plan_rounds_and_pads():
    assert describe_plan([(1, 0, 14, 6.07), (2, 14, 31, 0.748), (3, 31, 40, 2.999)]) == [
        "Day 1: points 0-14, 6h 04m",
        "Day 2: points 14-31, 0h 45m",
        "Day 3: points 31-40, 3h 00m",
    ]

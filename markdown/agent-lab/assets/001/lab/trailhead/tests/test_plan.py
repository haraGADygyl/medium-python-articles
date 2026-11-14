import pytest

from trailhead.plan import describe_plan, split_days


@pytest.fixture
def five_flat_hours(make_track):
    # Five legs of 5 km each along the equator: one hour per leg by Naismith's rule.
    step = 5 / 111.19508
    return make_track(*[(0, index * step, 0) for index in range(6)])


def test_everything_fits_in_one_day(five_flat_hours):
    assert split_days(five_flat_hours) == [(1, 0, 5, 1.0 * 5)]


def test_days_respect_the_limit(five_flat_hours):
    assert split_days(five_flat_hours, max_hours_per_day=2.5) == [
        (1, 0, 2, 2.0),
        (2, 2, 4, 2.0),
        (3, 4, 5, 1.0),
    ]


def test_one_long_leg_is_a_day_on_its_own(make_track):
    track = make_track((0, 0, 0), (0, 0.5, 0), (0, 0.51, 0))
    days = split_days(track, max_hours_per_day=3)
    assert [(day, first, last) for day, first, last, _ in days] == [(1, 0, 1), (2, 1, 2)]


def test_invalid_limit(five_flat_hours):
    with pytest.raises(ValueError):
        split_days(five_flat_hours, max_hours_per_day=0)


def test_describe_plan():
    assert describe_plan([(1, 0, 14, 6.07), (2, 14, 31, 0.75)]) == [
        "Day 1: points 0-14, 6h 04m",
        "Day 2: points 14-31, 0h 45m",
    ]

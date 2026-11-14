import pytest

from trailhead.pace import leg_hours
from trailhead.plan import split_days

STEP = 5 / 111.19508  # one flat hour per leg along the equator


@pytest.fixture
def hours_track(make_track):
    def build(legs: int):
        return make_track(*[(0, index * STEP, 0) for index in range(legs + 1)])

    return build


def test_days_respect_the_limit(hours_track):
    days = split_days(hours_track(5), max_hours_per_day=2.5)
    assert [(day, first, last) for day, first, last, _ in days] == [(1, 0, 2), (2, 2, 4), (3, 4, 5)]


def test_a_day_may_fill_the_limit_exactly(hours_track):
    track = hours_track(4)
    legs = leg_hours(track)
    days = split_days(track, max_hours_per_day=legs[0] + legs[1])
    assert (days[0][1], days[0][2]) == (0, 2)


def test_no_day_exceeds_the_limit(hours_track):
    for limit in (1.5, 3, 4.2, 6):
        days = split_days(hours_track(13), max_hours_per_day=limit)
        assert all(hours <= limit for *_, hours in days), limit
        assert sum(hours for *_, hours in days) == pytest.approx(13, abs=0.05)


def test_one_long_leg_is_a_day_on_its_own(make_track):
    track = make_track((0, 0, 0), (0, 0.01, 0), (0, 0.5, 0), (0, 0.51, 0))
    days = split_days(track, max_hours_per_day=3)
    assert [(first, last) for _, first, last, _ in days] == [(0, 1), (1, 2), (2, 3)]

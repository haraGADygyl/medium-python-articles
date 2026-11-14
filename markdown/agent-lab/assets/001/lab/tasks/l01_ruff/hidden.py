import pytest

from trailhead.pace import leg_hours, naismith_hours
from trailhead.report import summarise
from trailhead.track import TrackError, parse_track


def test_fitness_still_scales_time():
    assert naismith_hours(10, 600, fitness=1.5) == pytest.approx(2.0)
    assert naismith_hours(10, 0, fitness=0.5) == pytest.approx(4.0)


def test_fitness_reaches_legs_and_summary(make_track):
    track = make_track((0, 0, 1000), (0, 0.01, 1300))
    assert leg_hours(track, fitness=2) == pytest.approx([x / 2 for x in leg_hours(track)])
    assert summarise(track, fitness=2).hours == pytest.approx(summarise(track).hours / 2)


def test_bad_numbers_are_still_track_errors():
    with pytest.raises(TrackError, match="line 3: not a number"):
        parse_track("lat,lon,ele\n0,0,0\n0,east,0\n")

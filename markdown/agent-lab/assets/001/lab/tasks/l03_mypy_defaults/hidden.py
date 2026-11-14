import pytest

from trailhead.plan import split_days
from trailhead.track import load_track, parse_track


def test_unnamed_track_without_default():
    assert parse_track("lat,lon,ele\n0,0,0\n0,0.01,0\n").name == "unnamed"
    assert parse_track("lat,lon,ele\n0,0,0\n0,0.01,0\n", default_name="ridge").name == "ridge"


def test_file_stem_still_names_the_track(write_track):
    assert load_track(write_track("lat,lon,ele\n0,0,0\n0,0.01,0\n", "musala.csv")).name == "musala"


def test_default_day_limit_is_seven_hours(make_track):
    step = 4.99 / 111.19508  # just under one flat hour per leg
    track = make_track(*[(0, index * step, 0) for index in range(9)])
    days = split_days(track)
    assert [(day, first, last) for day, first, last, _ in days] == [(1, 0, 7), (2, 7, 8)]
    assert [hours for *_, hours in days] == pytest.approx([6.99, 1.0])

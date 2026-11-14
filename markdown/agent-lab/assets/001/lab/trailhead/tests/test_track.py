import pytest

from trailhead.track import TrackError, load_track, parse_track

RILA = """\
# name: Seven Rila Lakes
# units: m
lat,lon,ele
42.2031,23.3205,2140

42.2049,23.3188,2196
42.2060,23.3170,2250
"""


def test_parses_name_and_points():
    track = parse_track(RILA)
    assert track.name == "Seven Rila Lakes"
    assert [point.ele for point in track.points] == [2140, 2196, 2250]
    assert track.points[1].lat == 42.2049


def test_feet_are_converted_to_metres():
    track = parse_track("# units: ft\nlat,lon,ele\n0,0,1000\n0,0.01,2000\n")
    assert [point.ele for point in track.points] == pytest.approx([304.8, 609.6])


def test_default_name_comes_from_the_file(write_track):
    path = write_track("lat,lon,ele\n0,0,0\n0,0.01,0\n", filename="vihren.csv")
    assert load_track(path).name == "vihren"


def test_bad_header():
    with pytest.raises(TrackError, match="line 1:"):
        parse_track("latitude,longitude,elevation\n0,0,0\n0,1,0\n")


def test_wrong_number_of_fields_reports_the_line():
    with pytest.raises(TrackError, match="line 3: expected 3 fields, got 2"):
        parse_track("lat,lon,ele\n0,0,0\n0,1\n")


def test_not_a_number():
    with pytest.raises(TrackError, match="not a number"):
        parse_track("lat,lon,ele\n0,0,0\n0,east,0\n")


def test_coordinates_out_of_range():
    with pytest.raises(TrackError, match="out of range"):
        parse_track("lat,lon,ele\n0,0,0\n0,181,0\n")


def test_needs_two_points():
    with pytest.raises(TrackError, match="at least two points"):
        parse_track("lat,lon,ele\n0,0,0\n")


def test_track_length_is_the_sum_of_legs(make_track):
    track = make_track((0, 0, 0), (0, 0.01, 0), (0, 0.03, 0))
    assert track.leg_lengths_km() == pytest.approx([1.11195, 2.2239], abs=1e-3)
    assert track.length_km() == pytest.approx(3.33585, abs=1e-3)

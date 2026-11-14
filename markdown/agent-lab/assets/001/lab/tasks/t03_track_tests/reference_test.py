import pytest

from trailhead.track import TrackError, load_track, parse_track


def test_name_points_comments_and_blank_lines():
    track = parse_track("# name: Ridge\n# a comment\n\nlat,lon,ele\n0,0,10\n\n0,0.01,20\n")
    assert track.name == "Ridge"
    assert [p.ele for p in track.points] == [10, 20]


def test_unnamed_and_default_name(write_track):
    assert parse_track("lat,lon,ele\n0,0,0\n0,1,0\n").name == "unnamed"
    assert parse_track("lat,lon,ele\n0,0,0\n0,1,0\n", default_name="x").name == "x"
    assert load_track(write_track("lat,lon,ele\n0,0,0\n0,1,0\n", "vihren.csv")).name == "vihren"


def test_feet_converted():
    track = parse_track("# units: ft\nlat,lon,ele\n0,0,1000\n0,1,0\n")
    assert track.points[0].ele == pytest.approx(304.8)


def test_unknown_units():
    with pytest.raises(TrackError, match="line 1:"):
        parse_track("# units: yards\nlat,lon,ele\n0,0,0\n0,1,0\n")


def test_bounds_are_inclusive():
    track = parse_track("lat,lon,ele\n90,180,0\n-90,-180,0\n")
    assert len(track.points) == 2
    with pytest.raises(TrackError, match="out of range"):
        parse_track("lat,lon,ele\n90.1,0,0\n0,0,0\n")


def test_line_numbers_count_comments_and_blanks():
    with pytest.raises(TrackError, match="^line 4: expected 3 fields"):
        parse_track("# c\n\nlat,lon,ele\n0,0\n0,1,0\n")


def test_needs_two_points():
    with pytest.raises(TrackError):
        parse_track("lat,lon,ele\n0,0,0\n")


def test_bad_header_and_number():
    with pytest.raises(TrackError, match="line 1:"):
        parse_track("a,b,c\n0,0,0\n0,1,0\n")
    with pytest.raises(TrackError, match="line 2: not a number"):
        parse_track("lat,lon,ele\nx,0,0\n0,1,0\n")

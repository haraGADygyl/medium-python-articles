from trailhead.track import parse_track


def test_parse():
    track = parse_track("# name: Ridge\nlat,lon,ele\n0,0,10\n0,0.01,20\n")
    assert track.name == "Ridge"
    assert len(track.points) == 2

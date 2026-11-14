import pytest

from trailhead.geo import compass_point, initial_bearing
from trailhead.report import summarise


@pytest.mark.parametrize(
    ("end", "expected"),
    [((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), 270), ((1, 1), 45), ((-1, -1), 225)],
)
def test_bearing(end, expected):
    assert initial_bearing(0, 0, *end) == pytest.approx(expected, abs=0.1)


def test_reported_ridge_heads_east(make_track):
    track = make_track((42.20, 23.30, 2000), (42.20, 23.375, 2100), (42.20, 23.45, 2050))
    assert compass_point(initial_bearing(42.20, 23.30, 42.20, 23.45)) == "E"
    assert summarise(track).heading == "E"


def test_heading_north_west(make_track):
    assert summarise(make_track((42.0, 23.0, 0), (42.05, 22.93, 0))).heading == "NW"

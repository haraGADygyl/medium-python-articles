import pytest

from trailhead.geo import compass_point, haversine_km, initial_bearing


def test_one_hundredth_of_a_degree_along_the_equator():
    assert haversine_km(0, 0, 0, 0.01) == pytest.approx(1.11195, abs=1e-4)


def test_distance_between_two_cities():
    sofia, plovdiv = (42.6977, 23.3219), (42.1354, 24.7453)
    assert haversine_km(*sofia, *plovdiv) == pytest.approx(132.5, abs=0.1)


def test_distance_is_symmetric_and_zero_for_the_same_point():
    there = haversine_km(42.1, 23.3, 42.2, 23.4)
    assert there == pytest.approx(haversine_km(42.2, 23.4, 42.1, 23.3))
    assert haversine_km(42.1, 23.3, 42.1, 23.3) == 0


@pytest.mark.parametrize(
    ("end", "expected"),
    [((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), 270)],
)
def test_bearing_along_the_axes(end, expected):
    assert initial_bearing(0, 0, *end) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("bearing", "name"),
    [(0, "N"), (22.4, "N"), (22.5, "NE"), (90, "E"), (200, "S"), (337.5, "N"), (359.9, "N")],
)
def test_compass_point(bearing, name):
    assert compass_point(bearing) == name

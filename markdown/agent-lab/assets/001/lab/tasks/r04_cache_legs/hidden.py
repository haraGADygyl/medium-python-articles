import pytest

import trailhead.geo
import trailhead.track
from trailhead.geo import haversine_km as real_haversine
from trailhead.report import summarise
from trailhead.track import Point, Track


@pytest.fixture
def calls(monkeypatch):
    count = {"n": 0}

    def counting(*args):
        count["n"] += 1
        return real_haversine(*args)

    monkeypatch.setattr(trailhead.geo, "haversine_km", counting)
    monkeypatch.setattr(trailhead.track, "haversine_km", counting, raising=False)
    return count


def zigzag(n: int) -> Track:
    return Track("zigzag", [Point(0, i * 0.01, 1000 + (i % 3) * 10) for i in range(n)])


def test_a_summary_computes_each_leg_once(calls):
    summarise(zigzag(50))
    assert calls["n"] <= 50  # 49 legs, plus at most one for the loop check


def test_repeated_calls_are_cached(calls):
    track = zigzag(20)
    track.length_km()
    track.leg_lengths_km()
    track.length_km()
    assert calls["n"] <= 19


def test_appending_a_point_is_seen():
    track = zigzag(3)
    before = track.length_km()
    track.points.append(Point(0, 0.05, 1000))
    assert len(track.leg_lengths_km()) == 3
    assert track.length_km() == pytest.approx(before + real_haversine(0, 0.02, 0, 0.05))


def test_replacing_the_points_is_seen():
    track = zigzag(5)
    track.length_km()
    track.points = [Point(0, 0, 0), Point(0, 0.01, 0)]
    assert track.leg_lengths_km() == pytest.approx([real_haversine(0, 0, 0, 0.01)])


def test_editing_a_point_in_place_is_seen():
    track = zigzag(3)
    track.length_km()
    track.points[2] = Point(0, 0.11, 1000)
    assert track.length_km() == pytest.approx(real_haversine(0, 0, 0, 0.11))


def test_callers_cannot_corrupt_the_cache():
    track = zigzag(4)
    legs = track.leg_lengths_km()
    legs.append(99.0)
    legs[0] = 99.0
    assert track.leg_lengths_km() == pytest.approx([real_haversine(0, 0, 0, 0.01)] * 3, rel=1e-6)


def test_tracks_still_compare_and_print_as_before():
    a, b = zigzag(5), zigzag(5)
    a.length_km()
    assert a == b
    assert repr(a) == repr(b)

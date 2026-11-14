from pathlib import Path

import pytest

from trailhead.track import Point, Track


@pytest.fixture
def make_track():
    """Build a Track straight from (lat, lon, ele) tuples."""

    def build(*points: tuple[float, float, float], name: str = "test") -> Track:
        return Track(name, [Point(*point) for point in points])

    return build


@pytest.fixture
def write_track(tmp_path):
    """Write track text to a file and return its path."""

    def write(text: str, filename: str = "walk.csv") -> Path:
        path = tmp_path / filename
        path.write_text(text, encoding="utf-8")
        return path

    return write

"""Reading tracks from the trailhead CSV format."""

from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from trailhead.geo import haversine_km

FEET_TO_METRES = 0.3048
HEADER = ["lat", "lon", "ele"]


class TrackError(ValueError):
    """A track that cannot be used; the message starts with the line number when known."""


@dataclass(frozen=True, slots=True)
class Point:
    lat: float
    lon: float
    ele: float  # metres


@dataclass(slots=True)
class Track:
    name: str
    points: list[Point] = field(default_factory=list)

    def leg_lengths_km(self) -> list[float]:
        """Length of each leg, the stretch between two consecutive points."""
        return [haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in pairwise(self.points)]

    def length_km(self) -> float:
        return sum(self.leg_lengths_km())


def parse_track(text: str, default_name: str | None = None) -> Track:
    """Parse a track; see the README for the format."""
    name = default_name or "unnamed"
    scale = 1.0
    points: list[Point] = []
    header_seen = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            key, sep, value = line.lstrip("#").partition(":")
            key, value = key.strip().lower(), value.strip()
            if sep and key == "name" and value:
                name = value
            elif sep and key == "units":
                if value not in ("m", "ft"):
                    raise TrackError(f"line {number}: unknown units {value!r}")
                scale = FEET_TO_METRES if value == "ft" else 1.0
            continue
        if not header_seen:
            if [column.strip() for column in line.split(",")] != HEADER:
                raise TrackError(f"line {number}: expected the header 'lat,lon,ele'")
            header_seen = True
            continue
        points.append(_parse_point(line, number, scale))
    if len(points) < 2:
        raise TrackError("a track needs at least two points")
    return Track(name, points)


def _parse_point(line: str, number: int, scale: float) -> Point:
    fields = [part.strip() for part in line.split(",")]
    if len(fields) != 3:
        raise TrackError(f"line {number}: expected 3 fields, got {len(fields)}")
    try:
        lat, lon, ele = (float(part) for part in fields)
    except ValueError:
        raise TrackError(f"line {number}: not a number") from None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise TrackError(f"line {number}: coordinates out of range")
    return Point(lat, lon, ele * scale)


def load_track(path: str | Path) -> Track:
    """Read a track file; without a ``# name:`` line the track is named after the file."""
    path = Path(path)
    return parse_track(path.read_text(encoding="utf-8"), default_name=path.stem)

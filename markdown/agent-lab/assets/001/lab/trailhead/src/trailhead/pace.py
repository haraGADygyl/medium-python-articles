"""Walking-time estimates."""

from itertools import pairwise
from math import exp

from trailhead.track import Track

FLAT_SPEED_KMH = 5.0
CLIMB_M_PER_HOUR = 600.0


def naismith_hours(distance_km: float, ascent_m: float, fitness: float = 1.0) -> float:
    """Naismith's rule: 5 km per hour on the flat plus one hour per 600 m of ascent.

    Descent adds nothing. ``fitness`` scales the result: 1.0 is an average walker,
    1.25 walks 25% faster, 0.8 slower.
    """
    if distance_km < 0 or ascent_m < 0:
        raise ValueError("distance and ascent must not be negative")
    if fitness <= 0:
        raise ValueError("fitness must be positive")
    return (distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR) / fitness


def tobler_kmh(grade: float) -> float:
    """Tobler's hiking function: walking speed in km/h on a slope.

    ``grade`` is rise over run (0.1 is a 10% climb, -0.1 a 10% descent). The
    fastest speed, 6 km/h, is on a gentle 5% descent.
    """
    return 6.0 * exp(-3.5 * abs(grade + 0.05))


def leg_hours(track: Track, fitness: float = 1.0) -> list[float]:
    """Naismith time for every leg, counting only the leg's own climb."""
    return [
        naismith_hours(km, max(b.ele - a.ele, 0.0), fitness)
        for (a, b), km in zip(pairwise(track.points), track.leg_lengths_km(), strict=True)
    ]

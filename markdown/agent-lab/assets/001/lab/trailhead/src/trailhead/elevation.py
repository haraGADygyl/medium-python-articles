"""Ascent, descent and gradient of a track."""

from collections.abc import Sequence
from itertools import pairwise

from trailhead.track import Track

DEFAULT_THRESHOLD_M = 3.0


def gain_and_loss(
    elevations: Sequence[float], threshold: float = DEFAULT_THRESHOLD_M
) -> tuple[float, float]:
    """Total ascent and descent in metres, each rounded to 0.1 m.

    A change counts once it reaches ``threshold`` metres from the last counted
    elevation, so GPS jitter is ignored but a long climb in small steps is not.
    """
    if threshold < 0:
        raise ValueError("threshold must not be negative")
    if not elevations:
        return 0.0, 0.0
    gain = loss = 0.0
    reference = elevations[0]
    for elevation in elevations[1:]:
        change = elevation - reference
        if change > 0 and change >= threshold:
            gain += change
            reference = elevation
        elif change < 0 and -change >= threshold:
            loss -= change
            reference = elevation
    return round(gain, 1), round(loss, 1)


def highest_and_lowest(track: Track) -> tuple[float, float]:
    """Highest and lowest elevation on the track, in metres."""
    elevations = [point.ele for point in track.points]
    return max(elevations), min(elevations)


def steepest_grade(track: Track) -> float:
    """Gradient of the steepest leg in percent, uphill or downhill, rounded to 0.1.

    Gradient is the change in elevation over the horizontal distance. Legs of
    zero length (repeated points) are skipped.
    """
    steepest = 0.0
    for (a, b), km in zip(pairwise(track.points), track.leg_lengths_km(), strict=True):
        if km == 0:
            continue
        steepest = max(steepest, abs(b.ele - a.ele) / (km * 1000) * 100)
    return round(steepest, 1)

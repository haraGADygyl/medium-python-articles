"""Splitting a track into days of walking."""

from trailhead.pace import leg_hours
from trailhead.track import Track

DEFAULT_MAX_HOURS = 7.0


def split_days(
    track: Track, max_hours_per_day: float = DEFAULT_MAX_HOURS, fitness: float = 1.0
) -> list[tuple[int, int, int, float]]:
    """Group consecutive legs into days of walking.

    Returns ``(day, first_point, last_point, hours)`` tuples: days count from 1,
    point indexes from 0, hours rounded to 0.01. A day never goes over
    ``max_hours_per_day`` unless a single leg on its own does.
    """
    if max_hours_per_day <= 0:
        raise ValueError("max_hours_per_day must be positive")
    days: list[tuple[int, int, int, float]] = []
    first, used = 0, 0.0
    for index, hours in enumerate(leg_hours(track, fitness)):
        if used > 0 and used + hours > max_hours_per_day:
            days.append((len(days) + 1, first, index, round(used, 2)))
            first, used = index, 0.0
        used += hours
    days.append((len(days) + 1, first, len(track.points) - 1, round(used, 2)))
    return days


def describe_plan(days: list[tuple[int, int, int, float]]) -> list[str]:
    """One line per day, for example ``Day 2: points 14-31, 6h 05m``."""
    lines: list[str] = []
    for day, first, last, hours in days:
        whole, minutes = divmod(round(hours * 60), 60)
        lines.append(f"Day {day}: points {first}-{last}, {whole}h {minutes:02d}m")
    return lines

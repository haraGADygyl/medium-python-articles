"""Summary statistics over a set of observations."""
from collections.abc import Iterable

from .models import Observation

MEASUREMENTS = ("wave_height_m", "water_temp_c", "wind_gust_ms", "battery_v")


def mean(values: list[float]) -> float | None:
    """Arithmetic mean, or None for no values."""
    return sum(values) / len(values) if values else None


def summarise(observations: Iterable[Observation]) -> dict[str, float | int | None]:
    """The mean of each measurement over the readings that have it.

    Each mean is rounded to 3 decimals once, after averaging, so rounding
    never biases the result. `count` is the number of observations.
    """
    rows = list(observations)
    summary: dict[str, float | int | None] = {"count": len(rows)}
    for name in MEASUREMENTS:
        values = [getattr(o, name) for o in rows if getattr(o, name) is not None]
        average = mean(values)
        summary[name] = None if average is None else round(average, 3)
    return summary

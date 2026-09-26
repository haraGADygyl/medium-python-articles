"""Group observations into hourly UTC windows."""
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from .models import Observation

HOUR = timedelta(hours=1)


def hour_start(moment: datetime) -> datetime:
    """The start of the UTC hour containing `moment`."""
    in_utc = moment.astimezone(timezone.utc)
    return in_utc.replace(minute=0, second=0, microsecond=0)


def in_window(moment: datetime, start: datetime) -> bool:
    """Whether `moment` falls in the window [start, start + 1 hour)."""
    return start <= moment < start + HOUR


def bucket_by_hour(observations: Iterable[Observation]) -> dict[datetime, list[Observation]]:
    """Map each UTC hour start to the observations recorded in that hour."""
    buckets: dict[datetime, list[Observation]] = defaultdict(list)
    for observation in observations:
        buckets[hour_start(observation.recorded_at)].append(observation)
    return dict(sorted(buckets.items()))


def select_window(observations: Iterable[Observation], start: datetime) -> list[Observation]:
    """The observations inside one hourly window."""
    return [o for o in observations if in_window(o.recorded_at, start)]

"""Publish observations as the JSON feed the met offices consume."""
import json
import math
from collections.abc import Iterable

from .models import Observation

FEED_FIELDS = ("wave_height_m", "water_temp_c", "wind_gust_ms", "battery_v")


def _feed_record(observation: Observation) -> dict:
    record = {
        "observation_id": observation.observation_id,
        "buoy_id": observation.buoy_id,
        "recorded_at": observation.recorded_at.isoformat(),
    }
    faults = []
    for name in FEED_FIELDS:
        value = getattr(observation, name)
        if isinstance(value, float) and not math.isfinite(value):
            record[name] = None
            faults.append(name)
        else:
            record[name] = value
    if faults:
        record["faults"] = faults
    return record


def to_feed_json(observations: Iterable[Observation]) -> str:
    """Strict JSON (RFC 8259): non-finite numbers are published as null + faults."""
    return json.dumps([_feed_record(o) for o in observations],
                      separators=(",", ":"), allow_nan=False)

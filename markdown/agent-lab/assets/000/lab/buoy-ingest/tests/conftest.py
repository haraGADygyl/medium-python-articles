from datetime import datetime, timezone

import pytest

from buoy_ingest.models import Observation, Sensor


@pytest.fixture
def make_observation():
    """Factory for observations with sensible defaults."""
    def build(observation_id=9007199254740993, recorded_at=None, **fields):
        defaults = dict(
            buoy_id="NE-08",
            recorded_at=recorded_at or datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc),
            lat=57.21621, lon=-2.37579,
            wave_height_m=3.5, water_temp_c=12.0, wind_gust_ms=10.7, battery_v=13.12,
            sensors=[Sensor("accelerometer", "ok", 1933), Sensor("gps", "ok", 318)],
        )
        defaults.update(fields)
        return Observation(observation_id=observation_id, **defaults)
    return build

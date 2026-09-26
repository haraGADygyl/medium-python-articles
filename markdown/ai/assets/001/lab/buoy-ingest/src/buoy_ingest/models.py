"""Plain data types shared by every module."""
from dataclasses import dataclass, field
from datetime import datetime


class ParseError(ValueError):
    """A raw observation could not be turned into an Observation."""


@dataclass(frozen=True)
class Sensor:
    tag: str
    status: str
    samples: int


@dataclass
class Observation:
    observation_id: int
    buoy_id: str
    recorded_at: datetime
    lat: float
    lon: float
    wave_height_m: float | None = None
    water_temp_c: float | None = None
    wind_gust_ms: float | None = None
    battery_v: float | None = None
    notes: str | None = None
    sensors: list[Sensor] = field(default_factory=list)

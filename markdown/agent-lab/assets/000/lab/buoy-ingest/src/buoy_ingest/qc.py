"""Quality control rules applied before an observation reaches the feed."""
from dataclasses import dataclass, field

from .models import Observation

RANGES = {
    "wave_height_m": (0.0, 25.0),
    "water_temp_c": (-2.0, 35.0),
    "wind_gust_ms": (0.0, 80.0),
}
BATTERY_FLOOR_V = 11.5


@dataclass
class QCResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def evaluate(observation: Observation) -> QCResult:
    """Fail an observation that is out of range, low on battery or has an offline sensor."""
    reasons = []
    for name, (low, high) in RANGES.items():
        value = getattr(observation, name)
        if value is not None and not low <= value <= high:
            reasons.append(f"{name} out of range: {value}")
    if observation.battery_v is not None and observation.battery_v < BATTERY_FLOOR_V:
        reasons.append(f"battery below {BATTERY_FLOOR_V} V: {observation.battery_v}")
    offline = [s.tag for s in observation.sensors if s.status == "offline"]
    if offline:
        reasons.append(f"offline sensors: {', '.join(offline)}")
    return QCResult(passed=not reasons, reasons=reasons)

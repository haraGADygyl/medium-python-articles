"""Turn raw JSON Lines and CSV rows into Observations."""
import csv
import io
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone

from .models import Observation, ParseError, Sensor

# ISO 8601 with a mandatory offset: ...+HH:MM, ...-HH:MM or ...Z.
_OFFSET = re.compile(r"(Z|[+-]\d{2}:\d{2})$")
_REQUIRED = ("observation_id", "buoy_id", "recorded_at", "position")


def parse_timestamp(text: str) -> datetime:
    """Parse an ISO 8601 timestamp that carries an explicit UTC offset.

    A timestamp without an offset is ambiguous (local time? UTC?) and is
    rejected with ParseError. The result is always in UTC.
    """
    if not isinstance(text, str) or not _OFFSET.search(text):
        raise ParseError(f"timestamp needs an explicit UTC offset: {text!r}")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ParseError(f"not an ISO 8601 timestamp: {text!r}") from exc
    return moment.astimezone(timezone.utc)


def _optional_float(record: dict, key: str) -> float | None:
    value = record.get(key)
    return None if value is None else float(value)


def from_record(record: dict) -> Observation:
    """Build an Observation from one decoded JSON object."""
    missing = [key for key in _REQUIRED if key not in record]
    if missing:
        raise ParseError(f"missing fields: {', '.join(missing)}")
    position = record["position"]
    return Observation(
        observation_id=int(record["observation_id"]),
        buoy_id=str(record["buoy_id"]),
        recorded_at=parse_timestamp(record["recorded_at"]),
        lat=float(position["lat"]),
        lon=float(position["lon"]),
        wave_height_m=_optional_float(record, "wave_height_m"),
        water_temp_c=_optional_float(record, "water_temp_c"),
        wind_gust_ms=_optional_float(record, "wind_gust_ms"),
        battery_v=_optional_float(record, "battery_v"),
        notes=record.get("notes"),
        sensors=[Sensor(s["tag"], s["status"], int(s["samples"]))
                 for s in record.get("sensors", [])],
    )


def parse_line(line: str) -> Observation:
    """Parse one JSON Lines record."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(record, dict):
        raise ParseError("a record must be a JSON object")
    return from_record(record)


def read_jsonl(lines: Iterable[str]) -> list[Observation]:
    """Parse every non-blank line; the first bad line raises ParseError."""
    return [parse_line(line) for line in lines if line.strip()]


def parse_csv(text: str) -> list[Observation]:
    """Parse the legacy CSV export some older buoys still upload.

    Columns: observation_id, buoy_id, recorded_at, lat, lon, wave_height_m
    """
    rows = csv.DictReader(io.StringIO(text))
    observations = []
    for row in rows:
        observations.append(Observation(
            observation_id=int(row["observation_id"]),
            buoy_id=row["buoy_id"],
            recorded_at=parse_timestamp(row["recorded_at"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            wave_height_m=float(row["wave_height_m"]) if row["wave_height_m"] else None,
        ))
    return observations


def merge_batches(batches: Iterable[Iterable[Observation]]) -> list[Observation]:
    """Concatenate upload batches, keeping the first copy of each observation."""
    seen: set[int] = set()
    merged = []
    for batch in batches:
        for observation in batch:
            if observation.observation_id in seen:
                continue
            seen.add(observation.observation_id)
            merged.append(observation)
    return merged

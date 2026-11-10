"""Turn the shared buoy payload into a TOML document and back.

TOML has two things JSON does not (a datetime type, comments) and lacks one thing
JSON has (null). So the conversion has to make two decisions:

- recorded_at, an ISO 8601 string in JSON, becomes a native TOML offset datetime
- notes, null in 95% of records, is dropped, because TOML cannot write it
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "payload"))
from make_payload import build  # noqa: E402

__all__ = ["build", "to_toml_doc", "from_toml_doc"]


def to_toml_row(row: dict) -> dict:
    """One record shaped for TOML: native datetime, no None values."""
    shaped = {key: value for key, value in row.items() if value is not None}
    shaped["recorded_at"] = datetime.fromisoformat(row["recorded_at"])
    return shaped


def from_toml_row(row: dict) -> dict:
    """Undo to_toml_row, which only works because we know the schema."""
    restored = dict(row)
    restored["recorded_at"] = row["recorded_at"].isoformat()
    restored.setdefault("notes", None)
    order = ("observation_id", "buoy_id", "recorded_at", "position",
             "wave_height_m", "water_temp_c", "wind_gust_ms", "battery_v",
             "qc_passed", "notes", "sensors")
    return {key: restored[key] for key in order}


def to_toml_doc(rows: list[dict]) -> dict:
    """A TOML document must be a table, so the records go under one key."""
    return {"observation": [to_toml_row(row) for row in rows]}


def from_toml_doc(doc: dict) -> list[dict]:
    return [from_toml_row(row) for row in doc["observation"]]

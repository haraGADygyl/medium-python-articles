"""The series payload to and from an Arrow table with an explicit schema."""
import sys
from datetime import datetime
from pathlib import Path

import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402,F401

SCHEMA = pa.schema([
    ("observation_id", pa.int64()),
    ("buoy_id", pa.string()),
    ("recorded_at", pa.timestamp("ms", tz="UTC")),
    ("position", pa.struct([("lat", pa.float64()), ("lon", pa.float64())])),
    ("wave_height_m", pa.float64()),
    ("water_temp_c", pa.float64()),
    ("wind_gust_ms", pa.float64()),
    ("battery_v", pa.float64()),
    ("qc_passed", pa.bool_()),
    ("notes", pa.string()),
    ("sensors", pa.list_(pa.struct([
        ("tag", pa.string()),
        ("status", pa.string()),
        ("samples", pa.int32()),
    ]))),
])


def to_table(rows: list[dict]) -> pa.Table:
    """Only the timestamp changes: Arrow wants a datetime, JSON carried a string."""
    shaped = [{**r, "recorded_at": datetime.fromisoformat(r["recorded_at"])}
              for r in rows]
    return pa.Table.from_pylist(shaped, schema=SCHEMA)


def from_table(table: pa.Table) -> list[dict]:
    return [{**r, "recorded_at": r["recorded_at"].isoformat()}
            for r in table.to_pylist()]

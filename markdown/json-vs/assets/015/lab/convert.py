"""The series payload to and from records that match buoy.avsc."""
import json
import sys
from datetime import datetime
from pathlib import Path

from fastavro import parse_schema

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402,F401

SCHEMA = parse_schema(json.loads((Path(__file__).parent / "buoy.avsc").read_text()))


def to_avro(row: dict) -> dict:
    """Only the timestamp changes: Avro wants a datetime, JSON carried a string."""
    return {**row, "recorded_at": datetime.fromisoformat(row["recorded_at"])}


def from_avro(record: dict) -> dict:
    return {**record, "recorded_at": record["recorded_at"].isoformat()}

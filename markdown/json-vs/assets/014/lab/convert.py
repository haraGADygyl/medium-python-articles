"""The series payload to and from the buoy.v1 protobuf messages."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import buoy_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402,F401

STATUS = {"ok": buoy_pb2.SENSOR_STATUS_OK, "degraded": buoy_pb2.SENSOR_STATUS_DEGRADED,
          "offline": buoy_pb2.SENSOR_STATUS_OFFLINE}
STATUS_NAME = {v: k for k, v in STATUS.items()}
MEASUREMENTS = ("wave_height_m", "water_temp_c", "wind_gust_ms", "battery_v")


def to_proto(row: dict, out: buoy_pb2.Observation) -> None:
    out.observation_id = row["observation_id"]
    out.buoy_id = row["buoy_id"]
    out.recorded_at.FromDatetime(datetime.fromisoformat(row["recorded_at"]))
    out.position.lat = row["position"]["lat"]
    out.position.lon = row["position"]["lon"]
    for name in MEASUREMENTS:
        if row[name] is not None:
            setattr(out, name, row[name])
    out.qc_passed = row["qc_passed"]
    if row["notes"] is not None:
        out.notes = row["notes"]
    for sensor in row["sensors"]:
        out.sensors.add(tag=sensor["tag"], status=STATUS[sensor["status"]],
                        samples=sensor["samples"])


def to_batch(rows: list[dict]) -> buoy_pb2.Batch:
    batch = buoy_pb2.Batch()
    for row in rows:
        to_proto(row, batch.observations.add())
    return batch


def from_proto(obs: buoy_pb2.Observation) -> dict:
    return {
        "observation_id": obs.observation_id,
        "buoy_id": obs.buoy_id,
        "recorded_at": obs.recorded_at.ToDatetime(tzinfo=timezone.utc).isoformat(),
        "position": {"lat": obs.position.lat, "lon": obs.position.lon},
        **{name: getattr(obs, name) if obs.HasField(name) else None for name in MEASUREMENTS},
        "qc_passed": obs.qc_passed,
        "notes": obs.notes if obs.HasField("notes") else None,
        "sensors": [{"tag": s.tag, "status": STATUS_NAME[s.status], "samples": s.samples}
                    for s in obs.sensors],
    }

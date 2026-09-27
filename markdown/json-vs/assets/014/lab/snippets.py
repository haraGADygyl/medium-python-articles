"""The Python snippet the article shows (writes observation.bin)."""
import json
from datetime import datetime
from pathlib import Path

import buoy_pb2

reading = {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5,
    "water_temp_c": 12.0,
    "wind_gust_ms": 10.7,
    "battery_v": 13.12,
    "qc_passed": True,
    "notes": None,
    "sensors": [
        {"tag": "accelerometer", "status": "offline", "samples": 1933},
        {"tag": "thermistor", "status": "degraded", "samples": 1866},
        {"tag": "anemometer", "status": "degraded", "samples": 318},
    ],
}
STATUS = {"ok": buoy_pb2.SENSOR_STATUS_OK,
          "degraded": buoy_pb2.SENSOR_STATUS_DEGRADED,
          "offline": buoy_pb2.SENSOR_STATUS_OFFLINE}

observation = buoy_pb2.Observation(
    observation_id=reading["observation_id"],
    buoy_id=reading["buoy_id"],
    position=buoy_pb2.Position(**reading["position"]),
    wave_height_m=reading["wave_height_m"],
    water_temp_c=reading["water_temp_c"],
    wind_gust_ms=reading["wind_gust_ms"],
    battery_v=reading["battery_v"],
    qc_passed=reading["qc_passed"],
    sensors=[buoy_pb2.Sensor(tag=s["tag"], status=STATUS[s["status"]],
                             samples=s["samples"]) for s in reading["sensors"]],
)
observation.recorded_at.FromDatetime(datetime.fromisoformat(reading["recorded_at"]))

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_proto = observation.SerializeToString()
print(len(as_json), len(as_proto))  # 427 142
print(as_proto[:16].hex(" "))
# 08 81 80 80 80 80 80 80 10 12 05 4e 45 2d 30 38
Path("observation.bin").write_bytes(as_proto)

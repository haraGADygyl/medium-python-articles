import json
from operator import attrgetter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(Path("buoy.schema.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())

wire = """{"observation_id": 9007199254740993, "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00",
  "position": {"lat": 57.21621, "lon": -2.37579},
  "wave_height_m": -999.0, "water_temp_c": 12.0, "wind_gust_ms": 10.7,
  "battery_v": 13.12, "qc_passed": "false", "note": "drifted off station",
  "sensors": [{"tag": "accelerometer", "status": "OFFLINE", "samples": 1933}]}"""

reading = json.loads(wire)

print(bool(reading["qc_passed"]), reading.get("notes"))  # True None

for error in sorted(validator.iter_errors(reading), key=attrgetter("json_path")):
    print(f"{error.json_path}: {error.message}")

# $: Additional properties are not allowed ('note' was unexpected)
# $.qc_passed: 'false' is not of type 'boolean'
# $.recorded_at: '2026-02-11T00:00:00' is not a 'date-time'
# $.sensors[0].status: 'OFFLINE' is not one of ['ok', 'degraded', 'offline']
# $.wave_height_m: -999.0 is less than the minimum of 0

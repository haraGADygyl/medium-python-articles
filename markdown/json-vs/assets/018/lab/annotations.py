"""`format` and `default` are annotations in draft 2020-12, not checks.

Run it in two environments to see the format checker change under you:

    .venv/bin/python annotations.py     # jsonschema + rfc3339-validator
    bare/bin/python annotations.py      # jsonschema only
"""
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).parent
schema = json.loads((HERE / "buoy.schema.json").read_text())

try:
    extra = version("rfc3339-validator")
except PackageNotFoundError:
    extra = "not installed"

print(f"jsonschema {version('jsonschema')}, rfc3339-validator {extra}")
print(f"formats this FormatChecker knows: {sorted(FormatChecker().checkers)}")

reading = {
    "observation_id": 9007199254740993, "buoy_id": "NE-08",
    "recorded_at": "yesterday at noon",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5, "water_temp_c": 12.0, "wind_gust_ms": 10.7,
    "battery_v": 13.12, "qc_passed": True,
    "sensors": [{"tag": "gps", "status": "ok", "samples": 64}],
}

annotating = Draft202012Validator(schema)
asserting = Draft202012Validator(schema, format_checker=FormatChecker())
print(f"'yesterday at noon', no format checker:   valid={annotating.is_valid(reading)}")
print(f"'yesterday at noon', FormatChecker():     valid={asserting.is_valid(reading)}")

dated = reading | {"recorded_at": "2026-02-11T00:00:00+00:00"}
asserting.validate(dated)
print(f"no 'notes' key, schema says default null: valid, 'notes' in record "
      f"after validate()={'notes' in dated}")

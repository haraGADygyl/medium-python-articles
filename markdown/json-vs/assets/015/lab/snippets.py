"""The Python snippet the article shows (writes buoy.avro)."""
import io
import json
from datetime import datetime
from pathlib import Path

from fastavro import json_writer, parse_schema, reader, schemaless_writer, writer

schema = parse_schema(json.loads(Path("buoy.avsc").read_text()))

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
record = {**reading, "recorded_at": datetime.fromisoformat(reading["recorded_at"])}

body = io.BytesIO()
schemaless_writer(body, schema, record)
as_json = json.dumps(reading, separators=(",", ":")).encode()
print(len(as_json), len(body.getvalue()))  # 427 121
print(body.getvalue()[:16].hex(" "))
# 82 80 80 80 80 80 80 20 0a 4e 45 2d 30 38 80 90

with open("buoy.avro", "wb") as out:
    writer(out, schema, [record])
with open("buoy.avro", "rb") as source:
    avro_file = reader(source)
    print(avro_file.writer_schema["name"], next(avro_file)["wave_height_m"])
    # buoy.v1.Observation 3.5

as_avro_json = io.StringIO()
json_writer(as_avro_json, schema, [record])
text = as_avro_json.getvalue()
print(text[text.index('"recorded_at"'):text.index('"qc_passed"')])
# "recorded_at": 1770768000000, "position": {"lat": 57.21621, "lon": -2.37579},
# "wave_height_m": {"double": 3.5}, "water_temp_c": {"double": 12.0}, ...

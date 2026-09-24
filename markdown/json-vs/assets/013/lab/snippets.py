"""The snippets the article shows, run end to end."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import cbor2

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

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_cbor = cbor2.dumps(reading)

print(len(as_json), len(as_cbor))
print(as_cbor[:16].hex(" "))
print(cbor2.loads(as_cbor) == reading)

print("--- tags")
tagged = {
    "recorded_at": datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc),
    "trace_id": 0x9C3E1F0A6B2D48E7A15C0F93D4B8E261,
    "battery_v": Decimal("13.10"),
    "signature": bytes(range(64)),
}

blob = cbor2.dumps(tagged, datetime_as_timestamp=True)
print(len(blob))
print(cbor2.loads(blob) == tagged)

try:
    json.dumps(tagged)
except TypeError as exc:
    print(f"TypeError: {exc}")

print("--- unknown tag")
future = cbor2.loads(cbor2.dumps(cbor2.CBORTag(40001, "HB-214")))
print(repr(future))
print(cbor2.dumps(future).hex(" "))

print("--- determinism")
from_device = {"buoy_id": "NE-08", "wave_height_m": 3.5}
from_archive = {"wave_height_m": 3.5, "buoy_id": "NE-08"}


def fingerprint(blob: bytes) -> str:
    """First twelve hex digits of the SHA-256."""
    return hashlib.sha256(blob).hexdigest()[:12]


print(from_device == from_archive)
print(fingerprint(cbor2.dumps(from_device)),
      fingerprint(cbor2.dumps(from_archive)))
print(fingerprint(cbor2.dumps(from_device, canonical=True)),
      fingerprint(cbor2.dumps(from_archive, canonical=True)))

print(cbor2.dumps(3.5).hex(" "))
print(cbor2.dumps(3.5, canonical=True).hex(" "))


"""The snippets the article shows, run end to end."""
import json
import struct
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bson
from bson.codec_options import CodecOptions

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
as_bson = bson.encode(reading)

print(len(as_json), len(as_bson))
print(as_bson[:24])
print(bson.encode({"tags": ["gps", "thermistor"]}))

print("--- walk")
FIXED = {0x01: 8, 0x08: 1, 0x09: 8, 0x0A: 0, 0x10: 4, 0x12: 8}


def find_field(doc: bytes, wanted: str) -> tuple[int, int]:
    """Offset of `wanted`'s value, and how many bytes were read to find it."""
    offset, touched = 4, 4                     # skip the document length
    while doc[offset] != 0x00:
        kind = doc[offset]
        key_end = doc.index(b"\x00", offset + 1)
        key = doc[offset + 1:key_end].decode()
        touched += key_end - offset + 1
        value_at = key_end + 1
        if key == wanted:
            return value_at, touched
        if kind in FIXED:
            size = FIXED[kind]
        else:                                  # string, document or array
            (length,) = struct.unpack_from("<i", doc, value_at)
            touched += 4
            size = length + 4 if kind == 0x02 else length
        offset = value_at + size
    raise KeyError(wanted)


value_at, touched = find_field(as_bson, "qc_passed")
print(as_bson[value_at], touched, len(as_bson))
print(as_json.index(b'"qc_passed":') + len(b'"qc_passed":'))

print("--- types")
recorded = datetime(2026, 2, 11, 5, 15, 30, 123456,
                    tzinfo=timezone(timedelta(hours=1)))
typed = {"recorded_at": recorded, "battery_v": bson.Decimal128("13.10")}
back = bson.decode(bson.encode(typed), CodecOptions(tz_aware=True))
print(back["recorded_at"])
print(back["battery_v"].to_decimal() == Decimal("13.10"))

try:
    bson.encode({"trace_id": 2**64})
except OverflowError as exc:
    print(f"OverflowError: {exc}")

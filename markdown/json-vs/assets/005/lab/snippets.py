"""The snippets the article shows, run end to end."""
import json
import math
import struct

import ubjson

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
as_ubjson = ubjson.dumpb(reading)

print(len(as_json), len(as_ubjson))
print(as_ubjson[:40])
print(ubjson.loadb(as_ubjson) == reading)

print("--- float32")
smaller = ubjson.dumpb(reading, no_float32=False)
print(len(smaller), ubjson.loadb(smaller)["battery_v"])

print("--- typed array")
spectrum = [round(0.01 * band * math.exp(-band / 12), 4) for band in range(64)]

generic = ubjson.dumpb(spectrum)
typed = b"[$D#U" + bytes([len(spectrum)]) + struct.pack(">64d", *spectrum)
text = json.dumps(spectrum, separators=(",", ":")).encode()

print(len(text), len(generic), len(typed))
print(ubjson.loadb(typed) == spectrum)

print("--- edges")
print(ubjson.dumpb(math.nan), ubjson.loadb(ubjson.dumpb(math.inf)))
print(ubjson.dumpb(2**64))

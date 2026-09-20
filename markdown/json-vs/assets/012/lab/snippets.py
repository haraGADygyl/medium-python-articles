"""The snippets the article shows, run end to end."""
import json
from datetime import datetime, timezone

import msgpack

reading = {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5,
    "qc_passed": True,
    "notes": None,
}

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_msgpack = msgpack.packb(reading)
print(len(as_json), len(as_msgpack))
print(as_msgpack[:14])
print(msgpack.unpackb(as_msgpack, raw=False) == reading)
print(msgpack.unpackb(as_msgpack, raw=False)["observation_id"])

stamped = msgpack.packb({"recorded_at": datetime(2026, 2, 11, 4, 15,
                                                 tzinfo=timezone.utc)},
                        datetime=True)
print(len(stamped),
      msgpack.unpackb(stamped, raw=False, timestamp=3)["recorded_at"])

stream = b"".join(msgpack.packb(r) for r in [reading, reading, reading])
unpacker = msgpack.Unpacker(raw=False)
unpacker.feed(stream[:40])
print([r["buoy_id"] for r in unpacker])
unpacker.feed(stream[40:])
print(sum(1 for _ in unpacker))

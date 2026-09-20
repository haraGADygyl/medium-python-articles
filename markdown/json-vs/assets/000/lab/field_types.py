"""What MessagePack can express that JSON cannot, on one record."""
import json
from datetime import datetime, timezone

import msgpack

BIG_ID = 9007199254740993          # one past 2**53
STAMP = datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc)


def show(label: str, as_json: bytes, as_msgpack: bytes) -> None:
    print(f"{label:<22}{len(as_json):>6} B json{len(as_msgpack):>6} B msgpack")


def main() -> None:
    show("64-bit id",
         json.dumps(BIG_ID).encode(), msgpack.packb(BIG_ID))
    show("timestamp",
         json.dumps(STAMP.isoformat()).encode(),
         msgpack.packb(STAMP, datetime=True))
    show("float 2.37",
         json.dumps(2.37).encode(), msgpack.packb(2.37))
    show("true", json.dumps(True).encode(), msgpack.packb(True))
    show("null", json.dumps(None).encode(), msgpack.packb(None))
    show("key 'wave_height_m'",
         json.dumps("wave_height_m").encode(),
         msgpack.packb("wave_height_m"))

    back = msgpack.unpackb(msgpack.packb({"observation_id": BIG_ID}))
    print()
    print(f"id survives msgpack round trip: "
          f"{back['observation_id'] == BIG_ID} ({back['observation_id']})")
    stamp_back = msgpack.unpackb(msgpack.packb(STAMP, datetime=True),
                                 timestamp=3)
    print(f"timestamp comes back as: {stamp_back!r}")
    print(f"json has no such type; it returns "
          f"{json.loads(json.dumps(STAMP.isoformat()))!r}")


if __name__ == "__main__":
    main()

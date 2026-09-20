"""Where MessagePack wins and loses, by field type."""
import gzip
import json
import random

import msgpack

RECORDS = 50000
SEED = 20260920
WORDS = ["harbour", "buoy", "drifted", "off", "station", "mooring", "swell"]


def numeric(rng: random.Random) -> dict:
    """Rounded floats, the shape sensor data usually has."""
    return {"a": round(rng.uniform(0, 100), 2),
            "b": round(rng.uniform(0, 100), 1),
            "c": round(rng.uniform(0, 100), 2)}


def integers(rng: random.Random) -> dict:
    """Small integers, where varint encoding is at its best."""
    return {"a": rng.randrange(0, 200), "b": rng.randrange(0, 200),
            "c": rng.randrange(0, 200)}


def flags(rng: random.Random) -> dict:
    """Booleans and nulls: one byte each in MessagePack."""
    return {"a": rng.random() > 0.5, "b": None,
            "c": rng.random() > 0.5}


def text(rng: random.Random) -> dict:
    """Free text, where both formats store the same bytes."""
    return {"a": " ".join(rng.choices(WORDS, k=6)),
            "b": " ".join(rng.choices(WORDS, k=6)),
            "c": " ".join(rng.choices(WORDS, k=6))}


SHAPES = {"rounded floats": numeric, "small integers": integers,
          "booleans + nulls": flags, "free text": text}


def main() -> None:
    print(f"{RECORDS} records of each shape, 3 fields per record")
    print(f"{'shape':<18}{'JSON':>11}{'msgpack':>11}{'raw diff':>10}"
          f"{'JSON gz':>11}{'msgpack gz':>12}{'gz diff':>9}")
    for label, maker in SHAPES.items():
        rng = random.Random(SEED)
        rows = [maker(rng) for _ in range(RECORDS)]
        as_json = json.dumps(rows, separators=(",", ":")).encode()
        as_msgpack = msgpack.packb(rows)
        jz, mz = gzip.compress(as_json, 9), gzip.compress(as_msgpack, 9)
        print(f"{label:<18}{len(as_json):>11,}{len(as_msgpack):>11,}"
              f"{100 * (1 - len(as_msgpack) / len(as_json)):>9.1f}%"
              f"{len(jz):>11,}{len(mz):>12,}"
              f"{100 * (1 - len(mz) / len(jz)):>8.1f}%")


if __name__ == "__main__":
    main()

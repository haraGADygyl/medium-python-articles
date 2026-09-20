"""The shared payload for the JSON vs. series: harbour buoy observations.

Deterministic — the same seed produces the same bytes on every machine, so the
numbers in one article are comparable with the numbers in every other one.

    python3 make_payload.py            # 50000 records -> buoy.json, buoy.jsonl
    python3 make_payload.py --records 1 --pretty
"""
import argparse
import json
import random
from datetime import datetime, timedelta, timezone

SEED = 20260920
BUOYS = ["HB-214", "HB-215", "HB-301", "NE-07", "NE-08", "SW-42"]
SENSOR_TAGS = ["accelerometer", "thermistor", "anemometer", "gps"]
STATUSES = ["ok", "ok", "ok", "degraded", "offline"]
# Deliberately past 2**53, so the 64-bit integer article has a real casualty.
FIRST_OBSERVATION_ID = 9007199254740993


def make_record(index: int, rng: random.Random, start: datetime) -> dict:
    """One observation: mixed types, one nested object, one array of objects."""
    return {
        "observation_id": FIRST_OBSERVATION_ID + index,
        "buoy_id": rng.choice(BUOYS),
        "recorded_at": (start + timedelta(minutes=10 * index)).isoformat(),
        "position": {
            "lat": round(rng.uniform(56.9, 57.4), 5),
            "lon": round(rng.uniform(-2.6, -1.8), 5),
        },
        "wave_height_m": round(rng.uniform(0.2, 7.5), 2),
        "water_temp_c": round(rng.uniform(3.0, 14.0), 1),
        "wind_gust_ms": round(rng.uniform(0.0, 31.0), 1),
        "battery_v": round(rng.uniform(11.4, 13.2), 2),
        "qc_passed": rng.random() > 0.08,
        "notes": None if rng.random() > 0.05 else "drifted off station",
        "sensors": [
            {"tag": tag,
             "status": rng.choice(STATUSES),
             "samples": rng.randrange(64, 2048)}
            for tag in SENSOR_TAGS[:rng.randrange(2, 5)]
        ],
    }


def build(records: int) -> list[dict]:
    """The whole dataset, identical for a given record count."""
    rng = random.Random(SEED)
    start = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
    return [make_record(i, rng, start) for i in range(records)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=50000)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    data = build(args.records)
    if args.pretty:
        print(json.dumps(data[0], indent=2))
        return
    with open("buoy.json", "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    with open("buoy.jsonl", "w") as handle:
        for row in data:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(f"{len(data)} records -> buoy.json, buoy.jsonl")


if __name__ == "__main__":
    main()

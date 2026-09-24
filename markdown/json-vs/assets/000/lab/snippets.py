"""The snippets the article shows, run end to end (writes two small files)."""
import json
from collections.abc import Iterator
from pathlib import Path

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
batch = [reading, {**reading, "qc_passed": False}, reading]

as_json = json.dumps(batch, separators=(",", ":"))
as_jsonl = "".join(json.dumps(row, separators=(",", ":")) + "\n"
                   for row in batch)
Path("readings.json").write_text(as_json)
Path("readings.jsonl").write_text(as_jsonl)

print(len(as_json), len(as_jsonl))
print(as_json[:2], as_json[-2:])
print(as_jsonl.count("\n"))

try:
    json.loads(as_jsonl)
except json.JSONDecodeError as exc:
    print(f"JSONDecodeError: {exc}")

print("--- stream")


def failed_qc(path: Path) -> Iterator[dict]:
    """Yield the readings that failed QC, holding one line at a time."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if not row["qc_passed"]:
                    yield row


print(sum(1 for _ in failed_qc(Path("readings.jsonl"))))

print("--- append")
late_reading = {**reading, "observation_id": 9007199254740996}

with open("readings.jsonl", "a", encoding="utf-8") as handle:
    handle.write(json.dumps(late_reading, separators=(",", ":")) + "\n")

rows = json.loads(Path("readings.json").read_text())
rows.append(late_reading)
Path("readings.json").write_text(json.dumps(rows, separators=(",", ":")))

print(sum(1 for _ in open("readings.jsonl")), len(rows))

print("--- u2028")
note = json.dumps({"notes": "hull scraped mooring checked"},
                  ensure_ascii=False)
print(len(note.split("\n")), len(note.splitlines()))
print(json.dumps({"notes": "a b"}))

"""JSON vs. JSON Lines on the shared buoy payload.

Each read experiment runs in a fresh interpreter so peak memory is its own:
    python3 measure.py
"""
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zstandard

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RUNS = 5
RECORDS = 50000

# Each reader counts the observations that failed QC, the smallest real question
# that still needs every record.
READERS = {
    "json.load, whole array": """
with open(PATH) as handle:
    rows = json.load(handle)
first = rows[0]
FIRST_AT = now()
failed = sum(1 for row in rows if not row["qc_passed"])
""",
    "jsonl, list of all lines": """
with open(PATH) as handle:
    rows = [json.loads(line) for line in handle]
first = rows[0]
FIRST_AT = now()
failed = sum(1 for row in rows if not row["qc_passed"])
""",
    "jsonl, one line at a time": """
failed = 0
FIRST_AT = None
with open(PATH) as handle:
    for line in handle:
        row = json.loads(line)
        if FIRST_AT is None:
            FIRST_AT = now()
        failed += not row["qc_passed"]
""",
}

# VmHWM, not ru_maxrss: ru_maxrss survives exec, so a child forked from this
# (large) process would report the parent's peak instead of its own.
HARNESS = """
import json, sys, time
PATH = sys.argv[1]
now = time.perf_counter


def status_kb(field):
    with open("/proc/self/status") as proc:
        for entry in proc:
            if entry.startswith(field):
                return int(entry.split()[1])


base_kb = status_kb("VmRSS:")
started = now()
{body}
total = now() - started
print((FIRST_AT - started) * 1000, total * 1000,
      status_kb("VmHWM:") - base_kb, failed)
"""


def run_reader(body: str, path: Path) -> tuple[float, float, float, int]:
    """Best-of-RUNS first-record ms and total ms; peak extra RSS in MB."""
    best_first = best_total = float("inf")
    peak_mb, failed = 0.0, 0
    for _ in range(RUNS):
        out = subprocess.run(
            [sys.executable, "-c", HARNESS.format(body=body), str(path)],
            capture_output=True, text=True, check=True).stdout.split()
        first_ms, total_ms, kb, failed = (float(out[0]), float(out[1]),
                                          int(out[2]), int(out[3]))
        best_first = min(best_first, first_ms)
        best_total = min(best_total, total_ms)
        peak_mb = kb / 1024
    return best_first, best_total, peak_mb, failed


def main() -> None:
    data = build(RECORDS)
    extra = build(RECORDS + 1)[-1]
    work = Path(tempfile.mkdtemp(prefix="jsonl-lab-"))
    as_json = work / "buoy.json"
    as_jsonl = work / "buoy.jsonl"
    as_json.write_text(json.dumps(data, separators=(",", ":")))
    as_jsonl.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n"
                                for row in data))

    print(f"{RECORDS} buoy records, best of {RUNS}, Python "
          f"{sys.version.split()[0]}")
    print()
    print(f"{'file':<12}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for path in (as_json, as_jsonl):
        blob = path.read_bytes()
        print(f"{path.name:<12}{len(blob):>12,}"
              f"{len(gzip.compress(blob, 9)):>12,}"
              f"{len(zstandard.ZstdCompressor(level=3).compress(blob)):>12,}")

    print()
    print(f"{'reader':<28}{'first record ms':>16}{'all records ms':>16}"
          f"{'peak extra MB':>15}{'failed QC':>11}")
    for label, body in READERS.items():
        path = as_json if label.startswith("json.load") else as_jsonl
        first, total, peak, failed = run_reader(body, path)
        print(f"{label:<28}{first:>16.2f}{total:>16.1f}{peak:>15.1f}"
              f"{failed:>11,}")

    print()
    print("append one record to the 50000-record file")
    originals = {path: path.read_bytes() for path in (as_json, as_jsonl)}

    def append_json() -> int:
        rows = json.loads(as_json.read_text())
        rows.append(extra)
        return as_json.write_text(json.dumps(rows, separators=(",", ":")))

    def append_jsonl() -> int:
        with open(as_jsonl, "a") as handle:
            return handle.write(
                json.dumps(extra, separators=(",", ":")) + "\n")

    for path, append in ((as_json, append_json), (as_jsonl, append_jsonl)):
        fastest, written = float("inf"), 0
        for _ in range(RUNS):
            path.write_bytes(originals[path])
            started = time.perf_counter()
            written = append()
            fastest = min(fastest, (time.perf_counter() - started) * 1000)
        print(f"  {path.name:<12}{fastest:>10.3f} ms{written:>14,} bytes written")

    for path in (as_json, as_jsonl):
        os.remove(path)
    work.rmdir()


if __name__ == "__main__":
    main()

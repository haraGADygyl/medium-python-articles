"""JSONL splits at any newline, so N workers can each take a byte range.

A JSON array has no such boundary: finding where record 25,000 starts means
parsing everything before it.
"""
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RUNS = 5
WORKERS = [1, 2, 4, 6]


def count_failed(path: str, start: int, stop: int) -> int:
    """Count failed-QC records whose line starts inside [start, stop)."""
    failed = 0
    with open(path, "rb") as handle:
        if start:
            handle.seek(start - 1)
            handle.readline()           # finish the line the range landed in
        while handle.tell() < stop:
            line = handle.readline()
            if not line:
                break
            failed += not json.loads(line)["qc_passed"]
    return failed


def split_count(path: str, workers: int) -> int:
    """Fan the file out over `workers` processes by byte range."""
    size = os.path.getsize(path)
    edges = [size * i // workers for i in range(workers + 1)]
    with ProcessPoolExecutor(workers) as pool:
        parts = pool.map(count_failed, [path] * workers, edges[:-1], edges[1:])
        return sum(parts)


def main() -> None:
    rows = build(50000)
    work = Path(tempfile.mkdtemp(prefix="jsonl-par-"))
    path = work / "buoy.jsonl"
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n"
                            for r in rows))
    print(f"50000 records, {os.cpu_count()} CPUs, best of {RUNS}, "
          f"including process start-up")
    baseline = None
    for workers in WORKERS:
        fastest, failed = float("inf"), 0
        for _ in range(RUNS):
            started = time.perf_counter()
            failed = split_count(str(path), workers)
            fastest = min(fastest, (time.perf_counter() - started) * 1000)
        baseline = baseline or fastest
        print(f"  {workers} worker{'s' if workers > 1 else ' '}  "
              f"{fastest:8.1f} ms  {baseline / fastest:4.1f}x  "
              f"failed QC {failed:,}")
    path.unlink()
    work.rmdir()


if __name__ == "__main__":
    main()

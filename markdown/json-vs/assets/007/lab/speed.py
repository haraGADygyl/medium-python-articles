"""CSON parsers on data. JSON is valid CSON, so every parser reads the payload.

5,000 records rather than the series' 50,000: Python's cson takes about 140 s
for 5,000, and the full payload would take over twenty minutes.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import cson

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "payload"))

from make_payload import build                              # noqa: E402

RECORDS = 5000


def python_ms(fn, text: str, runs: int) -> tuple[float, object]:
    fastest, result = float("inf"), None
    for _ in range(runs):
        started = time.perf_counter()
        result = fn(text)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
    return fastest, result


def node_ms(mode: str, text: str, runs: int) -> float:
    return min(float(subprocess.run(
        ["node", str(HERE / "readers.js"), mode, "--time"], input=text,
        capture_output=True, text=True, check=True, cwd=HERE).stdout)
        for _ in range(runs))


def main() -> None:
    data = build(RECORDS)
    text = json.dumps(data, separators=(",", ":"))
    print(f"{RECORDS} records, {len(text):,} bytes of JSON read as CSON")
    json_ms, _ = python_ms(json.loads, text, 5)
    cson_ms, value = python_ms(cson.loads, text, 1)
    node_json = node_ms("json", text, 5)
    rows = [
        ("Python json.loads", json_ms, json_ms, 5),
        ("Python cson 0.8", cson_ms, json_ms, 1),
        ("Node JSON.parse", node_json, node_json, 5),
        ("npm cson-parser 4.0.9", node_ms("cson-parser", text, 3),
         node_json, 3),
        ("CoffeeScript 2.7.0 eval", node_ms("coffeescript", text, 3),
         node_json, 3),
    ]
    print(f"{'parser':<26}{'ms':>11}{'vs native':>11}  runs")
    for label, ms, base, runs in rows:
        print(f"{label:<26}{ms:>11.1f}{ms / base:>10.0f}x  {runs:>4}")
    print(f"Python cson returned the same data: {value == data}")


if __name__ == "__main__":
    main()

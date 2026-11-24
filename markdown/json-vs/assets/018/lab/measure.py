"""What validation costs: 50,000 records, parsed and then validated.

    python3 measure.py [records] > output-measure.txt

Best of five, GC paused. Every validator is built once, outside the timed
loop, except the last row, which calls jsonschema.validate() per record the
way most tutorials show it.
"""
import gc
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path

import fastjsonschema
import jsonschema
from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "payload"))
from make_payload import build  # noqa: E402

HERE = Path(__file__).parent


def best_of(runs: int, work) -> float:
    """Fastest wall time in milliseconds."""
    timings = []
    gc.disable()

    try:
        for _ in range(runs):
            start = time.perf_counter()
            work()
            timings.append((time.perf_counter() - start) * 1000)
    finally:
        gc.enable()

    return min(timings)


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
    records = build(count)
    lines = [json.dumps(r, separators=(",", ":")) for r in records]
    schema = json.loads((HERE / "buoy.schema.json").read_text())
    schema_bytes = len(json.dumps(schema, separators=(",", ":")).encode())

    print(f"jsonschema {version('jsonschema')}, fastjsonschema "
          f"{version('fastjsonschema')}, rfc3339-validator "
          f"{version('rfc3339-validator')}")
    print(f"{count:,} records, {sum(map(len, lines)):,} bytes of JSON Lines; "
          f"schema {schema_bytes:,} bytes compact")

    plain = Draft202012Validator(schema)
    with_formats = Draft202012Validator(schema, format_checker=FormatChecker())
    # fastjsonschema checks formats by default; switch it off for the plain row.
    compiled = fastjsonschema.compile(schema, use_formats=False)
    compiled_formats = fastjsonschema.compile(schema, use_formats=True)
    one_shot_count = max(1, count // 10)

    assert all(with_formats.is_valid(r) for r in records)
    assert all(compiled_formats(r) == r for r in records)

    rows = [
        ("json.loads per line", lambda: [json.loads(x) for x in lines], count),
        ("jsonschema, built once", lambda: [plain.is_valid(r) for r in records],
         count),
        ("jsonschema + FormatChecker", lambda: [with_formats.is_valid(r)
                                                for r in records], count),
        ("fastjsonschema, compiled", lambda: [compiled(r) for r in records],
         count),
        ("fastjsonschema + formats", lambda: [compiled_formats(r)
                                              for r in records], count),
        ("jsonschema.validate() per call",
         lambda: [jsonschema.validate(r, schema)
                  for r in records[:one_shot_count]], one_shot_count),
    ]
    parse_ms = None
    print(f"\n{'step':<32}{'records':>9}{'ms':>11}{'us/record':>12}{'x parse':>10}")

    for label, work, n in rows:
        ms = best_of(5, work)
        per_record = ms * 1000 / n
        parse_ms = parse_ms or per_record
        print(f"{label:<32}{n:>9,}{ms:>11.1f}{per_record:>12.2f}"
              f"{per_record / parse_ms:>10.1f}")

    start = time.perf_counter()
    fastjsonschema.compile(schema, use_formats=True)
    print(f"\nfastjsonschema.compile() itself: "
          f"{(time.perf_counter() - start) * 1000:.1f} ms")
    source = fastjsonschema.compile_to_code(schema)
    print(f"generated validator source: {len(source.splitlines()):,} lines")


if __name__ == "__main__":
    main()

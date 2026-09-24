"""What happens to each format when a write is cut short, and one JSONL trap."""
import json
import sys
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RECORDS = 50000
CRASH_AT = 30000        # the writer dies partway through this record


def read_jsonl(text: str) -> tuple[int, list[str]]:
    """Parse every complete line; report the ones that fail instead of stopping."""
    good, bad = 0, []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        try:
            json.loads(line)
            good += 1
        except json.JSONDecodeError as exc:
            bad.append(f"line {number}: {exc.msg} at column {exc.colno}")
    return good, bad


def main() -> None:
    rows = build(RECORDS)
    as_json = json.dumps(rows, separators=(",", ":"))
    lines = [json.dumps(row, separators=(",", ":")) for row in rows]
    as_jsonl = "\n".join(lines) + "\n"

    # The byte offset halfway through record CRASH_AT, in each layout.
    jsonl_cut = sum(len(line) + 1 for line in lines[:CRASH_AT - 1])
    jsonl_cut += len(lines[CRASH_AT - 1]) // 2
    json_cut = 1 + jsonl_cut          # the leading "[" shifts JSON by one byte

    print(f"writer killed halfway through record {CRASH_AT:,} of {RECORDS:,}")
    try:
        json.loads(as_json[:json_cut])
    except json.JSONDecodeError as exc:
        print(f"  buoy.json   JSONDecodeError: {exc.msg}; 0 records usable")
    good, bad = read_jsonl(as_jsonl[:jsonl_cut])
    print(f"  buoy.jsonl  {good:,} records usable; {len(bad)} bad line: {bad[0]}")

    boundary = sum(len(line) + 1 for line in lines[:CRASH_AT - 1])
    print()
    print(f"writer killed right after a newline, {CRASH_AT - 1:,} records in")
    try:
        json.loads(as_json[:boundary])
    except json.JSONDecodeError as exc:
        print(f"  buoy.json   JSONDecodeError: {exc.msg}")
    good, bad = read_jsonl(as_jsonl[:boundary])
    print(f"  buoy.jsonl  {good:,} records usable, {len(bad)} errors "
          f"- nothing says {RECORDS - good:,} are missing")

    note = {"buoy_id": "SW-42", "notes": "hull scraped mooring checked"}
    line = json.dumps(note, ensure_ascii=False)
    print()
    print("a note containing U+2028 LINE SEPARATOR, ensure_ascii=False")
    print(f"  split('\\n')   -> {len(line.split(chr(10)))} line")
    print(f"  splitlines()  -> {len(line.splitlines())} lines")
    try:
        [json.loads(part) for part in line.splitlines()]
    except json.JSONDecodeError as exc:
        print(f"  JSONDecodeError: {exc.msg}")


if __name__ == "__main__":
    main()

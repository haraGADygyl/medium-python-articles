"""Why a list built from JSONL lines is heavier than one json.load.

The decoder caches key strings for the length of one call. One call over the
whole array shares every "buoy_id" string; one call per line cannot.
"""
import json
import sys
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402


def distinct_key_objects(rows: list[dict]) -> int:
    """How many separate str objects hold the records' top-level keys."""
    return len({id(key) for row in rows for key in row})


def main() -> None:
    rows = build(50000)
    whole = json.loads(json.dumps(rows))
    per_line = [json.loads(json.dumps(row)) for row in rows]
    print(f"top-level key strings, 50000 records x {len(rows[0])} keys")
    print(f"  one json.loads over the array   {distinct_key_objects(whole):>9,}")
    print(f"  one json.loads per line         {distinct_key_objects(per_line):>9,}")


if __name__ == "__main__":
    main()

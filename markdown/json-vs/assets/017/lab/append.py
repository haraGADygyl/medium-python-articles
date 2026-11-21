"""A writer killed mid-file: what survives in JSON Lines and in Parquet.

Writes buoy-live.jsonl and buoy-live.parquet next to itself.
"""
import json
from pathlib import Path

import pyarrow.parquet as pq

from convert import SCHEMA, build, to_table

HERE = Path(__file__).parent


def main() -> None:
    rows = build(15_000)

    lines = HERE / "buoy-live.jsonl"
    with open(lines, "w") as out:
        for r in rows:
            out.write(json.dumps(r, separators=(",", ":")) + "\n")
    blob = lines.read_bytes()
    lines.write_bytes(blob[:len(blob) - 200])  # the process died mid-record
    survived = []
    for line in lines.read_text().splitlines():
        try:
            survived.append(json.loads(line))
        except json.JSONDecodeError:
            break
    print(f"JSON Lines, last 200 bytes lost: {len(survived):,} of {len(rows):,} records "
          f"read back")

    live = HERE / "buoy-live.parquet"
    writer = pq.ParquetWriter(live, SCHEMA)
    for start in range(0, len(rows), 5_000):
        writer.write_table(to_table(rows[start:start + 5_000]))
    on_disk = live.stat().st_size  # three row groups written, close() never called
    print(f"Parquet, three row groups flushed, footer not yet written: {on_disk:,} bytes")
    try:
        pq.read_table(live)
    except Exception as error:
        print(f"  {type(error).__name__}: {str(error).replace(str(live), live.name)}")
    writer.close()
    print(f"  after close(): {live.stat().st_size:,} bytes, "
          f"{pq.read_table(live).num_rows:,} records read back")


if __name__ == "__main__":
    main()

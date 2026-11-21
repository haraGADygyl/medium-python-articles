"""One question, asked of JSON, JSON Lines and Parquet: bytes read and time taken.

Writes buoy.json, buoy.jsonl, buoy.parquet and buoy-sorted.parquet next to itself.
Every Parquet file here uses 5,000-row groups, so there is something to skip.
"""
import gc
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from convert import build, to_table

RUNS = 5
HERE = Path(__file__).parent
GROUP = 5_000
WEEK = (datetime(2026, 6, 1, tzinfo=timezone.utc), datetime(2026, 6, 8, tzinfo=timezone.utc))


class Counting(io.RawIOBase):
    """A read-only file that remembers how many bytes were actually read."""

    def __init__(self, path: Path) -> None:
        self.inner = open(path, "rb")
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.inner.seek(offset, whence)

    def tell(self) -> int:
        return self.inner.tell()

    def readinto(self, buffer) -> int:
        count = self.inner.readinto(buffer)
        self.bytes_read += count

        return count


def best(fn) -> tuple[float, object]:
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        gc.disable()
        started = time.perf_counter()
        result = fn()
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
    return fastest, result


def mean_wave_json(buoy: str, since: str = "", until: str = "~") -> float:
    rows = json.loads((HERE / "buoy.json").read_bytes())
    waves = [r["wave_height_m"] for r in rows
             if r["buoy_id"] == buoy and since <= r["recorded_at"] < until]
    return sum(waves) / len(waves)


def mean_wave_jsonl(buoy: str, since: str = "", until: str = "~") -> float:
    total, count = 0.0, 0
    with open(HERE / "buoy.jsonl", "rb") as lines:
        for line in lines:
            r = json.loads(line)
            if r["buoy_id"] == buoy and since <= r["recorded_at"] < until:
                total += r["wave_height_m"]
                count += 1
    return total / count


def mean_wave_parquet(path: Path, buoy: str, week: bool = False) -> tuple[float, int]:
    """Two columns out of fourteen, row groups skipped by their min/max statistics."""
    filters = [("buoy_id", "=", buoy)]
    if week:
        filters += [("recorded_at", ">=", WEEK[0]), ("recorded_at", "<", WEEK[1])]
    source = Counting(path)
    table = pq.read_table(source, columns=["wave_height_m"], filters=filters)
    return pc.mean(table["wave_height_m"]).as_py(), source.bytes_read


def groups_kept(path: Path, column: str, low, high) -> int:
    """How many row groups could hold a value in [low, high], from the footer alone."""
    meta = pq.ParquetFile(path).metadata
    index = meta.schema.names.index(column)
    kept = 0
    for g in range(meta.num_row_groups):
        stats = meta.row_group(g).column(index).statistics
        kept += not (stats.max < low or stats.min > high)
    return kept


def main() -> None:
    rows = build(50000)
    (HERE / "buoy.json").write_text(json.dumps(rows, separators=(",", ":")))
    with open(HERE / "buoy.jsonl", "w") as out:
        for r in rows:
            out.write(json.dumps(r, separators=(",", ":")) + "\n")
    table = to_table(rows)
    pq.write_table(table, HERE / "buoy.parquet", row_group_size=GROUP)
    by_buoy = table.sort_by([("buoy_id", "ascending"), ("recorded_at", "ascending")])
    pq.write_table(by_buoy, HERE / "buoy-sorted.parquet", row_group_size=GROUP)

    files = {name: (HERE / name).stat().st_size
             for name in ("buoy.json", "buoy.jsonl", "buoy.parquet", "buoy-sorted.parquet")}
    print(f"50000 records, pyarrow {pa.__version__}, duckdb {duckdb.__version__}, "
          f"best of {RUNS}, {GROUP:,}-row groups")
    for name, size in files.items():
        print(f"  {name:<22}{size:>12,} bytes")

    since, until = (d.isoformat() for d in WEEK)
    print()
    print("Q1: mean wave height at NE-07, the whole year")
    t_json, a_json = best(lambda: mean_wave_json("NE-07"))
    t_jsonl, a_jsonl = best(lambda: mean_wave_jsonl("NE-07"))
    t_pq, (a_pq, read_pq) = best(lambda: mean_wave_parquet(HERE / "buoy.parquet", "NE-07"))
    print(f"  {'JSON, json.loads':<36}{t_json:>8.1f} ms  read {files['buoy.json']:>11,}"
          f"  -> {a_json:.4f}")
    print(f"  {'JSON Lines, line by line':<36}{t_jsonl:>8.1f} ms  read {files['buoy.jsonl']:>11,}"
          f"  -> {a_jsonl:.4f}")
    print(f"  {'Parquet, 2 columns + filter':<36}{t_pq:>8.1f} ms  read {read_pq:>11,}"
          f"  -> {a_pq:.4f}")

    print()
    print(f"Q2: mean wave height at NE-07, one week ({since[:10]} to {until[:10]})")
    t_json, a_json = best(lambda: mean_wave_json("NE-07", since, until))
    t_pq, (a_pq, read_pq) = best(lambda: mean_wave_parquet(HERE / "buoy.parquet", "NE-07",
                                                            week=True))
    kept = groups_kept(HERE / "buoy.parquet", "recorded_at", *WEEK)
    print(f"  {'JSON, json.loads':<36}{t_json:>8.1f} ms  read {files['buoy.json']:>11,}"
          f"  -> {a_json:.4f}")
    print(f"  {'Parquet, time-ordered file':<36}{t_pq:>8.1f} ms  read {read_pq:>11,}"
          f"  -> {a_pq:.4f}")
    print(f"  row groups whose recorded_at range overlaps the week: {kept} of "
          f"{pq.ParquetFile(HERE / 'buoy.parquet').metadata.num_row_groups}")

    print()
    print("Q1 again: statistics only skip what the sort order clusters")
    for name in ("buoy.parquet", "buoy-sorted.parquet"):
        path = HERE / name
        meta = pq.ParquetFile(path).metadata
        index = meta.schema.names.index("buoy_id")
        stats = meta.row_group(0).column(index).statistics
        t_pq, (a_pq, read_pq) = best(lambda: mean_wave_parquet(path, "NE-07"))
        kept = groups_kept(path, "buoy_id", "NE-07", "NE-07")
        print(f"  {name:<22} group 0 buoy_id {stats.min}..{stats.max:<8}"
              f" groups kept {kept:>2} of {meta.num_row_groups}"
              f"  read {read_pq:>9,}  {t_pq:>6.1f} ms  -> {a_pq:.4f}")

    print()
    print("the same SQL, the same engine (DuckDB), two files")
    sql = "SELECT round(avg(wave_height_m), 4) FROM {} WHERE buoy_id = 'NE-07'"
    con = duckdb.connect()
    con.execute("SET threads = 1")
    for label, source in (("read_json('buoy.json')", f"read_json('{HERE / 'buoy.json'}')"),
                          ("'buoy.parquet'", f"'{HERE / 'buoy.parquet'}'")):
        t, answer = best(lambda: con.execute(sql.format(source)).fetchone()[0])
        print(f"  {label:<28}{t:>8.1f} ms  -> {answer}")
    print("  (one thread, so the comparison is the format, not the core count)")


if __name__ == "__main__":
    main()

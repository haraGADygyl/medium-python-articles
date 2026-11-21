"""JSON vs. Parquet on the shared buoy payload: size, per-column cost, time."""
import gc
import gzip
import io
import json
import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from convert import build, from_table, to_table

RUNS = 5
RECORDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
CODECS = ("none", "snappy", "gzip", "zstd")
GROUPS = (50_000, 10_000, 5_000, 1_000)


def best(fn, *args) -> tuple[float, object]:
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        gc.disable()
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
    return fastest, result


def gz(blob: bytes) -> int:
    return len(gzip.compress(blob, 9))


def zs(blob: bytes) -> int:
    return len(zstandard.ZstdCompressor(level=3).compress(blob))


def parquet(table: pa.Table, **options) -> bytes:
    """pyarrow defaults unless overridden: snappy, dictionary on, one big row group.

    gzip runs at level 9 to match gzip -9; zstd keeps pyarrow's default, level 1.
    """
    if options.get("compression") == "gzip":
        options.setdefault("compression_level", 9)
    out = io.BytesIO()
    pq.write_table(table, out, **options)
    return out.getvalue()


def read_parquet(blob: bytes) -> pa.Table:
    return pq.read_table(io.BytesIO(blob))


def change(a: int, b: int) -> str:
    pct = 100 * (a / b - 1)
    return f"{abs(pct):.1f}% {'bigger' if pct > 0 else 'smaller'}"


def main() -> None:
    rows = build(RECORDS)
    table = to_table(rows)
    print(f"{RECORDS} buoy records, best of {RUNS}, pyarrow {pa.__version__}")

    as_json = json.dumps(rows, separators=(",", ":")).encode()
    as_jsonl = "".join(json.dumps(r, separators=(",", ":")) + "\n"
                       for r in rows).encode()
    files = {codec: parquet(table, compression=codec) for codec in CODECS}
    for codec, blob in files.items():
        assert from_table(read_parquet(blob)) == rows, codec

    print()
    print(f"{'format':<26}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for label, blob in (("JSON", as_json), ("JSON Lines", as_jsonl),
                        ("Parquet, codec none", files["none"])):
        print(f"{label:<26}{len(blob):>12,}{gz(blob):>12,}{zs(blob):>12,}")
    for codec in CODECS[1:]:
        print(f"{'Parquet, codec ' + codec:<26}{len(files[codec]):>12,}")
    plain = files["none"]
    print(f"  Parquet (none) vs JSON: raw {change(len(plain), len(as_json))}, "
          f"gzip {change(gz(plain), gz(as_json))}, zstd {change(zs(plain), zs(as_json))}")
    for codec in CODECS[1:]:
        print(f"  Parquet codec {codec} vs gzipped JSON: "
              f"{change(len(files[codec]), gz(as_json))}")
    footer = pq.ParquetFile(io.BytesIO(files["snappy"])).metadata.serialized_size
    print(f"  footer (schema, row-group and column statistics): {footer:,} bytes")

    print()
    print("where the bytes go: one column chunk per leaf, codec snappy")
    meta = pq.ParquetFile(io.BytesIO(files["snappy"])).metadata.row_group(0)
    print(f"  {'column':<30}{'bytes':>10}  encodings")
    for i in range(meta.num_columns):
        col = meta.column(i)
        name = col.path_in_schema.replace(".list.element", "[]")
        kinds = ", ".join(e for e in col.encodings if e != "RLE")
        print(f"  {name:<30}{col.total_compressed_size:>10,}  {kinds}")

    delta = parquet(table, use_dictionary=["buoy_id", "position.lat", "position.lon",
                                           "wave_height_m", "water_temp_c",
                                           "wind_gust_ms", "battery_v", "notes",
                                           "sensors.list.element.tag",
                                           "sensors.list.element.status",
                                           "sensors.list.element.samples"],
                    column_encoding={"observation_id": "DELTA_BINARY_PACKED",
                                     "recorded_at": "DELTA_BINARY_PACKED"})
    dmeta = pq.ParquetFile(io.BytesIO(delta)).metadata.row_group(0)
    print()
    print("the two sequential columns, DELTA_BINARY_PACKED instead of dictionary")
    for i in (0, 2):
        print(f"  {meta.column(i).path_in_schema:<30}"
              f"{meta.column(i).total_compressed_size:>10,} -> "
              f"{dmeta.column(i).total_compressed_size:>7,}")
    print(f"  whole file, snappy: {len(files['snappy']):,} -> {len(delta):,} "
          f"({change(len(delta), gz(as_json))} than gzipped JSON)")

    print()
    print("row-group size against file size (snappy)")
    print(f"{'rows per group':<16}{'groups':>8}{'bytes':>12}{'footer':>10}")
    for size in GROUPS:
        blob = parquet(table, row_group_size=size)
        info = pq.ParquetFile(io.BytesIO(blob)).metadata
        print(f"{size:<16,}{info.num_row_groups:>8}{len(blob):>12,}"
              f"{info.serialized_size:>10,}")

    first_json = json.dumps(rows[0], separators=(",", ":")).encode()
    first_parquet = parquet(to_table(rows[:1]))
    print()
    print("one record on its own")
    print(f"  {'JSON':<24}{len(first_json):>6} bytes raw{gz(first_json):>6} gzipped")
    print(f"  {'Parquet file, one row':<24}{len(first_parquet):>6} bytes raw"
          f"{gz(first_parquet):>6} gzipped")

    enc_json, _ = best(lambda: json.dumps(rows, separators=(",", ":")).encode())
    dec_json, _ = best(json.loads, as_json)
    to_arrow, _ = best(to_table, rows)
    write_only, _ = best(parquet, table)
    enc_parquet, _ = best(lambda: parquet(to_table(rows)))
    read_only, _ = best(read_parquet, files["snappy"])
    dec_parquet, _ = best(lambda: from_table(read_parquet(files["snappy"])))
    one_column, _ = best(lambda: pq.read_table(io.BytesIO(files["snappy"]),
                                               columns=["wave_height_m"]))

    print()
    print("time, ms                                     JSON    Parquet")
    print(f"  dicts -> bytes                         {enc_json:>8.1f}  {enc_parquet:>8.1f}"
          f"   (dicts -> Arrow {to_arrow:.1f}, Arrow -> bytes {write_only:.1f})")
    print(f"  bytes -> dicts                         {dec_json:>8.1f}  {dec_parquet:>8.1f}")
    print(f"  bytes -> Arrow table, all columns              {read_only:>8.1f}")
    print(f"  bytes -> Arrow table, one column               {one_column:>8.1f}")
    print()
    print("every codec round-trips the original records: True")


if __name__ == "__main__":
    main()

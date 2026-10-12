"""JSON vs. Apache Avro on the shared buoy payload."""
import gc
import gzip
import io
import json
import sys
import time

import fastavro
import msgpack
import zstandard
from fastavro import reader, schemaless_reader, schemaless_writer, writer

from convert import SCHEMA, build, from_avro, to_avro

RUNS = 5
RECORDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
CODECS = ("null", "deflate", "snappy", "zstandard")
BLOCKS = (16_000, 64_000, 1_000_000, 64_000_000)


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


def container(rows: list[dict], codec: str = "null", block: int = 16000) -> bytes:
    """An object container file; fastavro starts a new block every ~16 KB by default.

    deflate runs at level 9 to match gzip -9; zstandard keeps its default, level 3.
    """
    out = io.BytesIO()
    writer(out, SCHEMA, (to_avro(r) for r in rows), codec=codec, sync_interval=block,
           codec_compression_level=9 if codec == "deflate" else None)
    return out.getvalue()


def read_container(blob: bytes) -> list[dict]:
    return [from_avro(r) for r in reader(io.BytesIO(blob))]


def bare(row: dict) -> bytes:
    out = io.BytesIO()
    schemaless_writer(out, SCHEMA, to_avro(row))
    return out.getvalue()


def change(a: int, b: int) -> str:
    pct = 100 * (a / b - 1)
    return f"{abs(pct):.1f}% {'bigger' if pct > 0 else 'smaller'}"


def main() -> None:
    rows = build(RECORDS)
    print(f"{RECORDS} buoy records, best of {RUNS}, fastavro {fastavro.__version__}")

    as_json = json.dumps(rows, separators=(",", ":")).encode()
    as_msgpack = msgpack.packb(rows)
    files = {codec: container(rows, codec) for codec in CODECS}
    for codec, blob in files.items():
        assert read_container(blob) == rows, codec
    header = len(container([], "null"))

    print()
    print(f"{'format':<26}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for label, blob in (("JSON", as_json), ("MessagePack", as_msgpack),
                        ("Avro file, codec null", files["null"])):
        print(f"{label:<26}{len(blob):>12,}{gz(blob):>12,}{zs(blob):>12,}")
    for codec in CODECS[1:]:
        print(f"{'Avro file, codec ' + codec:<26}{len(files[codec]):>12,}")
    raw = files["null"]
    print(f"  Avro (null) vs JSON: raw {change(len(raw), len(as_json))}, "
          f"gzip {change(gz(raw), gz(as_json))}, zstd {change(zs(raw), zs(as_json))}")
    for codec in CODECS[1:]:
        print(f"  Avro codec {codec} vs gzipped JSON: "
              f"{change(len(files[codec]), gz(as_json))}")
    print(f"  file header (magic, schema, sync marker), written once: {header} bytes")

    print()
    print("codecs compress each block on its own: block size against file size")
    print(f"{'block size':<14}{'blocks':>8}{'deflate -9':>12}{'zstandard -3':>14}")
    for block in BLOCKS:
        deflated = container(rows, "deflate", block)
        blocks = sum(1 for _ in fastavro.block_reader(io.BytesIO(deflated)))
        print(f"{block:<14,}{blocks:>8,}{len(deflated):>12,}"
              f"{len(container(rows, 'zstandard', block)):>14,}")

    first_json = json.dumps(rows[0], separators=(",", ":")).encode()
    first_bare = bare(rows[0])
    first_file = container(rows[:1])
    print()
    print("one record on its own")
    print(f"  {'JSON':<34}{len(first_json):>5} bytes raw{gz(first_json):>6} gzipped")
    print(f"  {'Avro body, no schema':<34}{len(first_bare):>5} bytes raw"
          f"{gz(first_bare):>6} gzipped")
    print(f"  {'Avro body + 5-byte registry prefix':<34}{len(first_bare) + 5:>5} bytes raw")
    print(f"  {'Avro container file, one record':<34}{len(first_file):>5} bytes raw"
          f"{gz(first_file):>6} gzipped")

    enc_json, _ = best(lambda: json.dumps(rows, separators=(",", ":")).encode())
    dec_json, _ = best(json.loads, as_json)
    enc_avro, _ = best(container, rows)
    dec_avro, _ = best(read_container, raw)
    stamps, _ = best(lambda: [to_avro(r) for r in rows])
    enc_zstd, _ = best(container, rows, "zstandard")
    dec_zstd, _ = best(read_container, files["zstandard"])
    enc_json_gz, _ = best(lambda: gzip.compress(
        json.dumps(rows, separators=(",", ":")).encode(), 6))
    gz6 = gzip.compress(as_json, 6)
    dec_json_gz, _ = best(lambda: json.loads(gzip.decompress(gz6)))

    print()
    print("time, ms, dicts -> bytes -> dicts          JSON       Avro")
    print(f"  encode                              {enc_json:>9.1f}  {enc_avro:>9.1f}"
          f"   (of which ISO string -> datetime {stamps:.1f})")
    print(f"  decode                              {dec_json:>9.1f}  {dec_avro:>9.1f}")
    print(f"  encode, compressed (gzip -6 / zstd) {enc_json_gz:>9.1f}  {enc_zstd:>9.1f}")
    print(f"  decode, compressed (gzip -6 / zstd) {dec_json_gz:>9.1f}  {dec_zstd:>9.1f}")
    print()
    print(f"every codec round-trips the original records: True")


if __name__ == "__main__":
    main()

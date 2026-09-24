"""JSON vs. BSON on the shared buoy payload."""
import gc
import gzip
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import bson
import cbor2
import msgpack
import zstandard
from bson.raw_bson import RawBSONDocument

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RUNS = 5
RECORDS = 50000


def best(fn, *args) -> tuple[float, object]:
    """Fastest of RUNS calls, in milliseconds, plus the last result.

    The cyclic GC is off while timing, as timeit does: otherwise building
    50,000 dicts triggers collections that dwarf the codec being measured.
    """
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        gc.disable()
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
    return fastest, result


def sizes(blob: bytes) -> tuple[int, int, int]:
    return (len(blob), len(gzip.compress(blob, 9)),
            len(zstandard.ZstdCompressor(level=3).compress(blob)))


def typed(row: dict) -> dict:
    """The same record using BSON's datetime type for recorded_at."""
    return {**row, "recorded_at": datetime.fromisoformat(row["recorded_at"])}


def main() -> None:
    rows = build(RECORDS)
    print(f"{RECORDS} buoy records, best of {RUNS}, pymongo bson "
          f"C extension: {bson.has_c()}")

    # One document per record: how MongoDB stores and ships them.
    enc_json, json_docs = best(
        lambda: [json.dumps(r, separators=(",", ":")).encode() for r in rows])
    dec_json, _ = best(lambda: [json.loads(d) for d in json_docs])
    enc_bson, bson_docs = best(lambda: [bson.encode(r) for r in rows])
    dec_bson, _ = best(lambda: [bson.decode(d) for d in bson_docs])
    typed_rows = [typed(r) for r in rows]
    _, typed_docs = best(lambda: [bson.encode(r) for r in typed_rows])

    msgpack_stream = b"".join(msgpack.packb(r) for r in rows)
    cbor_stream = b"".join(cbor2.dumps(r) for r in rows)
    json_stream = b"\n".join(json_docs) + b"\n"
    bson_stream = b"".join(bson_docs)          # BSON documents self-delimit
    typed_stream = b"".join(typed_docs)

    print()
    print(f"{'format':<28}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}"
          f"{'encode ms':>11}{'decode ms':>11}")
    for label, blob, enc, dec in (
            ("JSON, one line per record", json_stream, enc_json, dec_json),
            ("BSON, one doc per record", bson_stream, enc_bson, dec_bson),
            ("BSON, recorded_at datetime", typed_stream, None, None),
            ("MessagePack, per record", msgpack_stream, None, None),
            ("CBOR, per record", cbor_stream, None, None)):
        raw, gz, zs = sizes(blob)
        timing = (f"{enc:>11.1f}{dec:>11.1f}" if enc is not None else "")
        print(f"{label:<28}{raw:>12,}{gz:>12,}{zs:>12,}{timing}")

    j_raw, j_gz, j_zs = sizes(json_stream)
    for label, blob in (("BSON", bson_stream), ("BSON typed", typed_stream)):
        raw, gz, zs = sizes(blob)
        print(f"  {label} vs JSON: raw {100 * (raw / j_raw - 1):+.1f}%, "
              f"gzip {100 * (gz / j_gz - 1):+.1f}%, "
              f"zstd {100 * (zs / j_zs - 1):+.1f}%")

    print()
    print("count failed QC across all 50,000 documents")
    ms, failed = best(lambda: sum(not json.loads(d)["qc_passed"]
                                  for d in json_docs))
    print(f"  {'json.loads each line':<34}{ms:>8.1f} ms   {failed:,}")
    ms, failed = best(lambda: sum(not bson.decode(d)["qc_passed"]
                                  for d in bson_docs))
    print(f"  {'bson.decode each document':<34}{ms:>8.1f} ms   {failed:,}")
    ms, failed = best(lambda: sum(not RawBSONDocument(d)["qc_passed"]
                                  for d in bson_docs))
    print(f"  {'RawBSONDocument, one field':<34}{ms:>8.1f} ms   {failed:,}")


if __name__ == "__main__":
    main()

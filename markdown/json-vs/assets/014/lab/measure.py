"""JSON vs. Protocol Buffers on the shared buoy payload."""
import gc
import gzip
import json
import time

import msgpack
import zstandard
from google.protobuf import __version__ as protobuf_version
from google.protobuf.internal import api_implementation

import buoy_pb2
from convert import build, from_proto, to_batch

RUNS = 5
RECORDS = 50000


def best(fn, *args) -> tuple[float, object]:
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


def parse_batch(blob: bytes) -> buoy_pb2.Batch:
    batch = buoy_pb2.Batch()
    batch.ParseFromString(blob)
    return batch


def main() -> None:
    rows = build(RECORDS)
    print(f"{RECORDS} buoy records, best of {RUNS}, protobuf {protobuf_version} "
          f"({api_implementation.Type()} backend)")

    enc_json, as_json = best(lambda: json.dumps(rows, separators=(",", ":")).encode())
    dec_json, _ = best(json.loads, as_json)
    build_ms, batch = best(to_batch, rows)
    ser_ms, as_proto = best(batch.SerializeToString)
    parse_ms, parsed = best(parse_batch, as_proto)
    dicts_ms, back = best(lambda b: [from_proto(o) for o in b.observations], parsed)
    as_msgpack = msgpack.packb(rows)

    print()
    print(f"{'format':<14}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for label, blob in (("JSON", as_json), ("Protobuf", as_proto), ("MessagePack", as_msgpack)):
        raw, gz, zs = sizes(blob)
        print(f"{label:<14}{raw:>12,}{gz:>12,}{zs:>12,}")
    (jr, jg, jz), (pr, pg, pz) = sizes(as_json), sizes(as_proto)
    def change(a: int, b: int) -> str:
        pct = 100 * (a / b - 1)
        return f"{abs(pct):.1f}% {'bigger' if pct > 0 else 'smaller'}"
    print(f"  Protobuf vs JSON: raw {change(pr, jr)}, gzip {change(pg, jg)}, "
          f"zstd {change(pz, jz)}")

    single_json = json.dumps(rows[0], separators=(",", ":")).encode()
    single_proto = batch.observations[0].SerializeToString()
    print()
    print("one record on its own, as an RPC would send it")
    for label, blob in (("JSON", single_json), ("Protobuf", single_proto)):
        print(f"  {label:<12}{len(blob):>6} bytes raw{len(gzip.compress(blob, 9)):>6} gzipped")

    print()
    print("time, ms                      JSON   Protobuf")
    print(f"  bytes only: encode      {enc_json:>9.1f}  {ser_ms:>9.1f}   (SerializeToString)")
    print(f"  bytes only: decode      {dec_json:>9.1f}  {parse_ms:>9.1f}   (ParseFromString)")
    print(f"  dicts -> bytes          {enc_json:>9.1f}  {build_ms + ser_ms:>9.1f}   "
          f"(build messages {build_ms:.1f} + serialize)")
    print(f"  bytes -> dicts          {dec_json:>9.1f}  {parse_ms + dicts_ms:>9.1f}   "
          f"(parse + read fields {dicts_ms:.1f})")
    print()
    print(f"round trip returns the original records: {back == rows}")


if __name__ == "__main__":
    main()

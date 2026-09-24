"""JSON vs. CBOR on the shared buoy payload, with MessagePack for scale."""
import gzip
import json
import sys
import time
from pathlib import Path

import cbor2
import msgpack
import zstandard

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RUNS = 5


def best(fn, *args) -> tuple[float, object]:
    """Fastest of RUNS calls, in milliseconds, plus the last result."""
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
    return fastest, result


def report(label: str, blob: bytes, encode_ms: float,
           decode_ms: float) -> dict:
    """Size raw, gzipped and zstd-compressed, plus round-trip timings."""
    return {
        "format": label,
        "bytes": len(blob),
        "gzip9": len(gzip.compress(blob, 9)),
        "zstd3": len(zstandard.ZstdCompressor(level=3).compress(blob)),
        "encode_ms": round(encode_ms, 1),
        "decode_ms": round(decode_ms, 1),
    }


def run(label: str, encode, decode, data: list[dict]) -> dict:
    """Time one encoder/decoder pair and check it round-trips."""
    enc_ms, blob = best(encode, data)
    dec_ms, back = best(decode, blob)
    assert back == data, f"{label} did not round-trip"
    return report(label, blob, enc_ms, dec_ms)


def main() -> None:
    records = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    data = build(records)

    rows = [
        run("JSON",
            lambda d: json.dumps(d, separators=(",", ":")).encode(),
            json.loads, data),
        run("MessagePack", msgpack.packb,
            lambda b: msgpack.unpackb(b, raw=False), data),
        run("CBOR", cbor2.dumps, cbor2.loads, data),
        run("CBOR canonical",
            lambda d: cbor2.dumps(d, canonical=True), cbor2.loads, data),
        run("CBOR stringref",
            lambda d: cbor2.dumps(d, string_referencing=True),
            cbor2.loads, data),
    ]

    print(f"{records} buoy records, best of {RUNS}")
    print(f"{'format':<16}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}"
          f"{'encode ms':>12}{'decode ms':>12}")
    for row in rows:
        print(f"{row['format']:<16}{row['bytes']:>12,}{row['gzip9']:>12,}"
              f"{row['zstd3']:>12,}{row['encode_ms']:>12}"
              f"{row['decode_ms']:>12}")

    base = rows[0]
    print()
    print("change against JSON (negative = bigger)")
    print(f"{'format':<16}{'raw':>10}{'gzip -9':>10}{'zstd -3':>10}")
    for row in rows[1:]:
        cells = [100 * (1 - row[k] / base[k])
                 for k in ("bytes", "gzip9", "zstd3")]
        print(f"{row['format']:<16}" + "".join(f"{c:>9.1f}%" for c in cells))


if __name__ == "__main__":
    main()

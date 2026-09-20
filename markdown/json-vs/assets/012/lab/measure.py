"""JSON vs. MessagePack on the shared buoy payload."""
import gzip
import json
import sys
import time
from pathlib import Path

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


def main() -> None:
    records = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    data = build(records)

    enc_ms, as_json = best(
        lambda d: json.dumps(d, separators=(",", ":")).encode(), data)
    dec_ms, _ = best(json.loads, as_json)
    rows = [report("JSON", as_json, enc_ms, dec_ms)]

    enc_ms, as_msgpack = best(msgpack.packb, data)
    dec_ms, _ = best(lambda b: msgpack.unpackb(b, strict_map_key=False),
                     as_msgpack)
    rows.append(report("MessagePack", as_msgpack, enc_ms, dec_ms))

    header = f"{records} buoy records, best of {RUNS}"
    print(header)
    print(f"{'format':<12}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}"
          f"{'encode ms':>12}{'decode ms':>12}")
    for row in rows:
        print(f"{row['format']:<12}{row['bytes']:>12,}{row['gzip9']:>12,}"
              f"{row['zstd3']:>12,}{row['encode_ms']:>12}"
              f"{row['decode_ms']:>12}")
    j, m = rows
    print()
    print(f"MessagePack raw:      {100 * (1 - m['bytes'] / j['bytes']):.1f}% "
          f"smaller than JSON")
    print(f"MessagePack gzip -9:  {100 * (1 - m['gzip9'] / j['gzip9']):.1f}% "
          f"smaller than gzipped JSON")
    print(f"MessagePack zstd -3:  {100 * (1 - m['zstd3'] / j['zstd3']):.1f}% "
          f"smaller than zstd JSON")
    print(f"gzipped JSON vs raw MessagePack: "
          f"{100 * (1 - j['gzip9'] / m['bytes']):.1f}% smaller")


if __name__ == "__main__":
    main()

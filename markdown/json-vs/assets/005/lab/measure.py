"""JSON vs. UBJSON on the shared buoy payload, with MessagePack and CBOR."""
import gc
import gzip
import json
import sys
import time
from pathlib import Path

import cbor2
import msgpack
import ubjson
import zstandard

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RUNS = 5
RECORDS = 50000
METRES_PER_DEGREE = 111_320          # of latitude, near enough anywhere


def best(fn, *args) -> tuple[float, object]:
    """Fastest of RUNS calls in ms, GC paused as timeit does, plus result."""
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        gc.disable()
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
    return fastest, result


def floats(value: object):
    """Every float in a nested structure, in order."""
    if isinstance(value, dict):
        for item in value.values():
            yield from floats(item)
    elif isinstance(value, list):
        for item in value:
            yield from floats(item)
    elif isinstance(value, float):
        yield value


def main() -> None:
    data = build(RECORDS)
    codecs = {
        "JSON": (lambda d: json.dumps(d, separators=(",", ":")).encode(),
                 json.loads),
        "UBJSON": (ubjson.dumpb, ubjson.loadb),
        "UBJSON, counts": (lambda d: ubjson.dumpb(d, container_count=True),
                           ubjson.loadb),
        "UBJSON, float32": (lambda d: ubjson.dumpb(d, no_float32=False),
                            ubjson.loadb),
        "MessagePack": (msgpack.packb, msgpack.unpackb),
        "CBOR": (cbor2.dumps, cbor2.loads),
    }
    print(f"{RECORDS} buoy records, best of {RUNS}, py-ubjson "
          f"{ubjson.__version__} (C extension: {ubjson.EXTENSION_ENABLED})")
    print()
    print(f"{'format':<17}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}"
          f"{'encode ms':>11}{'decode ms':>11}  round-trips")
    rows, decoded = {}, {}
    for label, (encode, decode) in codecs.items():
        enc_ms, blob = best(encode, data)
        dec_ms, back = best(decode, blob)
        decoded[label] = back
        rows[label] = (len(blob), len(gzip.compress(blob, 9)),
                       len(zstandard.ZstdCompressor(level=3).compress(blob)))
        raw, gz, zs = rows[label]
        print(f"{label:<17}{raw:>12,}{gz:>12,}{zs:>12,}{enc_ms:>11.1f}"
              f"{dec_ms:>11.1f}  {back == data}")

    raw, gz, zs = rows["JSON"]
    print()
    print("change against JSON (negative = bigger)")
    for label, (r, g, z) in rows.items():
        if label != "JSON":
            print(f"  {label:<17}raw {100 * (1 - r / raw):6.1f}%   "
                  f"gzip {100 * (1 - g / gz):6.1f}%   "
                  f"zstd {100 * (1 - z / zs):6.1f}%")

    original = list(floats(data))
    lossy = list(floats(decoded["UBJSON, float32"]))
    changed = sum(a != b for a, b in zip(original, lossy))
    worst_lat = max(abs(r["position"]["lat"] - l["position"]["lat"])
                    for r, l in zip(data, decoded["UBJSON, float32"]))
    print()
    print(f"no_float32=False: {changed:,} of {len(original):,} floats "
          f"came back different")
    print(f"  worst latitude error {worst_lat:.2e} degrees = "
          f"{worst_lat * METRES_PER_DEGREE * 100:.1f} cm")
    print(f"  e.g. {data[0]['battery_v']} -> "
          f"{decoded['UBJSON, float32'][0]['battery_v']}")


if __name__ == "__main__":
    main()

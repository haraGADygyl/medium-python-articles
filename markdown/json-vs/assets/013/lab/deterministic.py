"""Same data, different bytes: what deterministic encoding fixes, on the payload."""
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

import cbor2

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402


def reordered(value: object, rng: random.Random) -> object:
    """The same value with every map's keys in a shuffled order."""
    if isinstance(value, dict):
        keys = list(value)
        rng.shuffle(keys)
        return {k: reordered(value[k], rng) for k in keys}
    if isinstance(value, list):
        return [reordered(v, rng) for v in value]
    return value


def digest(blob: bytes) -> str:
    """Short SHA-256, enough to tell two blobs apart."""
    return hashlib.sha256(blob).hexdigest()[:16]


def narrowest(value: float) -> str:
    """The float width deterministic CBOR picks for this value."""
    for code, width in (("e", "half"), ("f", "single")):
        try:
            if struct.unpack(code, struct.pack(code, value))[0] == value:
                return width
        except OverflowError:
            continue
    return "double"


def floats(value: object):
    """Every float in a nested structure."""
    if isinstance(value, dict):
        for item in value.values():
            yield from floats(item)
    elif isinstance(value, list):
        for item in value:
            yield from floats(item)
    elif isinstance(value, float):
        yield value


def rfc8949_map(mapping: dict) -> bytes:
    """A map with keys in RFC 8949 section 4.2.1 order: bytewise on the
    encoded key. Only for maps under 24 entries, which fit in the head byte."""
    pairs = sorted((cbor2.dumps(k, canonical=True),
                    cbor2.dumps(v, canonical=True)) for k, v in mapping.items())
    return bytes([0xA0 + len(pairs)]) + b"".join(k + v for k, v in pairs)


def main() -> None:
    data = build(50000)
    shuffled = reordered(data, random.Random(8949))
    print(f"50000 records, key order shuffled in every map; equal: "
          f"{data == shuffled}")
    print()
    encoders = {
        "json": lambda d: json.dumps(d, separators=(",", ":")).encode(),
        "json sort_keys": lambda d: json.dumps(
            d, separators=(",", ":"), sort_keys=True).encode(),
        "cbor": cbor2.dumps,
        "cbor canonical": lambda d: cbor2.dumps(d, canonical=True),
    }
    for label, encode in encoders.items():
        left, right = digest(encode(data)), digest(encode(shuffled))
        print(f"{label:<16}{left}  {right}  "
              f"{'same' if left == right else 'DIFFERENT'}")

    widths: dict[str, int] = {"half": 0, "single": 0, "double": 0}
    for value in floats(data):
        widths[narrowest(value)] += 1
    total = sum(widths.values())
    print()
    print(f"{total:,} floats; deterministic CBOR stores them as")
    for width, count in widths.items():
        print(f"  {width:<7}{count:>9,}  {100 * count / total:5.1f}%")
    saved = widths["half"] * 6 + widths["single"] * 4
    print(f"bytes saved against always-double: {saved:,}")

    mixed = {"a": 2, 1000: 1}
    print()
    print("map with an int key and a text key")
    print(f"  cbor2 canonical=True   {cbor2.dumps(mixed, canonical=True).hex(' ')}"
          f"   (RFC 7049: shorter key first)")
    print(f"  RFC 8949 core det.     {rfc8949_map(mixed).hex(' ')}"
          f"   (bytewise: 0x19 < 0x61)")


if __name__ == "__main__":
    main()

"""Plain JSON vs. JSON-LD on the shared payload: size, processing, context loads."""
import gzip
import json
import sys
import time
from pathlib import Path

import zstandard
from pyld import jsonld

from contexts import CONTEXT_URL, OBSERVATION_CONTEXT, CountingLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402

RECORDS = 50000
PROCESSED = 1000        # pyld is pure Python; 1,000 records is plenty to time
CANONICALISED = 100


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)


def sizes(text: str) -> tuple[int, int, int]:
    blob = text.encode()
    return (len(blob), len(gzip.compress(blob, 9)),
            len(zstandard.ZstdCompressor(level=3).compress(blob)))


def timed(fn, items) -> tuple[float, list]:
    started = time.perf_counter()
    out = [fn(item) for item in items]
    return (time.perf_counter() - started) * 1000, out


def main() -> None:
    rows = build(RECORDS)
    plain = jsonl(rows)
    inline = jsonl([{"@context": OBSERVATION_CONTEXT, **r} for r in rows])
    linked = jsonl([{"@context": CONTEXT_URL, **r} for r in rows])

    print(f"{RECORDS} buoy records as JSON Lines, PyLD "
          f"{jsonld.__version__ if hasattr(jsonld, '__version__') else ''}")
    print(f"{'form':<30}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    base = sizes(plain)
    for label, text in (("plain JSON", plain),
                        ("JSON-LD, context inline", inline),
                        ("JSON-LD, context by URL", linked)):
        raw, gz, zs = sizes(text)
        print(f"{label:<30}{raw:>12,}{gz:>12,}{zs:>12,}   "
              f"raw {100 * (raw / base[0] - 1):+6.1f}%  "
              f"gzip {100 * (gz / base[1] - 1):+6.1f}%")

    loader = CountingLoader()
    jsonld.set_document_loader(loader)
    lines = linked.splitlines()[:PROCESSED]
    docs = [json.loads(line) for line in lines]

    print()
    print(f"processing the first {PROCESSED:,} records (context by URL)")
    ms, _ = timed(json.loads, lines)
    print(f"  {'json.loads':<32}{ms:>10.1f} ms   {1000 * ms / PROCESSED:>8.1f} us/record")
    ms, _ = timed(jsonld.expand, docs)
    print(f"  {'jsonld.expand':<32}{ms:>10.1f} ms   {1000 * ms / PROCESSED:>8.1f} us/record")
    print(f"  context fetched {loader.calls:,} times for {PROCESSED:,} documents")
    loader.calls = 0
    normalise = lambda d: jsonld.normalize(                   # noqa: E731
        d, {"algorithm": "URDNA2015", "format": "application/n-quads"})
    ms, quads = timed(normalise, docs[:CANONICALISED])
    print(f"  {'jsonld.normalize (URDNA2015)':<32}{ms:>10.1f} ms   "
          f"{1000 * ms / CANONICALISED:>8.1f} us/record  ({CANONICALISED} records)")
    per_record = sum(len(q.encode()) for q in quads) / CANONICALISED
    print(f"  canonical N-Quads: {per_record:,.0f} bytes per record")


if __name__ == "__main__":
    main()

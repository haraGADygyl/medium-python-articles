"""JSON vs. TOML on the shared buoy payload: size, gzip, zstd, and time."""
import gc
import gzip
import json
import sys
import time
import tomllib
from importlib.metadata import version

import rtoml
import tomli
import tomli_w
import tomlkit
import zstandard

from convert import build, from_toml_doc, to_toml_doc

RUNS = 5
SLOW_MS = 20000  # anything slower than this runs once
RECORDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50000


def best(fn, *args) -> tuple[float, int, object]:
    """Best wall time in ms, the number of runs it took, and the last result."""
    fastest, runs, result = float("inf"), 0, None
    while runs < RUNS:
        gc.disable()
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
        runs += 1
        if fastest > SLOW_MS:
            break

    return fastest, runs, result


def gz(blob: bytes) -> int:
    return len(gzip.compress(blob, 9))


def zs(blob: bytes) -> int:
    return len(zstandard.ZstdCompressor(level=3).compress(blob))


def change(a: int, b: int) -> str:
    pct = 100 * (a / b - 1)
    return f"{abs(pct):.1f}% {'bigger' if pct > 0 else 'smaller'}"


def main() -> None:
    rows = build(RECORDS)
    doc = to_toml_doc(rows)
    nulls = sum(1 for row in rows if row["notes"] is None)
    libs = ", ".join(f"{name} {version(name)}"
                     for name in ("tomli_w", "tomli", "tomlkit", "rtoml"))
    print(f"{RECORDS} buoy records, best of up to {RUNS}; {libs}")
    print(f"notes is null in {nulls} records ({100 * nulls / RECORDS:.1f}%): "
          f"TOML has no null, so those keys are dropped")

    as_json = json.dumps(rows, separators=(",", ":")).encode()
    writers = {
        "TOML, tomli_w": lambda: tomli_w.dumps(doc),
        "TOML, rtoml": lambda: rtoml.dumps(doc, none_value=None),
        "TOML, tomlkit": lambda: tomlkit.dumps(doc),
    }
    timings = {"JSON": best(lambda: json.dumps(rows, separators=(",", ":")))}
    for label, write in writers.items():
        timings[label] = best(write)
    texts = {label: result.encode() for label, (_, _, result) in timings.items()}

    for label, blob in texts.items():
        if label != "JSON":
            assert from_toml_doc(tomllib.loads(blob.decode())) == rows, label

    print()
    print(f"{'format':<18}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}{'lines':>10}")
    for label, blob in texts.items():
        print(f"{label:<18}{len(blob):>12,}{gz(blob):>12,}{zs(blob):>12,}"
              f"{blob.count(b'\n'):>10,}")
    for label, blob in texts.items():
        if label != "JSON":
            print(f"  {label} vs JSON: raw {change(len(blob), len(as_json))}, "
                  f"gzip {change(gz(blob), gz(as_json))}, "
                  f"zstd {change(zs(blob), zs(as_json))}")

    json_ms = timings["JSON"][0]
    print()
    print(f"{'write, ms':<28}{'ms':>10}{'vs json':>9}{'runs':>6}")
    for label, (ms, runs, _) in timings.items():
        writer = "json.dumps" if label == "JSON" else label.split(", ")[1] + " dumps"
        print(f"{writer:<28}{ms:>10.1f}{ms / json_ms:>8.0f}x{runs:>6}")

    toml_text = texts["TOML, tomli_w"].decode()
    readers = {
        "json.loads": lambda: json.loads(as_json),
        "tomllib.loads (stdlib)": lambda: tomllib.loads(toml_text),
        "tomli.loads": lambda: tomli.loads(toml_text),
        "rtoml.loads": lambda: rtoml.loads(toml_text),
        "tomlkit.parse": lambda: tomlkit.parse(toml_text),
    }
    print()
    print(f"{'read, ms':<28}{'ms':>10}{'vs json':>9}{'runs':>6}")
    read_json = None
    for label, read in readers.items():
        ms, runs, _ = best(read)
        read_json = read_json or ms
        print(f"{label:<28}{ms:>10.1f}{ms / read_json:>8.0f}x{runs:>6}")

    shape_ms, _, _ = best(to_toml_doc, rows)
    parsed = tomllib.loads(toml_text)
    unshape_ms, _, _ = best(from_toml_doc, parsed)
    print()
    print(f"not included above: shaping rows for TOML {shape_ms:.1f} ms, "
          f"restoring them {unshape_ms:.1f} ms")
    print("every TOML writer round-trips the records, nulls restored by schema: True")


if __name__ == "__main__":
    main()

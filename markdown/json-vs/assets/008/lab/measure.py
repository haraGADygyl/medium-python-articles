"""Plain JSON vs. GeoJSON on the shared buoy payload: size, load, zone query."""
import gc
import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np
import shapely
import zstandard

from geo import APPROACH_ZONE, to_collection

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402

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


def count_plain(text: str, zone) -> int:
    """Our own schema: pull lat/lon out by name, build points, test them."""
    rows = json.loads(text)
    lon = np.fromiter((r["position"]["lon"] for r in rows), float, len(rows))
    lat = np.fromiter((r["position"]["lat"] for r in rows), float, len(rows))
    return int(shapely.contains_xy(zone, lon, lat).sum())


def count_geojson_json(text: str, zone) -> int:
    """GeoJSON through json.loads: the schema tells you where x and y are."""
    features = json.loads(text)["features"]
    xy = np.array([f["geometry"]["coordinates"] for f in features])
    return int(shapely.contains_xy(zone, xy[:, 0], xy[:, 1]).sum())


def count_geojson(text: str, zone) -> int:
    """GeoJSON: GEOS reads the geometries directly (and drops properties)."""
    points = shapely.get_parts(shapely.from_geojson(text))
    return int(shapely.contains(zone, points).sum())


def main() -> None:
    rows = build(RECORDS)
    plain = json.dumps(rows, separators=(",", ":"))
    geo = json.dumps(to_collection(rows), separators=(",", ":"))
    zone = shapely.from_geojson(json.dumps(APPROACH_ZONE))
    shapely.prepare(zone)

    print(f"{RECORDS} buoy records, best of {RUNS}, shapely "
          f"{shapely.__version__} (GEOS {shapely.geos_version_string})")
    print()
    print(f"{'format':<22}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for label, text in (("plain JSON", plain), ("GeoJSON collection", geo)):
        raw, gz, zs = sizes(text.encode())
        print(f"{label:<22}{raw:>12,}{gz:>12,}{zs:>12,}")
    (pr, pg, pz), (gr, gg, gz_) = sizes(plain.encode()), sizes(geo.encode())
    print(f"  GeoJSON vs plain: raw {100 * (gr / pr - 1):+.1f}%, "
          f"gzip {100 * (gg / pg - 1):+.1f}%, zstd {100 * (gz_ / pz - 1):+.1f}%")

    print()
    print("observations inside the approach zone")
    ms, n = best(count_plain, plain, zone)
    print(f"  {'plain JSON + json.loads':<34}{ms:>8.1f} ms   {n:,}")
    ms, n = best(count_geojson, geo, zone)
    print(f"  {'GeoJSON + shapely.from_geojson':<34}{ms:>8.1f} ms   {n:,}")
    ms, n = best(count_geojson_json, geo, zone)
    print(f"  {'GeoJSON + json.loads':<34}{ms:>8.1f} ms   {n:,}")


if __name__ == "__main__":
    main()

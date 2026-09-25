"""GeoJSON vs. TopoJSON: forecast cells with shared borders, and the payload's points."""
import gzip
import json
import subprocess
from pathlib import Path

import numpy as np
import shapely
import zstandard

from cells import LAT0, LAT1, LON0, LON1, build_cells

HERE = Path(__file__).resolve().parent
METRES_PER_DEG_LAT = 111_320


def node(mode: str, arg: str, payload: str) -> str:
    return subprocess.run(["node", str(HERE / "topo.js"), mode, arg],
                          input=payload, capture_output=True, text=True,
                          check=True, cwd=HERE).stdout


def sizes(text: str) -> tuple[int, int, int]:
    blob = text.encode()
    return (len(blob), len(gzip.compress(blob, 9)),
            len(zstandard.ZstdCompressor(level=3).compress(blob)))


def worst_error_m(original: dict, decoded: dict) -> float:
    """Largest distance from an original vertex to its nearest decoded one.

    Nearest, not same-index: TopoJSON may start a decoded ring at a
    different vertex, so position i in one ring is not position i in the other.
    """
    worst = 0.0
    for a, b in zip(original["features"], decoded["features"]):
        ra = np.array(a["geometry"]["coordinates"][0])
        rb = np.array(b["geometry"]["coordinates"][0])
        scale = np.array([np.cos(np.radians(ra[:, 1].mean())), 1.0])
        diff = (ra[:, None, :] - rb[None, :, :]) * scale * METRES_PER_DEG_LAT
        nearest = np.sqrt((diff ** 2).sum(axis=2)).min(axis=1)
        worst = max(worst, float(nearest.max()))
    return worst


def gaps_and_overlaps_km2(collection: dict) -> float:
    """Area where the cells no longer tile the frame exactly."""
    polygons = [shapely.from_geojson(json.dumps(f["geometry"]))
                for f in collection["features"]]
    frame = shapely.box(LON0, LAT0, LON1, LAT1)
    union = shapely.union_all(polygons)
    total = sum(p.area for p in polygons)
    mismatch_deg2 = (frame.area - union.area) + (total - union.area)
    km_per_deg_lon = 111.32 * np.cos(np.radians((LAT0 + LAT1) / 2))
    return mismatch_deg2 * 111.32 * km_per_deg_lon


def main() -> None:
    cells = build_cells()
    geo = json.dumps(cells, separators=(",", ":"))
    polygons = [shapely.from_geojson(json.dumps(f["geometry"]))
                for f in cells["features"]]
    vertices = sum(len(f["geometry"]["coordinates"][0])
                   for f in cells["features"])
    print(f"{len(polygons)} forecast cells, {vertices:,} ring vertices, "
          f"all valid: {all(p.is_valid for p in polygons)}")

    print()
    print(f"{'encoding':<26}{'bytes':>10}{'gzip -9':>10}{'zstd -3':>10}"
          f"{'worst error':>13}")
    raw, gz, zs = sizes(geo)
    print(f"{'GeoJSON':<26}{raw:>10,}{gz:>10,}{zs:>10,}{'-':>13}")
    for q in (0, 1_000_000, 100_000, 10_000):
        topo = node("encode", str(q), geo)
        back = json.loads(node("decode", "", topo))
        raw, gz, zs = sizes(topo)
        label = "TopoJSON, no quantization" if not q else f"TopoJSON, q={q:,}"
        print(f"{label:<26}{raw:>10,}{gz:>10,}{zs:>10,}"
              f"{worst_error_m(cells, back):>11.2f} m")
        if q == 0:
            arcs = len(json.loads(topo)["arcs"])

    edges = sum(4 for _ in cells["features"])
    print()
    print(f"borders: {edges} written in GeoJSON (4 per cell), "
          f"{arcs} arcs in TopoJSON")

    timing = json.loads(node("timing", "100000", geo))
    print(f"reference implementation, q=100,000: encode "
          f"{timing['encMs']:.1f} ms, decode to GeoJSON {timing['decMs']:.1f} ms "
          f"(JSON.parse of the GeoJSON: {timing['parseMs']:.1f} ms)")

    topo = node("encode", "100000", geo)
    shared = json.loads(node("simplify", "0.2", topo))
    shared_kept = sum(len(f["geometry"]["coordinates"][0])
                      for f in shared["features"])

    # Give shapely the same vertex budget: search for the matching tolerance.
    low, high = 0.0, 0.05
    for _ in range(40):
        tolerance = (low + high) / 2
        kept = [shapely.simplify(poly, tolerance) for poly in polygons]
        shapely_kept = sum(len(p.exterior.coords) for p in kept)
        low, high = (tolerance, high) if shapely_kept > shared_kept else (low, tolerance)
    independent = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": json.loads(shapely.to_geojson(p))} for p in kept]}

    print()
    print(f"simplify the cells to about {100 * shared_kept / vertices:.0f}% "
          f"of their vertices, then check they still tile the frame")
    print(f"  {'shapely, each cell alone':<30}{shapely_kept:>7,} vertices   "
          f"gaps + overlaps {gaps_and_overlaps_km2(independent):.3f} km2")
    print(f"  {'topojson-simplify, shared':<30}{shared_kept:>7,} vertices   "
          f"gaps + overlaps {gaps_and_overlaps_km2(shared):.3f} km2")


def points() -> None:
    """The payload's 50,000 observations: points, and properties that dominate."""
    import sys
    sys.path.insert(0, str(HERE.parents[1] / "payload"))
    from make_payload import build
    rows = build(50000)
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates":
                      [r["position"]["lon"], r["position"]["lat"]]},
         "properties": {k: v for k, v in r.items() if k != "position"}}
        for r in rows]}
    geo = json.dumps(collection, separators=(",", ":"))
    topo = node("encode", "100000", geo)
    print()
    print("the payload's 50,000 observations as points")
    for label, text in (("GeoJSON", geo), ("TopoJSON, q=100,000", topo)):
        raw, gz, zs = sizes(text)
        print(f"  {label:<24}{raw:>12,}{gz:>12,}{zs:>12,}")


if __name__ == "__main__":
    main()
    points()

"""Sea-state forecast cells over the buoy fleet, as GeoJSON.

A 16 x 10 grid across the payload's bounding box. Every border between two
cells is one jagged line, generated once and used by both neighbours, the way
real administrative or maritime boundaries are shared. Each cell carries the
mean wave height of the payload observations that fall inside it.
"""
import json
import random
import sys
from pathlib import Path

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402

SEED = 20260925
COLS, ROWS = 16, 10
LON0, LON1, LAT0, LAT1 = -2.6, -1.8, 56.9, 57.4
POINTS_PER_EDGE = 24            # interior vertices on each shared border
JITTER = 0.25                   # of a cell's width, perpendicular to the border


def build_cells(records: int = 50000) -> dict:
    rng = random.Random(SEED)
    dx, dy = (LON1 - LON0) / COLS, (LAT1 - LAT0) / ROWS

    def corner(i: int, j: int) -> tuple[float, float]:
        return (round(LON0 + i * dx, 6), round(LAT0 + j * dy, 6))

    def jagged(a, b, along_x: bool) -> list[tuple[float, float]]:
        """Interior vertices of the border from a to b, jittered sideways."""
        points = []
        for k in range(1, POINTS_PER_EDGE + 1):
            t = k / (POINTS_PER_EDGE + 1)
            x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            wobble = rng.uniform(-JITTER, JITTER)
            if along_x:
                y += wobble * dy * 4 * t * (1 - t)
            else:
                x += wobble * dx * 4 * t * (1 - t)
            points.append((round(x, 6), round(y, 6)))
        return points

    # Borders on the outer frame stay straight; inner borders are jagged.
    horizontal = {(i, j): ([] if j in (0, ROWS) else
                           jagged(corner(i, j), corner(i + 1, j), True))
                  for i in range(COLS) for j in range(ROWS + 1)}
    vertical = {(i, j): ([] if i in (0, COLS) else
                         jagged(corner(i, j), corner(i, j + 1), False))
                for i in range(COLS + 1) for j in range(ROWS)}

    rows = build(records)
    lon = np.array([r["position"]["lon"] for r in rows])
    lat = np.array([r["position"]["lat"] for r in rows])
    wave = np.array([r["wave_height_m"] for r in rows])

    features = []
    for j in range(ROWS):
        for i in range(COLS):
            ring = [corner(i, j), *horizontal[(i, j)],            # south, W->E
                    corner(i + 1, j), *vertical[(i + 1, j)],      # east, S->N
                    corner(i + 1, j + 1),
                    *reversed(horizontal[(i, j + 1)]),            # north, E->W
                    corner(i, j + 1),
                    *reversed(vertical[(i, j)]),                  # west, N->S
                    corner(i, j)]
            polygon = shapely.Polygon(ring)
            inside = shapely.contains_xy(polygon, lon, lat)
            features.append({
                "type": "Feature",
                "properties": {
                    "cell_id": f"C{j:02d}{i:02d}",
                    "observations": int(inside.sum()),
                    "mean_wave_m": round(float(wave[inside].mean()), 3)
                    if inside.any() else None,
                },
                "geometry": {"type": "Polygon",
                             "coordinates": [[list(p) for p in ring]]},
            })
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    cells = build_cells()
    print(json.dumps(cells["features"][0]["properties"]),
          len(cells["features"]),
          len(cells["features"][0]["geometry"]["coordinates"][0]))

# JSON vs. TopoJSON

#### Store each border once instead of twice: 61% smaller gzipped for a map of forecast cells, and simplification that cannot tear the map apart

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

GeoJSON writes every polygon on its own. When two regions share a border, the border is written twice, once in each polygon, vertex for vertex. For a map of countries, counties or sea areas, where almost every border is shared, that means most of the file is stored twice.

TopoJSON, Mike Bostock's extension of GeoJSON, stores the **topology** instead. Each border becomes one **arc**, written once, and each polygon lists the arcs that make up its ring. Coordinates are also quantized to integers on a grid and delta-encoded, so each vertex is a small step from the previous one rather than a pair of long decimals. It was built for web maps, where a smaller file means a faster first paint.

The previous article in this series measured GeoJSON on the fleet's points. This one tests the shape TopoJSON was designed for. I split the buoy fleet's sea area into 160 forecast cells with irregular shared borders, each carrying the mean wave height of the payload observations inside it. TopoJSON cut that file by 61% after gzip. At the same vertex budget, it simplified the map with no gaps, where simplifying each cell alone left 30 km² of gaps and overlaps.

---

### The same shapes, both ways

Two adjacent square cells as GeoJSON, each ring written in full, 370 bytes compact:

```json
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "properties": {"cell_id": "C0000"},
   "geometry": {"type": "Polygon", "coordinates": [[[-2.6, 56.9], [-2.55, 56.9],
     [-2.55, 56.95], [-2.6, 56.95], [-2.6, 56.9]]]}},
  {"type": "Feature", "properties": {"cell_id": "C0001"},
   "geometry": {"type": "Polygon", "coordinates": [[[-2.55, 56.9], [-2.5, 56.9],
     [-2.5, 56.95], [-2.55, 56.95], [-2.55, 56.9]]]}}
]}
```

The same two cells through the reference encoder, `topojson-server`, with a quantization of 10,000. Arcs, indexes and a transform replace the coordinates. Here it is inside a script that decodes it by hand:

```python
import json
from itertools import accumulate

topology = json.loads("""{
  "type": "Topology",
  "objects": {"cells": {"type": "GeometryCollection", "geometries": [
    {"type": "Polygon", "arcs": [[0, 1]], "properties": {"cell_id": "C0000"}},
    {"type": "Polygon", "arcs": [[2, -1]], "properties": {"cell_id": "C0001"}}
  ]}},
  "arcs": [
    [[5000, 0], [0, 9999]],
    [[5000, 9999], [-5000, 0], [0, -9999], [5000, 0]],
    [[5000, 0], [4999, 0], [0, 9999], [-4999, 0]]
  ],
  "bbox": [-2.6, 56.9, -2.5, 56.95],
  "transform": {"scale": [0.00001000100010001001, 0.000005000500050005427],
                "translate": [-2.6, 56.9]}
}""")


def decode_arc(arc: list[list[int]], transform: dict) -> list[tuple]:
    """Undo delta encoding, then quantization: integers back to degrees."""
    (sx, sy), (tx, ty) = transform["scale"], transform["translate"]
    xs = accumulate(point[0] for point in arc)
    ys = accumulate(point[1] for point in arc)
    return [(round(x * sx + tx, 6), round(y * sy + ty, 6))
            for x, y in zip(xs, ys)]


def ring(arc_indexes: list[int], arcs: list[list[tuple]]) -> list[tuple]:
    """Stitch arcs into a ring; a negative index ~i means arc i reversed."""
    points: list[tuple] = []
    for index in arc_indexes:
        arc = arcs[index] if index >= 0 else arcs[~index][::-1]
        points.extend(arc if not points else arc[1:])
    return points


arcs = [decode_arc(arc, topology["transform"]) for arc in topology["arcs"]]
for cell in topology["objects"]["cells"]["geometries"]:
    print(cell["properties"]["cell_id"], ring(cell["arcs"][0], arcs))
# C0000 [(-2.549995, 56.9), (-2.549995, 56.95), (-2.6, 56.95), (-2.6, 56.9), ...]
# C0001 [(-2.549995, 56.9), (-2.5, 56.9), (-2.5, 56.95), (-2.549995, 56.95), ...]
```

Arc 0 is the shared border, from `[5000, 0]` a step of `[0, 9999]` north. The western cell uses it as `0`, and the eastern cell as `-1`, which is `~0`: the same arc walked backwards. Each arc's first point is absolute on a 10,000-step grid, and every later point is a delta from the one before. The transform maps grid steps back to degrees.

The decoded output shows the cost too. The shared border comes back at longitude `-2.549995`, not `-2.55`: quantization moved it about 30 cm to the nearest grid line. And at 455 bytes, this two-cell TopoJSON is *bigger* than the 370-byte GeoJSON. With one short shared border, the arcs, indexes and transform cost more than they save.

---

### What TopoJSON actually changes

Borders stop being duplicated. The 160 forecast cells have 640 sides as GeoJSON writes them, four per cell. As TopoJSON they are 342 arcs: every inner border once, plus the outer frame merged into long runs.

Precision becomes a parameter. Quantization picks the grid, and the grid decides both the size and the error. There is no free setting: you choose how many metres of error the map can take.

The map knows which shapes are neighbours. Because a border is one object, `topojson-client`'s `mesh` can return just the inner borders, drawn once, for a stroke without doubled lines. `topojson-simplify` can remove vertices from an arc and have both neighbours change the same way. Simplifying GeoJSON polygons one at a time cannot promise that, and the measurement shows what happens.

And it is no longer GeoJSON. A TopoJSON file has to be decoded by `topojson-client` or a port of it before most tools can use it. The format is a specification on GitHub, not an RFC.

---

### The measurement

160 cells, 14,912 ring vertices, encoded with `topojson-server` 3.0.1. "Worst error" is the largest distance from an original vertex to the nearest decoded one:

```
encoding                       bytes   gzip -9   zstd -3  worst error
GeoJSON                      296,826    59,169    65,145            -
TopoJSON, no quantization    160,539    42,537    44,740       0.00 m
TopoJSON, q=1,000,000        122,798    27,136    28,572       0.04 m
TopoJSON, q=100,000          107,429    22,952    24,693       0.37 m
TopoJSON, q=10,000            92,123    18,373    20,307       3.69 m

simplify the cells to about 24% of their vertices, then check they still tile the frame
  shapely, each cell alone        3,623 vertices   gaps + overlaps 30.439 km2
  topojson-simplify, shared       3,618 vertices   gaps + overlaps 0.000 km2

the payload's 50,000 observations as points
  GeoJSON                   23,340,549   1,905,078   2,370,374
  TopoJSON, q=100,000       21,518,358   1,837,799   2,244,267
```

Sharing arcs alone, with no quantization, removed 46% of the raw bytes. At a quantization of 100,000, where the worst vertex moved 37 cm, the file was 64% smaller raw and 61% smaller gzipped. That compressed saving is the one that matters for a web map, and it survives compression because the duplication was real, not just repeated text. Going to 10,000 took another 20% off the gzipped size, at 3.69 m of error.

The simplification row is the reason topology exists. Both methods kept about 3,620 vertices. Simplifying each GeoJSON cell alone treated each shared border twice, and the two copies came out different. Across the frame, that left 30.4 km² of slivers and overlaps, about 1.1% of the area. Simplifying the shared arcs left none.

Encoding and decoding cost little: 3.5 ms to build the topology and 0.6 ms to turn it back into GeoJSON.

---

### Where JSON still wins

For points. The payload's 50,000 observations saved 7.8% raw and 3.5% gzipped. Points share no borders, and the properties (ids, wave heights, sensor lists) are most of the bytes. TopoJSON cannot shrink those.

For small files. The two-cell example was 23% bigger as TopoJSON. The gain grows with the number of shared vertices, and a handful of shapes does not have enough of them.

For tools. GeoJSON is RFC 7946 and read natively by PostGIS, GEOS, QGIS and every web map library. TopoJSON is mostly JavaScript, with the D3 ecosystem at its centre, and everything else needs a decode step first.

For editing and precision. Moving one border means re-encoding the topology, and every quantized file is lossy by the amount you chose. For survey-grade coordinates or data you keep editing, GeoJSON's plain decimals are the safer store.

---

### Conclusion

Use TopoJSON to ship polygon maps with shared borders to a browser: administrative areas, forecast zones, choropleths. On these 160 cells it cut the gzipped download by 61% at 37 cm of error. It also makes border rendering and simplification consistent, which GeoJSON cannot do.

Keep GeoJSON as the source of truth, and for points, small collections, and anything a spatial database or GIS will read. Generate TopoJSON from it as a build step.

The cost is a decode step before most tools can read the file, quantization error you have to choose, and a format that pays off only for shapes that share borders. For points and for small files, TopoJSON is the bigger of the two.

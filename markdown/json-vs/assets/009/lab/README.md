# Lab — 009, JSON vs. TopoJSON

TopoJSON's case is polygons that share borders, and the series payload is points, so
this lab derives a polygon map from it: `cells.py` splits the payload's bounding box
into 160 sea-state forecast cells (16 x 10) whose inner borders are jagged lines,
each generated once and used by both neighbours. Each cell carries the count and mean
wave height of the payload observations inside it. The payload's own 50,000 points
are measured too.

Python 3.12.3 with `shapely==2.1.2`, `numpy==2.5.3`, `zstandard==0.23.0`; Node
v24.20.0 with the reference implementation — `topojson-server@3.0.1`,
`topojson-client@3.1.0`, `topojson-simplify@3.0.3` — pinned in `package.json` /
`package-lock.json`, driven through `topo.js`.

```bash
pip install shapely==2.1.2 numpy==2.5.3 zstandard==0.23.0
npm ci
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size at four quantizations, round-trip error, arcs, simplification gaps, points | `python3 measure.py` | `output-topojson.txt` |
| Decode a two-cell TopoJSON by hand (`pair.topojson`, from `pair.geojson`) | `python3 snippets.py` | `output-snippets.txt` |

**Round-trip error** is the largest distance from an original vertex to the nearest
decoded vertex of the same cell, in metres. Nearest, not same-index: TopoJSON may
start a decoded ring at a different vertex.

**Simplification.** `topojson-simplify` keeps the top 20% of vertex weights on the
shared arcs; `shapely.simplify` is then given the same vertex budget (tolerance found
by bisection) and applied to each cell alone. "Gaps + overlaps" is the frame area
not covered by the union plus the area covered more than once, in km².

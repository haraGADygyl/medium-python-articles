"""The snippet the article shows: decode a TopoJSON ring by hand."""
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

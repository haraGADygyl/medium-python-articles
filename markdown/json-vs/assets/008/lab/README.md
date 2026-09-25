# Lab — 008, JSON vs. GeoJSON

Python 3.12.3, `shapely==2.1.2` (GEOS 3.13.1), `geojson==3.3.0`, `numpy==2.5.3`,
`zstandard==0.23.0`, Ryzen 5 3600. The payload is the series' shared dataset,
generated in memory by `../../payload/make_payload.py`; `geo.py` turns it into a
RFC 7946 FeatureCollection (position -> Point geometry, everything else ->
properties) and defines the approach-zone Polygon.

```bash
pip install shapely==2.1.2 geojson==3.3.0 numpy==2.5.3 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size of plain JSON vs FeatureCollection; zone query three ways | `python3 measure.py` | `output-geojson.txt` |
| The snippets in the article: Feature, swapped coordinates, dropped properties, a drift track | `python3 snippets.py` | `output-snippets.txt` |

**The three zone-query paths** all count the same 6,355 observations: our own
schema through `json.loads`; GeoJSON through `json.loads`, taking
`coordinates[0]`/`[1]` as x/y; and GeoJSON handed whole to GEOS with
`shapely.from_geojson`, which returns geometries and discards `properties`.

Distances use the haversine formula on a 6,371 km sphere. Timings are best of five
with the cyclic GC paused; they move by roughly ±10% between runs, sizes do not.

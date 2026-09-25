# JSON vs. GeoJSON

#### 12.3% more bytes, 1.7% after gzip, for a schema every map tool reads — and a coordinate order that puts a swapped buoy 8,470 km away

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

Every record in this series has a position: `{"lat": 57.21621, "lon": -2.37579}`. That is a perfectly good schema, and it is ours. A map library, a spatial database or a GIS desktop app has no idea that `lat` and `lon` are coordinates until someone writes the glue code that says so. Everyone who has put points on a map has written that glue code more than once.

GeoJSON removes the conversation. It is JSON with a fixed shape for geography, standardised as RFC 7946 in 2016. A `Feature` has a `geometry` and `properties`, a geometry has a `type` and `coordinates`, and all coordinates are longitude and latitude on WGS 84. Anything that speaks GeoJSON can draw, index or query your data without being told what your fields mean.

I converted the series' 50,000 buoy observations into a GeoJSON FeatureCollection and measured three things. The file grew 12.3% raw and 1.7% gzipped. The spatial tools read it directly, and one of them dropped every property on the way in. And writing latitude first, the most common GeoJSON bug, moved a buoy from the North Sea to the Indian Ocean without any validator objecting.

---

### The same record, both ways

A shortened observation, and the same observation turned into a Feature:

```python
import json
import math

import geojson
import shapely

reading = {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5,
    "qc_passed": True,
}

feature = {
    "type": "Feature",
    "geometry": {"type": "Point",
                 "coordinates": [reading["position"]["lon"],
                                 reading["position"]["lat"]]},
    "properties": {k: v for k, v in reading.items() if k != "position"},
}
print(json.dumps(feature["geometry"]))
# {"type": "Point", "coordinates": [-2.37579, 57.21621]}
```

Printed in full, the Feature reads:

```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [-2.37579, 57.21621]},
  "properties": {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "wave_height_m": 3.5,
    "qc_passed": true
  }
}
```

Three things changed. The position left the record and became a `geometry`, the one part of a Feature that tools interpret. Everything else moved into `properties`, which GeoJSON treats as opaque: any JSON is allowed, and nothing in it is understood. And the named `lat` and `lon` became a bare two-element array in which the *order* carries the meaning: `[longitude, latitude]`, x before y.

The Point is the simplest of GeoJSON's types. There are also `LineString`, `Polygon`, their `Multi` versions and `GeometryCollection`, enough for tracks, zones, coastlines and shipping lanes.

---

### What GeoJSON actually changes

Order replaces names, and that is the format's sharpest edge. People say "lat, long" and write it that way. Many mapping APIs take latitude first. GeoJSON takes longitude first. Swap them and nothing complains:

```python
def distance_km(a: list[float], b: list[float]) -> float:
    """Haversine distance between two [lon, lat] pairs on a 6,371 km sphere."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


right = [-2.37579, 57.21621]           # [longitude, latitude]
swapped = [57.21621, -2.37579]         # latitude written first

print(geojson.Point(swapped).is_valid)    # True
print(round(distance_km(right, swapped)))  # 8470
```

The swapped buoy sits 8,470 km away, just south of the equator north-east of the Seychelles. `geojson`'s validator calls it valid because it is: 57.2 is a legal longitude and −2.4 a legal latitude. A swap is caught only when a value falls outside the other axis's range, which for most of the inhabited world it does not. Our named `{"lat", "lon"}` object could not be misread this way. The only reliable defence is a check that knows where your data should be: a bounding box for the fleet, tested on every write, turns this silent 8,470 km error into a rejected record.

What you gain is reach. GitHub renders a `.geojson` file as a map. PostGIS reads it with `ST_GeomFromGeoJSON`, and Leaflet, Mapbox, QGIS and `shapely` all read it without a line of glue. The approach zone in this lab is a GeoJSON Polygon, and `shapely` tests all 50,000 points against it without knowing anything about buoys. RFC 7946 also fixes decisions a home-grown schema leaves open: WGS 84 only, exterior polygon rings counter-clockwise, and six decimal places, about 10 cm, as a sensible precision.

But tools read the geometry, not the Feature:

```python
point = shapely.from_geojson(json.dumps(feature))
print(point)                        # POINT (-2.37579 57.21621)
print(shapely.to_geojson(point))
# {"type":"Point","coordinates":[-2.37579,57.21621]}
```

GEOS, the geometry engine under `shapely` and PostGIS, returns the Point and discards `properties`. For a spatial query that is fine. For a round trip it is not: read and write the file through the geometry library and the wave heights are gone.

GeoJSON also has no time. RFC 7946 allows a third coordinate for altitude and advises against anything more. A buoy's drift over an hour becomes a `LineString`, and its timestamps have to go into `properties` as a parallel array that no tool knows to line up with the vertices.

---

### The measurement

All 50,000 observations as a FeatureCollection, against the plain payload:

```
format                       bytes     gzip -9     zstd -3
plain JSON              20,790,509   1,872,392   2,344,331
GeoJSON collection      23,340,549   1,905,078   2,370,374
  GeoJSON vs plain: raw +12.3%, gzip +1.7%, zstd +1.1%

observations inside the approach zone
  plain JSON + json.loads              328.6 ms   6,355
  GeoJSON + shapely.from_geojson       977.1 ms   6,355
  GeoJSON + json.loads                 370.0 ms   6,355
```

The structure costs 2.5 MB raw: `"type":"Feature"`, `"geometry"`, `"type":"Point"` and `"properties"` on every record. It is exactly the kind of repetition a compressor removes, and gzipped the difference is 1.7%. Over HTTP with compression on, the standard format is almost free.

All three routes found the same 6,355 observations in the zone. Parsing with `json.loads` and taking coordinates by position was the fast path, 370.0 ms against 328.6 for our own schema. Handing the whole file to GEOS with `shapely.from_geojson` took 977.1 ms, 2.6 times as long, and returned geometry without properties. The standard format did not make the query faster. It made it possible without writing a schema adapter.

---

### Where JSON still wins

When nothing on the other end is a map. An analytics job, a dashboard or an API client that wants a wave height and a buoy id gains nothing from a `Feature` wrapper. It pays 12.3% raw to reach through `properties` for the fields that matter.

When the data is a time series. A position that changes every ten minutes is a row with a timestamp. GeoJSON can store it only as a point per observation or as a line with a side array of times.

When names are safer than order. `{"lat": ..., "lon": ...}` cannot be read backwards. `[x, y]` can, and the lab's validator will not notice.

---

### Conclusion

Use GeoJSON whenever the data will meet spatial tooling: maps, spatial databases, GIS, anything that draws, indexes or tests shapes. The price is 12.3% raw, 1.7% gzipped, and one ordering rule you must get right. In return, a dozen tools read your data with no glue code.

Keep plain JSON for records whose position is one attribute among many and whose consumers are not spatial. Convert at the edge, where the map is.

The cost of GeoJSON is that meaning moves from names to positions. `[longitude, latitude]` must be right on every write. A swap passes every structural check, the properties can vanish through a geometry library, and time has nowhere to live.

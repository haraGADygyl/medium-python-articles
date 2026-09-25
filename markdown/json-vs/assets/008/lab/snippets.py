"""The snippets the article shows, run end to end."""
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

print("--- swap")


def distance_km(a: list[float], b: list[float]) -> float:
    """Haversine distance between two [lon, lat] pairs on a 6,371 km sphere."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


right = [-2.37579, 57.21621]           # [longitude, latitude]
swapped = [57.21621, -2.37579]         # latitude written first

print(geojson.Point(swapped).is_valid)
print(round(distance_km(right, swapped)))

print("--- properties")
point = shapely.from_geojson(json.dumps(feature))
print(point)
print(shapely.to_geojson(point))

print("--- track")
drift = [
    ("2026-02-11T00:00:00+00:00", -2.37579, 57.21621),
    ("2026-02-11T00:10:00+00:00", -2.37541, 57.21655),
    ("2026-02-11T00:20:00+00:00", -2.37502, 57.21690),
]
track = {
    "type": "Feature",
    "geometry": {"type": "LineString",
                 "coordinates": [[lon, lat] for _, lon, lat in drift]},
    "properties": {"buoy_id": "NE-08",
                   "recorded_at": [stamp for stamp, _, _ in drift]},
}
print(shapely.from_geojson(json.dumps(track)).length > 0,
      len(track["properties"]["recorded_at"]))

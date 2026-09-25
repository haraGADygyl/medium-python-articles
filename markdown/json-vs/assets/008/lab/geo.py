"""Shared helpers: the payload as GeoJSON, and a zone to query against."""
# A rectangular exclusion zone around the harbour approach, as GeoJSON.
# Exterior ring counter-clockwise, as RFC 7946 section 3.1.6 asks.
APPROACH_ZONE = {
    "type": "Polygon",
    "coordinates": [[[-2.30, 57.05], [-2.05, 57.05], [-2.05, 57.25],
                     [-2.30, 57.25], [-2.30, 57.05]]],
}


def to_feature(row: dict) -> dict:
    """One buoy observation as a GeoJSON Feature: [longitude, latitude]."""
    properties = {k: v for k, v in row.items() if k != "position"}
    return {
        "type": "Feature",
        "geometry": {"type": "Point",
                     "coordinates": [row["position"]["lon"],
                                     row["position"]["lat"]]},
        "properties": properties,
    }


def to_collection(rows: list[dict]) -> dict:
    return {"type": "FeatureCollection",
            "features": [to_feature(r) for r in rows]}


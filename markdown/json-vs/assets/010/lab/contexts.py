"""JSON-LD contexts for the buoy payload, and a counting offline loader.

Real vocabularies where they exist: W3C SOSA for observations, W3C Basic Geo for
positions, XML Schema for datatypes. Measurements have no standard term, so they
live under a vocabulary the fleet owns.
"""
CONTEXT_URL = "https://harbour-buoys.example/contexts/observation.jsonld"
TERMS = "https://harbour-buoys.example/terms#"

OBSERVATION_CONTEXT = {
    "sosa": "http://www.w3.org/ns/sosa/",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "fleet": TERMS,
    "observation_id": "fleet:observationId",
    "buoy_id": "sosa:madeBySensor",
    "recorded_at": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
    "position": "fleet:position",
    "lat": "geo:lat",
    "lon": "geo:long",
    "wave_height_m": "fleet:significantWaveHeightMetres",
    "water_temp_c": "fleet:waterTemperatureCelsius",
    "wind_gust_ms": "fleet:windGustMetresPerSecond",
    "qc_passed": "fleet:qualityControlPassed",
    "notes": "fleet:notes",
    "sensors": {"@id": "fleet:sensor", "@container": "@list"},
    "tag": "fleet:sensorTag",
    "status": "fleet:sensorStatus",
    "samples": "fleet:sampleCount",
    # battery_v deliberately left out: see what expansion does with it.
}

# A second agency publishing the same kind of reading under its own names.
AGENCY_CONTEXT = {
    "sosa": "http://www.w3.org/ns/sosa/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "fleet": TERMS,
    "station": "sosa:madeBySensor",
    "obs_time": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
    "hs": "fleet:significantWaveHeightMetres",
}


class CountingLoader:
    """Serves the context from memory and counts how often it is asked."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, url: str, options: dict | None = None) -> dict:
        self.calls += 1
        return {"contentType": "application/ld+json", "contextUrl": None,
                "documentUrl": url,
                "document": {"@context": OBSERVATION_CONTEXT}}

"""The snippets the article shows, run end to end."""
import json

from pyld import jsonld

fleet_context = {
    "sosa": "http://www.w3.org/ns/sosa/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "fleet": "https://harbour-buoys.example/terms#",
    "buoy_id": "sosa:madeBySensor",
    "recorded_at": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
    "wave_height_m": "fleet:significantWaveHeightMetres",
}

ours = {
    "@context": fleet_context,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "wave_height_m": 3.5,
    "battery_v": 13.12,
}

expanded = jsonld.expand(ours)[0]
for iri, values in expanded.items():
    print(iri, values)
# http://www.w3.org/ns/sosa/madeBySensor [{'@value': 'NE-08'}]
# http://www.w3.org/ns/sosa/resultTime [{'@type': 'http://www.w3.org/2001/XMLSchema#dateTime', ...}]
# https://harbour-buoys.example/terms#significantWaveHeightMetres [{'@value': 3.5}]
print(any("battery" in iri for iri in expanded))  # False

theirs = {
    "@context": {
        "sosa": "http://www.w3.org/ns/sosa/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "station": "sosa:madeBySensor",
        "obs_time": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
        "hs": "https://harbour-buoys.example/terms#significantWaveHeightMetres",
    },
    "station": "NE-08",
    "obs_time": "2026-02-11T00:00:00+00:00",
    "hs": 3.5,
}

print(jsonld.expand(theirs) == jsonld.expand(ours))  # True

in_our_terms = jsonld.compact(theirs, fleet_context)
del in_our_terms["@context"]
print(json.dumps(in_our_terms))
# {"buoy_id": "NE-08", "recorded_at": "2026-02-11T00:00:00+00:00", "wave_height_m": 3.5}

CONTEXT_URL = "https://harbour-buoys.example/contexts/observation.jsonld"
PINNED = {CONTEXT_URL: {"@context": fleet_context}}


def pinned_loader(url: str, options: dict | None = None) -> dict:
    """Serve known contexts from memory; refuse to fetch anything else."""
    if url not in PINNED:
        raise ValueError(f"context not pinned: {url}")
    return {"contentType": "application/ld+json", "contextUrl": None,
            "documentUrl": url, "document": PINNED[url]}


jsonld.set_document_loader(pinned_loader)
linked = {"@context": CONTEXT_URL, "buoy_id": "NE-08", "wave_height_m": 3.5}
print(len(jsonld.expand(linked)[0]))  # 2

try:
    jsonld.expand({"@context": "https://elsewhere.example/ctx.jsonld", "a": 1})
except jsonld.JsonLdError as exc:
    print(f"JsonLdError: {exc.type}")  # JsonLdError: jsonld.InvalidUrl

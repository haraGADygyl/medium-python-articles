# JSON vs. JSON-LD

#### A context turns field names into global identifiers so data from two producers merges without a meeting — and silently drops every key you forgot to map

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

A JSON key means whatever the two sides agreed it means. Our buoys report `wave_height_m`. A neighbouring agency reports the same measurement as `hs`, the oceanographer's shorthand for significant wave height, and its timestamp as `obs_time`. Combining the two feeds means a mapping table, a meeting to agree it, and code that breaks when either side renames a field.

JSON-LD, a W3C Recommendation whose current version 1.1 dates from 2020, attaches that agreement to the data. An `@context` maps every key to an IRI, a globally unique identifier for the concept. Two documents with different key names but the same IRIs describe the same things, and a processor can prove it. To any consumer that ignores `@context`, the document is still plain JSON. It is the format behind schema.org markup in web pages, ActivityPub in the fediverse, and W3C Verifiable Credentials.

I gave the series' buoy record a context built from real W3C vocabularies and measured what it costs. Two producers with different field names expanded to identical data. The same expansion silently dropped two of the record's eleven keys, and processing each record took 57 times as long as `json.loads`.

---

### The same record, both ways

A shortened observation with a context in front of it. `sosa` is the W3C vocabulary for sensor observations, and `fleet` is a vocabulary the buoy operator owns, for measurements no standard names:

```json
{
  "@context": {
    "sosa": "http://www.w3.org/ns/sosa/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "fleet": "https://harbour-buoys.example/terms#",
    "buoy_id": "sosa:madeBySensor",
    "recorded_at": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
    "wave_height_m": "fleet:significantWaveHeightMetres"
  },
  "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00+00:00",
  "wave_height_m": 3.5,
  "battery_v": 13.12
}
```

Below the context the record is unchanged, so a client that knows nothing about JSON-LD reads it as it always did. A JSON-LD processor **expands** it: each key is replaced by its IRI and each value is wrapped with its type.

```python
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
```

Two things happened. The timestamp is now a typed `xsd:dateTime`, something plain JSON can only express as a string and a convention. And `battery_v` is gone. The context had no term for it, so expansion dropped it without an error or a warning.

---

### What JSON-LD actually changes

The payoff is merging without a meeting. Here is the other agency's reading, with its own names and its own context:

```python
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
```

As JSON, the two documents share no keys. Expanded, they are identical. **Compaction** runs the other way: it rewrites their document using our context, so our existing code reads `buoy_id` and `wave_height_m` from data that arrived as `station` and `hs`. The mapping table still exists, but it is now data, published with the documents, instead of code in every consumer.

Expanded data is also RDF. The lab's full record canonicalises to 26 statements in N-Quads, the form Verifiable Credentials sign so that a signature survives key reordering and re-serialisation.

That is also where the "LD", linked data, comes in. Give an observation an `@id`, an IRI of its own, and any other document can refer to it, and a processor can join them the way a database joins rows on a key. The buoy, its maintenance log and the forecast built from its readings can live in three documents from three publishers and still form one graph.

Expansion has two silent rules, and the full record hit both. Every key without a term is dropped, which cost us `battery_v`. Every `null` is dropped, which cost us `notes`. Adding an `@vocab` catch-all keeps unmapped keys under a default namespace, and that recovered `battery_v`. Nothing brings back a `null`.

---

### The measurement

All 50,000 records as JSON Lines, then the first 1,000 through PyLD 3.3.0 with the context referenced by URL:

```
form                                 bytes     gzip -9     zstd -3
plain JSON                      20,790,508   1,872,391   2,344,851   raw   +0.0%  gzip   +0.0%
JSON-LD, context inline         57,140,508   2,280,875   2,537,368   raw +174.8%  gzip  +21.8%
JSON-LD, context by URL         24,340,508   1,915,982   2,396,991   raw  +17.1%  gzip   +2.3%

processing the first 1,000 records (context by URL)
  json.loads                             7.2 ms        7.2 us/record
  jsonld.expand                        408.7 ms      408.7 us/record
  context fetched 1,000 times for 1,000 documents
  jsonld.normalize (URDNA2015)          76.1 ms      761.4 us/record  (100 records)
```

A full context inside every record nearly triples the raw size, and even gzip leaves it 21.8% bigger. Referenced by URL, the context costs 71 bytes a record, 2.3% gzipped. That is why published contexts live at URLs.

A URL has its own cost. Expansion took 408.7 µs per record against 7.2 for `json.loads`, 57 times as long. The lab's loader counted what the default does with a remote context: 1,000 fetches for 1,000 documents. Canonicalising to RDF took 761 µs per record, over 100 times `json.loads`. The result was 2,307 bytes of N-Quads per record, 5.5 times the size of the JSON it came from.

The fix for the fetches is a loader that never goes to the network. It serves the contexts you have reviewed from memory and refuses everything else:

```python
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
```

The pinned context expands with no network access. A document pointing at a context nobody reviewed fails loudly instead of being fetched. That makes a context a dependency you control, not a URL someone else can change.

---

### Where JSON still wins

When one producer talks to one consumer. If both sides are your code, a shared schema does the job of a context at no cost. JSON-LD's value grows with the number of independent parties, and with two it rarely pays.

When the data is volume. At 57 times the processing cost of `json.loads`, JSON-LD processing belongs at the boundary where outside data enters your system. Expand or compact there, and keep plain JSON inside.

When a missing field should be an error. JSON parsers keep every key you send. JSON-LD expansion quietly deletes keys it cannot map and values that are `null`. A typo in the context loses data without a trace.

When you cannot depend on someone else's server. A remote context is a network request unless you cache it. If its host goes down, your parsing fails. If its host changes it, your data's meaning changes. Pin contexts locally, which is what a production document loader must do.

---

### Conclusion

Use JSON-LD when data crosses organisational lines and has to be merged, searched or signed by parties who never agreed a schema: structured data for search engines, federated social protocols, credentials, open-data catalogues. Two producers' readings became one graph without a line of mapping code in either consumer.

Use plain JSON inside your systems, and convert at the boundary. Consumers that ignore `@context` still work, so adding one never breaks a client.

The cost of JSON-LD is 57 times the processing of `json.loads`, a network dependency unless you pin your contexts, and silent deletion of every key you forgot to map. Map every key, or add `@vocab`, and check what survives expansion.

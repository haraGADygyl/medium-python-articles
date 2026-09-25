# Lab — 010, JSON vs. JSON-LD

A demonstration lab with measurements. `contexts.py` gives the series' buoy record a
JSON-LD context built on real vocabularies — W3C SOSA for observations, W3C Basic
Geo for positions, XML Schema datatypes — plus a vocabulary the fleet owns for
measurements no standard names. `battery_v` is deliberately left unmapped.

Python 3.12.3, `PyLD==3.3.0`, `zstandard==0.23.0`, Ryzen 5 3600. No network access
is needed or used: `CountingLoader` serves the context from memory and counts how
often PyLD asks for it.

```bash
pip install PyLD==3.3.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Keys dropped on expansion, two producers, one record as RDF | `python3 semantics.py` | `output-semantics.txt` |
| Size (inline vs referenced context), expand/normalize time, context fetches | `python3 measure.py` | `output-jsonld.txt` |
| The snippets printed in the article, including the pinned loader | `python3 snippets.py` | `output-snippets.txt` |

`measure.py` times PyLD on the first 1,000 records (expand) and the first 100
(URDNA2015 canonicalisation); PyLD is pure Python and the full 50,000 would add
nothing but minutes. `harbour-buoys.example` is a placeholder domain for the
fleet's own vocabulary and context URL.

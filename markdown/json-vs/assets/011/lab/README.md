# Lab — 011, JSON vs. JsonML

The series payload written as XML (one `<observation>` per record, the way a data
centre might publish it), then converted two ways: to JsonML with the ~30-line codec
in `jsonml.py` (standard-library `xml.etree` only), and to the usual key-value shape
with `xmltodict`. The snippets add a one-sentence note with mixed content, which is
where the two differ.

Python 3.12.3, `xmltodict==1.0.4`, `zstandard==0.23.0`, Ryzen 5 3600.

```bash
pip install xmltodict==1.0.4 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size of XML, JsonML, xmltodict JSON, plain payload; canonical round trips; speed | `python3 measure.py` | `output-jsonml.txt` |
| The snippets in the article: codec, mixed content, one-vs-many, lookups, string rival | `python3 snippets.py` | `output-snippets.txt` |

**Round trips are compared as canonical XML** (`ET.canonicalize`, C14N 2.0), so
cosmetic differences — `xmltodict.unparse` writes `<position ...></position>` where
ElementTree writes `<position ... />` — do not count as losses. Compared as raw
strings, `xmltodict` fails the payload round trip for that cosmetic reason alone.

Timings are best of five with the cyclic GC paused; they move by roughly ±10% between
runs, sizes do not.

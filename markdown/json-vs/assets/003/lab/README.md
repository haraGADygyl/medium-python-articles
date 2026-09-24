# Lab — 003, JSON vs. BSON

Python 3.12.3, `pymongo==4.18.2` (its `bson` module, C extension on),
`msgpack==1.1.0`, `cbor2==6.1.4`, `zstandard==0.23.0`, Ryzen 5 3600. The payload is
the series' shared dataset, generated in memory by `../../payload/make_payload.py`.

```bash
pip install pymongo==4.18.2 msgpack==1.1.0 cbor2==6.1.4 zstandard==0.23.0
```

Install `pymongo`, not the unrelated `bson` package on PyPI: both provide a module
called `bson`, and they conflict.

| Experiment | Command | Output |
| --- | --- | --- |
| Size, compressed size, encode/decode, one-field reads, 50,000 records | `python3 measure.py` | `output-bson.txt` |
| The snippets printed in the article (layout, field walker, types) | `python3 snippets.py` | `output-snippets.txt` |

**Framing.** Every format is measured one document per record, which is how MongoDB
stores and ships BSON: JSON as newline-terminated lines, BSON, MessagePack and CBOR
concatenated (each self-delimits). A BSON document must be a mapping, so the
50,000-record list cannot be encoded as one value without wrapping it.

**Timing.** Best of five, with the cyclic garbage collector disabled during each
timed run as `timeit` does; building 50,000 dicts otherwise triggers collections
that swamp the codec being measured. Timings move by roughly ±10% between runs;
sizes do not.

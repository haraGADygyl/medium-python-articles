# Lab — 013, JSON vs. CBOR

Python 3.12.3, `cbor2==6.1.4`, `msgpack==1.1.0`, `zstandard==0.23.0`, Ryzen 5 3600.
The payload is the series' shared dataset, generated in memory by
`../../payload/make_payload.py`.

```bash
pip install cbor2==6.1.4 msgpack==1.1.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size and speed, 50000 records, JSON / MessagePack / three CBOR modes | `python3 measure.py` | `output-cbor.txt` |
| Tagged values against their JSON workarounds | `python3 tags.py` | `output-tags.txt` |
| Key order, hashes, float narrowing, RFC 7049 vs RFC 8949 ordering | `python3 deterministic.py` | `output-deterministic.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

`measure.py` takes an optional record count (`python3 measure.py 5000`) and asserts
that every format round-trips the payload before it reports a number.

**What `canonical=True` means in cbor2 6.1.4.** It narrows floats to the shortest
exact width and sorts map keys *length-first*, which is RFC 7049's canonical order.
RFC 8949 section 4.2.1 sorts keys *bytewise* on their encoding instead. The two agree
for text keys, which is every key in the buoy payload, and disagree as soon as a map
mixes key types — `deterministic.py` prints both orders for `{"a": 2, 1000: 1}`.

**The three CBOR modes.** `CBOR` is `cbor2.dumps` with defaults (every float as a
double). `CBOR canonical` is `canonical=True`. `CBOR stringref` is
`string_referencing=True`, which wraps the output in tag 256 and replaces repeated
strings with tag 25 back-references; a decoder must implement both tags to read it.

Timings move by roughly ±10% between runs on this machine; the sizes do not move.

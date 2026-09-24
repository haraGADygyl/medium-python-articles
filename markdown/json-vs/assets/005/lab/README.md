# Lab — 005, JSON vs. UBJSON

Python 3.12.3, `py-ubjson==0.16.1` (C extension on), `msgpack==1.1.0`,
`cbor2==6.1.4`, `zstandard==0.23.0`, Ryzen 5 3600. The payload is the series'
shared dataset, generated in memory by `../../payload/make_payload.py` and encoded
as one array.

```bash
pip install py-ubjson==0.16.1 msgpack==1.1.0 cbor2==6.1.4 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size, compressed size, speed, round-trip check, float32 damage | `python3 measure.py` | `output-ubjson.txt` |
| The snippets printed in the article (layout, typed array, float32, edges) | `python3 snippets.py` | `output-snippets.txt` |

**The three UBJSON rows.** `UBJSON` is `ubjson.dumpb` with defaults.
`UBJSON, counts` is `container_count=True`, which writes `#` lengths on every
container. `UBJSON, float32` is `no_float32=False`: every float inside
single-precision *range* is written as a 32-bit float whether or not it fits
exactly, so the round-trip check fails. The library's own docstring warns of "the
loss of precision".

**Typed arrays.** `py-ubjson` reads optimized (`$`/`#`) containers of any type but
writes the typed form only for `bytes`. The typed float64 array in `snippets.py` is
assembled by hand to show the saving the format allows.

**Ecosystem note.** `py-ubjson` 0.16.1 was released on 2020-04-18 and is the latest
version on PyPI as of this lab.

Timing: best of five with the cyclic GC paused, as `timeit` does. Timings move by
roughly ±10% between runs; sizes do not.

# Lab — 000, JSON vs. MessagePack

Python 3.12.3, `msgpack==1.1.0`, `zstandard==0.23.0`, Ryzen 5 3600. The payload is
the series' shared dataset, generated in memory by `../../payload/make_payload.py`.

```bash
pip install msgpack==1.1.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size and speed, 50000 records | `python3 measure.py` | `output-msgpack.txt` |
| Size win by field type | `python3 shapes.py` | `output-shapes.txt` |
| Per-value encoding sizes, 64-bit id, timestamps | `python3 field_types.py` | `output-types.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

`measure.py` takes an optional record count (`python3 measure.py 5000`).

The file is named `field_types.py` rather than `types.py` on purpose: a module
called `types.py` shadows the standard library's `types` and breaks `import json`.

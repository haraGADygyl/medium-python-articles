# Lab — 000, JSON vs. JSON Lines (JSONL)

Python 3.12.3 standard-library `json`, plus `zstandard==0.23.0` for the zstd column,
Ryzen 5 3600, 12 threads. The payload is the series' shared dataset, generated in
memory by `../../payload/make_payload.py` and written to a temporary directory.

```bash
pip install zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size, first-record and full-read time, peak memory, append cost | `python3 measure.py` | `output-jsonl.txt` |
| Byte-range split over 1, 2, 4 and 6 worker processes | `python3 parallel.py` | `output-parallel.txt` |
| Torn writes, silent truncation, the U+2028 trap | `python3 failure_modes.py` | `output-failures.txt` |
| Key strings shared by one decode call vs one call per line | `python3 key_sharing.py` | `output-keys.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

**Peak memory** is read from `VmHWM` in `/proc/self/status` of a fresh interpreter,
minus its `VmRSS` before the read starts. `ru_maxrss` is deliberately not used: it
survives `exec`, so a child started from the (large) parent reports the parent's
peak. Linux only for that reason.

`snippets.py` writes `readings.json` and `readings.jsonl` into the current
directory; run it from a scratch directory.

Timings move by roughly ±10% between runs on this machine; sizes and counts do not.

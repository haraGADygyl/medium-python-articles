# Lab — 004, JSON vs. JSON5

A demonstration lab: one hand-written JSON5 config (`fleet.json5`) on seven parsers,
a one-value round trip through three JSON5 writers, and — because every JSON
document is valid JSON5 — the parsers' speed on the series' 20.8 MB payload.

Python 3.12.3 with `json5==0.15.0` and `pyjson5==2.0.1`; Node v24.20.0 with
`json5@2.2.3` and `jsonc-parser@3.3.1` (pinned in `package.json` /
`package-lock.json`); jq 1.7; Ryzen 5 3600.

```bash
pip install json5==0.15.0 pyjson5==2.0.1
npm ci
```

| Experiment | Command | Output |
| --- | --- | --- |
| The config on seven parsers, and whether the readers agree | `python3 interop.py` | `output-interop.txt` |
| Change `poll_interval_s` and write it back with each library | `python3 roundtrip.py` | `output-roundtrip.txt` |
| Parse time on the 50,000-record payload | `python3 speed.py` | `output-speed.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

`speed.py` runs the pure-Python `json5` parser once, not five times: a single parse
of the payload takes about five minutes. The npm `json5` parser also runs once.

There is no size measurement on purpose: JSON5's case is readability, and a byte
count would be a number in search of a point.

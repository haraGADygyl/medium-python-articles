# Lab — 006, JSON vs. YAML

A demonstration lab: one ten-line YAML config (`fleet.yaml`) on three parsers, the
parsers' speed on the series' 20.8 MB payload (every JSON document is YAML 1.2),
and three things a YAML document can do to its reader.

Python 3.12.3 with `PyYAML==6.0.3` (libyaml bindings present), `ruamel.yaml==0.19.1`
and `ruamel.yaml.clib==0.2.15`; Node v24.20.0 with `yaml@2.9.1` (pinned in
`package.json` / `package-lock.json`); Ryzen 5 3600.

```bash
pip install PyYAML==6.0.3 ruamel.yaml==0.19.1 ruamel.yaml.clib==0.2.15
npm ci
```

| Experiment | Command | Output |
| --- | --- | --- |
| The config on PyYAML (1.1), ruamel.yaml (1.2) and npm `yaml` (1.2) | `python3 traps.py` | `output-traps.txt` |
| Parse time on the 50,000-record payload | `python3 speed.py` | `output-speed.txt` |
| Alias expansion, duplicate keys, `!!python/object/apply` | `python3 safety.py` | `output-safety.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

**Install `ruamel.yaml.clib` explicitly.** ruamel.yaml 0.19 does not pull it in, and
without it `YAML(typ="safe", pure=False)` silently falls back to the pure-Python
parser — the first run of `speed.py` measured 101 s for "ruamel.yaml C" before this
was noticed. `speed.py` now prints which engine it used.

The YAML parsers run once each on the payload; a single pure-Python parse takes
over a minute. `safety.py`'s tag example calls `builtins.sum`, which is harmless;
the point is that `unsafe_load` calls whatever the document names.

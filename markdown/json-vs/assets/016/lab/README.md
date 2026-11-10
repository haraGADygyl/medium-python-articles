# Lab — 016, JSON vs. TOML

A measurement lab with three small demonstrations: a TOML config read by `tomllib`,
the nine values from the YAML article (006) written as TOML, one buoy record written
by three TOML writers, a comment round trip, and the series' 50,000-record payload
written and read as TOML.

Python 3.12.3 (its `tomllib` implements TOML 1.0.0), `tomli==2.5.0` (TOML 1.1.0,
installed as a mypyc-compiled wheel), `tomli_w==1.2.0`, `tomlkit==0.15.2`,
`rtoml==0.14.0`, `zstandard==0.23.0`; Ryzen 5 3600. The payload is the shared dataset
from `../../payload/make_payload.py`.

```bash
pip install tomli==2.5.0 tomli_w==1.2.0 tomlkit==0.15.2 rtoml==0.14.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| The config snippet printed in the article (reads `fleet.toml`) | `python3 snippets.py` | `output-snippets.txt` |
| `fleet.toml` converted to JSON, datetimes via `isoformat()` | `python3 fleet_json.py` | `output-fleet.json` |
| The YAML article's nine values on TOML 1.0 (`tomllib`) and 1.1 (`tomli`) | `python3 refusals.py` | `output-refusals.txt` |
| One record: what each writer does with `null`, and its layout | `python3 record.py` | `output-record.txt` |
| Edit one value: `tomllib` + `tomli_w` against `tomlkit` | `python3 roundtrip.py` | `output-roundtrip.txt` |
| Parse time on the 664-byte config itself | `python3 config_speed.py` | `output-config-speed.txt` |
| Size (raw, gzip -9, zstd -3) and read/write time on 50,000 records | `python3 measure.py` | `output-toml.txt` |

`convert.py` shapes the payload for TOML: `recorded_at` becomes a native offset
datetime and `notes` is dropped wherever it is `null`, because TOML has no null.
`measure.py` asserts that every writer's output reads back, through `tomllib` and
`convert.from_toml_doc`, to exactly the original records before it prints a number.
Restoring `notes = None` works only because the script knows the schema.

**rtoml's default for `None`.** `rtoml.dumps` writes `None` as the string `"null"`
unless called with `none_value=None`, and `rtoml.loads` leaves `"null"` as a string
unless called with `none_value="null"`. `record.py` shows the default; `measure.py`
passes `none_value=None` so all three writers produce the same data.

**Timing** is best of five with GC paused. Anything slower than 20 s runs once
(`tomlkit`, both ways). Shaping the rows for TOML and restoring them is timed
separately and not included in the TOML numbers. `measure.py 2000` runs the same
experiment on fewer records.

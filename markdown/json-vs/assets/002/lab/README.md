# Lab — 002, JSON vs. Infinity and NaN Values

A demonstration lab: one document with non-finite floats, handed to five JSON
implementations, then one `NaN` planted in the series payload.

Python 3.12.3 (standard-library `json`), Node v24.20.0, jq 1.7, PHP 8.5.10,
PostgreSQL 18.0 in Docker. The payload is the series' shared dataset from
`../../payload/make_payload.py`, with record 31,337's `wave_height_m` set to `NaN`.

```bash
./run.sh        # starts a throwaway PostgreSQL on 127.0.0.1:55002, runs all three, removes it
```

| Experiment | Command | Output |
| --- | --- | --- |
| Five readers and five writers on NaN/Infinity, and `1e400` | `python3 matrix.py` | `output-matrix.txt` |
| One NaN in 50,000 records, per consumer | `python3 pipeline.py` | `output-pipeline.txt` |
| The snippets printed in the article | `python3 snippets.py` | `output-snippets.txt` |

`runtimes.py` shells out to `node`, `jq`, `php` and `docker exec <container> psql`;
all four must be on `PATH`. The container name defaults to `json-vs-lab-002` and can
be changed with `LAB_PG_CONTAINER`.

**jq version matters.** jq 1.7 accepts `NaN` and `Infinity` literals, keeps `NaN`
internally (`isnan` is true) and prints it as `null`; it prints `Infinity` as the
largest finite double, and preserves the literal `1E+400` until arithmetic touches it.
jq 1.6 and earlier behave differently.

# Lab — 017, JSON vs. Parquet

A measurement lab: size, per-column cost and read/write time for the series' 50,000
buoy records as JSON and as Parquet, then one question asked of JSON, JSON Lines and
Parquet with the bytes actually read counted, and a writer killed before it finished.

Python 3.12.3, `pyarrow==26.0.1` (it writes `parquet-cpp-arrow version 26.0.1`),
`duckdb==2.0.0`, `zstandard==0.23.0`; Ryzen 5 3600, local NVMe, files in the page cache.
The payload is the shared dataset from `../../payload/make_payload.py`; `convert.py`
turns it into an Arrow table with an explicit schema.

```bash
pip install pyarrow==26.0.1 duckdb==2.0.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size (raw, gzip -9, zstd -3, four Parquet codecs), bytes per column, delta encoding, row-group sweep, one record, timing | `python3 measure.py` | `output-parquet.txt` |
| One question three ways: bytes read and time, row-group skipping on a time-ordered and a buoy-sorted file, the same SQL in DuckDB over JSON and Parquet (writes the four data files) | `python3 query.py` | `output-query.txt` |
| The snippet printed in the article (reads `buoy.jsonl`, run after `query.py`) | `python3 snippets.py` | `output-snippets.txt` |
| The pushdown snippet printed in the article (reads `buoy.parquet`) | `python3 pushdown.py` | `output-pushdown.txt` |
| A writer stopped before `close()`: JSON Lines against Parquet | `python3 append.py` | `output-append.txt` |

`measure.py` takes an optional record count (`python3 measure.py 5000`) and asserts that
every codec round-trips the payload, through `convert.from_table`, to exactly the
original records before it reports a number.

**Codec levels.** Parquet's `gzip` runs at level 9 to match the `gzip -9` it is compared
with. `zstd` keeps pyarrow's default, level 1; `snappy` is pyarrow's default codec.
Every codec compresses one page at a time, inside one column chunk.

**Row groups.** pyarrow puts up to 1,048,576 rows in a group, so `measure.py`'s
default files hold one group. `query.py` writes 5,000-row groups on purpose, to give
the footer statistics something to skip; the sweep in `measure.py` shows what smaller
groups cost in size.

**Bytes read** come from a counting file object handed to `pq.read_table`, so they
include the footer and anything pyarrow reads ahead, not only the pages it decodes.

**Timing** is best of five, GC paused. The JSON side of each query parses the whole
file; the Parquet side reads the projected columns into Arrow and filters there. The
DuckDB comparison runs with `SET threads = 1`. Sizes and bytes read are identical from
run to run. Times are not: across two runs the query times moved by up to ~20% and the
paths that build Python dicts by up to ~25% (Parquet's dicts -> bytes was 229.7 ms in
the saved run and 178.7 ms in the next), so the article quotes those as ranges or
ratios, never to the decimal.

# Lab — 015, JSON vs. Apache Avro

Python 3.12.3, `fastavro==1.13.1`, `backports.zstd==1.8.0` (fastavro's `zstandard`
codec), `cramjam==2.13.0` (its `snappy` codec), `msgpack==1.1.0`,
`zstandard==0.23.0`, Ryzen 5 3600. The payload is the series' shared dataset from
`../../payload/make_payload.py`; `buoy.avsc` is the schema for it.

```bash
pip install fastavro==1.13.1 backports.zstd==1.8.0 cramjam==2.13.0 \
            msgpack==1.1.0 zstandard==0.23.0
```

| Experiment | Command | Output |
| --- | --- | --- |
| Size (raw, gzip, zstd, four Avro codecs), block size sweep, single-record size, timing | `python3 measure.py` | `output-avro.txt` |
| Schema resolution: added field, missing default, alias, silent rename, wrong writer's schema, registry framing | `python3 evolution.py` | `output-evolution.txt` |
| The snippet printed in the article (writes `buoy.avro`) | `python3 snippets.py` | `output-snippets.txt` |
| The reordered-schema snippet printed in the article | `python3 reorder.py` | `output-reorder.txt` |

`measure.py` takes an optional record count (`python3 measure.py 5000`) and asserts
that every codec round-trips the payload before it reports a number.

**Codec levels.** `deflate` runs at level 9 to match the `gzip -9` it is compared
with; `zstandard` keeps fastavro's default, level 3, to match `zstd -3`. Each codec
compresses one block at a time, and fastavro starts a new block every ~16 KB
(`sync_interval=16000`) unless told otherwise — the block size sweep shows what that
default costs.

**Sizes move by a few bytes between runs.** Every container file starts with a random
16-byte sync marker that is repeated after each block, so the gzipped and
codec-compressed sizes differ by a handful of bytes from run to run. Raw sizes do not.

**Timing** is dicts to bytes and bytes to dicts on both sides, best of five, GC paused.
The Avro side includes turning the payload's ISO 8601 strings into `datetime` objects
for `timestamp-millis` and back (the encode cost is printed separately). Two runs
agreed within ~5%.

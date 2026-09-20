# The shared payload — harbour buoy observations

Every article in the `JSON vs.` series measures the same dataset, so a number in
one article is comparable with a number in another.

```bash
python3 make_payload.py                 # 50000 records -> buoy.json, buoy.jsonl
python3 make_payload.py --records 1 --pretty   # one record, for the article body
```

The generator is deterministic (`SEED = 20260920`), so the byte counts below
reproduce on any machine running Python 3.12+.

| File | Bytes | gzip -9 |
| --- | --- | --- |
| `buoy.json` (50000 records, compact) | 20,790,509 | 1,872,392 (9.0%) |
| `buoy.jsonl` (50000 records) | 20,790,508 | — |

The generated files are gitignored; regenerate them rather than committing 20 MB.

## Why this shape

One record exercises everything the series argues about:

- **`observation_id` starts at 9007199254740993**, one past `2**53`, so the 64-bit
  integer article has a real casualty and every binary format can be checked for
  whether it survives the round trip.
- **`recorded_at` is an ISO 8601 string**, because JSON has no date type — the
  point CBOR, TOML, Avro and Protobuf each answer differently.
- **`position`** is a nested object, **`sensors`** a variable-length array of
  objects: the structures columnar and schema-first formats handle least like JSON.
- **`notes` is usually `null`**, giving nullable-column behaviour to measure.
- **`qc_passed`** is a boolean, the type with the largest relative size win in the
  binary formats.
- **Keys repeat on every record**, which is why JSON gzips to 9% here and why
  "smaller than JSON" needs the compressed number beside it.

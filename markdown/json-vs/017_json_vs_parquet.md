# JSON vs. Parquet

#### Parquet stores each field as its own column with min/max statistics, so one question read 177 KB instead of parsing 21 MB, but the file is unreadable until its writer finishes

**By Tihomir Manushev**

*Nov 21, 2026 · 8 min read*

---

JSON stores a dataset the way a program produces it: one complete record, then the next. That is the right shape for an API response, a message on a queue, or a log line appended as it happens. It is the wrong shape for the question an analyst asks of a year of buoy data: what was the average wave height at NE-07? The answer needs two fields out of fourteen, and a JSON reader has to parse all fourteen in all 50,000 records to find them.

Every binary format in this series so far kept the record shape and made each record smaller. Parquet changes the shape instead: it stores all the wave heights together, all the buoy ids together, and writes a summary of each block of values at the end of the file.

I measured it with `pyarrow` 26.0.1. The question read 176,842 bytes from Parquet and took about 2 ms; JSON parsed 20.8 MB and took 312 ms. Parquet also stayed smaller than JSON after gzip, which none of the row formats measured earlier in this series managed.

---

### The same document, both ways

The series' first record, as the generator prints it:

```json
{
  "observation_id": 9007199254740993,
  "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00+00:00",
  "position": {"lat": 57.21621, "lon": -2.37579},
  "wave_height_m": 3.5,
  "water_temp_c": 12.0,
  "wind_gust_ms": 10.7,
  "battery_v": 13.12,
  "qc_passed": true,
  "notes": null,
  "sensors": [
    {"tag": "accelerometer", "status": "offline", "samples": 1933},
    {"tag": "thermistor", "status": "degraded", "samples": 1866},
    {"tag": "anemometer", "status": "degraded", "samples": 318}
  ]
}
```

One record is a poor way to show Parquet, because the format only makes sense across many rows. So this snippet converts the whole of `buoy.jsonl` and then reads back the file's footer:

```python
import json
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

reading = pa.struct([("lat", pa.float64()), ("lon", pa.float64())])
sensor = pa.struct([("tag", pa.string()), ("status", pa.string()),
                    ("samples", pa.int32())])
schema = pa.schema([
    ("observation_id", pa.int64()),
    ("buoy_id", pa.string()),
    ("recorded_at", pa.timestamp("ms", tz="UTC")),
    ("position", reading),
    ("wave_height_m", pa.float64()),
    ("water_temp_c", pa.float64()),
    ("wind_gust_ms", pa.float64()),
    ("battery_v", pa.float64()),
    ("qc_passed", pa.bool_()),
    ("notes", pa.string()),
    ("sensors", pa.list_(sensor)),
])

with open("buoy.jsonl") as lines:
    records = [json.loads(line) for line in lines]
for record in records:
    record["recorded_at"] = datetime.fromisoformat(record["recorded_at"])

table = pa.Table.from_pylist(records, schema=schema)
pq.write_table(table, "buoy.parquet", row_group_size=5_000)

footer = pq.ParquetFile("buoy.parquet").metadata

print(footer.num_rows, footer.num_row_groups, footer.num_columns)  # 50000 10 14

print([footer.schema.column(i).path for i in range(footer.num_columns)][-3:])
# ['sensors.list.element.tag', 'sensors.list.element.status', 'sensors.list.element.samples']

first_group = footer.row_group(0)
stamps = first_group.column(2).statistics

print(stamps.min, stamps.max)
# 2026-02-11 00:00:00+00:00 2026-03-17 17:10:00+00:00

waves, notes = first_group.column(5).statistics, first_group.column(10).statistics

print(waves.min, waves.max, waves.null_count, notes.null_count)  # 0.2 7.49 0 4748
```

The schema is required. JSON lets each record decide its own types, but a Parquet column has one type for every row, so the ISO string becomes a real `timestamp` and `samples` becomes a 32-bit integer.

The footer shows how Parquet lays the data out. Eleven top-level fields became **fourteen leaf columns**, because nesting is flattened. `position` turns into two columns, `position.lat` and `position.lon`. Each field inside `sensors` becomes its own column of values, plus small repetition and definition levels that record where each list starts and which values are null.

The 50,000 rows are split into ten **row groups** of 5,000. Inside each group, every leaf column is stored as one **column chunk**, and the footer records each chunk's minimum, maximum and null count. Group 0 covers 11 February to 17 March. Its wave heights run from 0.2 to 7.49 metres, and 4,748 of its 5,000 `notes` are null. A reader gets all of that without reading a single data page.

---

### What Parquet actually changes

**Similar values sit next to each other.** A JSON file alternates an id, a string, a timestamp, two coordinates, four doubles and a list, over and over. A Parquet column chunk holds 50,000 values of one type, and that lets the writer pick an encoding per column. Here is where the bytes went in the default single-group file:

```
  column                             bytes  encodings
  observation_id                   298,098  PLAIN, RLE_DICTIONARY
  buoy_id                           19,078  PLAIN, RLE_DICTIONARY
  recorded_at                      398,047  PLAIN, RLE_DICTIONARY
  position.lat                     347,873  PLAIN, RLE_DICTIONARY
  position.lon                     386,120  PLAIN, RLE_DICTIONARY
  wave_height_m                     65,655  PLAIN, RLE_DICTIONARY
  ...
  qc_passed                          5,273  PLAIN
  notes                              5,108  PLAIN, RLE_DICTIONARY
  ...
  sensors[].samples                233,706  PLAIN, RLE_DICTIONARY
```

`buoy_id` has six distinct values, so **dictionary encoding** stores them once and then a few bits per row: 19 KB for 50,000 strings. Wave heights have two decimals between 0.2 and 7.5, which is about 730 distinct doubles, so they fit in a dictionary too. The 5-decimal coordinates are nearly all unique and stay big. `notes` is almost always null, and nulls cost only definition levels, so the column is 5 KB.

pyarrow tries a dictionary on every column except the boolean, and that choice is wrong for the two sequential ones. Switching `observation_id` and `recorded_at` to `DELTA_BINARY_PACKED`, which stores the gap between neighbouring values, took them from 298,098 and 398,047 bytes to **336 and 356**. A row format cannot do this, because neighbouring ids are never next to each other in its bytes.

**Reading the footer lets a reader skip work.** Asking for two columns is **projection pushdown**: the reader seeks to those two column chunks and ignores the other twelve. Adding a filter is **predicate pushdown**: any row group whose min/max range cannot match is skipped entirely:

```python
from datetime import datetime, timezone

import pyarrow.compute as pc
import pyarrow.parquet as pq

week_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
week_end = datetime(2026, 6, 8, tzinfo=timezone.utc)
one_buoy_one_week = [
    ("buoy_id", "=", "NE-07"),
    ("recorded_at", ">=", week_start),
    ("recorded_at", "<", week_end),
]

waves = pq.read_table("buoy.parquet", columns=["wave_height_m"],
                      filters=one_buoy_one_week)

print(waves.num_rows, round(pc.mean(waves["wave_height_m"]).as_py(), 4))  # 167 4.0784

footer = pq.ParquetFile("buoy.parquet").metadata
overlapping = [
    group for group in range(footer.num_row_groups)
    if footer.row_group(group).column(2).statistics.max >= week_start
    and footer.row_group(group).column(2).statistics.min < week_end
]

print(overlapping)  # [3]
```

Only row group 3 overlaps the first week of June, so nine of the ten are never decoded. The list comprehension does by hand what `read_table` does internally.

---

### The measurement

50,000 records, best of five. The Parquet `gzip` codec ran at level 9, to match `gzip -9`:

```
format                           bytes     gzip -9     zstd -3
JSON                        20,790,509   1,872,392   2,344,331
Parquet, codec none          2,343,604   1,443,988   1,343,345
Parquet, codec snappy        2,028,783
Parquet, codec gzip          1,441,664
Parquet, codec zstd          1,613,717
  Parquet (none) vs JSON: raw 88.7% smaller, gzip 22.9% smaller, zstd 42.7% smaller
  Parquet codec snappy vs gzipped JSON: 8.4% bigger
  Parquet codec gzip vs gzipped JSON: 23.0% smaller
```

Without compression, Parquet is 2.3 MB against JSON's 20.8, and less than half the 6.0 MB Avro file from the last article. After gzip it is still 22.9% smaller. MessagePack, Avro and Protobuf all lost after compression, because gzip removes the repeated keys they had removed already. Parquet's advantage comes from dictionary encoding and from grouping values of the same kind, and gzip cannot recreate either from a row format. With delta-encoded ids and timestamps, the snappy file shrank to 1,333,283 bytes, 28.8% smaller than gzipped JSON. pyarrow's default codec, snappy, is the exception: it is 8.4% bigger than gzipped JSON, because it trades ratio for speed.

Then the question, asked three ways against files with 5,000-row groups, with every byte read counted:

```
Q1: mean wave height at NE-07, the whole year
  JSON, json.loads                       312.0 ms  read  20,790,509  -> 3.8560
  JSON Lines, line by line               316.0 ms  read  20,790,508  -> 3.8560
  Parquet, 2 columns + filter              2.2 ms  read     176,842  -> 3.8560

Q1 again: statistics only skip what the sort order clusters
  buoy.parquet           group 0 buoy_id HB-214..SW-42    groups kept 10 of 10  read   176,842
  buoy-sorted.parquet    group 0 buoy_id HB-214..HB-214   groups kept  3 of 10  read    93,163

the same SQL, the same engine (DuckDB), two files
  read_json('buoy.json')         164.1 ms  -> 3.856
  'buoy.parquet'                   1.5 ms  -> 3.856
```

Same answer, 118 times fewer bytes, more than 100 times faster. DuckDB, given the same SQL and one thread, was about 100 times faster on Parquet than on JSON, so the gap comes from the format and not from Python's `json` module.

The buoy filter skipped nothing at first. The observations are stored in time order, so every row group contains all six buoys and spans `HB-214` to `SW-42`. Sorting the file by buoy before writing let the statistics rule out seven groups of ten and nearly halved the bytes read. Statistics only help when the sort order clusters the column you filter on. The one-week query read 114,907 bytes because the file was already in time order.

The pushdown has a cost in file size. Ten row groups made the file 2,320,298 bytes instead of 2,028,783, and fifty made it 2,814,027 with an 83 KB footer. Every group restarts its dictionaries and carries its own statistics.

---

### Where JSON still wins

For one record at a time. A Parquet file holding the single record above is **4,450 bytes**; the JSON is 427. The schema, the footer and fourteen nearly empty column chunks are paid for on every file, so a message queue of one-row Parquet files is ten times worse than JSON.

For data that is still being written. A JSON Lines writer that dies loses at most the line it was writing: with the last 200 bytes cut off, 14,999 of 15,000 records read back. A Parquet writer that has flushed three row groups but not called `close()` leaves 689,751 bytes and none of them can be read:

```
ArrowInvalid: Could not open Parquet input source 'buoy-live.parquet': Parquet magic bytes not found in footer.
```

The footer comes last, and without it there is no map to the data. Parquet files are written once and never appended to, which is why streaming pipelines land JSON Lines first and compact them into Parquet later.

For code that wants Python dicts. Reading the file into an Arrow table took 15 to 17 ms. Turning that table back into 50,000 dicts took 405 to 456 ms in total, 1.5 to 1.7 times slower than `json.loads`. Parquet is fast when the work stays in columns.

And for anything a person or `curl` reads, since a Parquet file is binary and needs a library to open.

---

### Conclusion

Use Parquet for data that is written once and then queried many times: a day of events, a year of sensor readings, a table exported for analysts. Parquet stores each column with its own encoding and min/max statistics, so a reader can fetch two columns out of fourteen and skip row groups that cannot match. On this payload, Parquet was the first format in the series that stayed smaller than JSON after gzip.

Use JSON for single records, for anything still being appended to, and for anything a person has to read.

The cost of Parquet is that it works only in batches. A file is unreadable until it is closed and cannot be appended to, a one-row file is ten times the size of the JSON, and pushdown only pays off if someone chose the sort order and row-group size with the queries in mind.

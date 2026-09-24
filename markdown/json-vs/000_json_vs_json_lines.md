# JSON vs. JSON Lines (JSONL)

#### The same records, one byte apart — and that byte decides whether you can stream, append and split the file

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

Put fifty thousand records in a JSON file and you have written one value: an array. To read record one you parse all fifty thousand, to add record fifty thousand and one you rewrite the file, and if the writer dies halfway through, nothing in the file is readable.

JSON Lines makes one change. Instead of a single array, the file holds one JSON value per line, separated by `\n`. No brackets, no commas between records. On the series' 50,000 harbour buoy observations, that change makes the file exactly one byte smaller — and moves the first record from 318 ms away to 0.04 ms, cuts peak memory from 121.7 MB to 0.2 MB, and turns a 20.8 MB append into a 365-byte one.

It also costs something JSON never had to worry about: a JSON Lines file cannot tell you when it is incomplete. Both halves are below, measured.

---

### The same records, both ways

One observation from the series' generator:

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

A batch of three, written both ways:

```python
import json
from collections.abc import Iterator
from pathlib import Path

reading = {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5,
    "water_temp_c": 12.0,
    "wind_gust_ms": 10.7,
    "battery_v": 13.12,
    "qc_passed": True,
    "notes": None,
    "sensors": [
        {"tag": "accelerometer", "status": "offline", "samples": 1933},
        {"tag": "thermistor", "status": "degraded", "samples": 1866},
        {"tag": "anemometer", "status": "degraded", "samples": 318},
    ],
}
batch = [reading, {**reading, "qc_passed": False}, reading]

as_json = json.dumps(batch, separators=(",", ":"))
as_jsonl = "".join(json.dumps(row, separators=(",", ":")) + "\n"
                   for row in batch)
Path("readings.json").write_text(as_json)
Path("readings.jsonl").write_text(as_jsonl)

print(len(as_json), len(as_jsonl))  # 1286 1285
print(as_json[:2], as_json[-2:])    # [{ }]
print(as_jsonl.count("\n"))         # 3

try:
    json.loads(as_jsonl)
except json.JSONDecodeError as exc:
    print(f"JSONDecodeError: {exc}")
# JSONDecodeError: Extra data: line 2 column 1 (char 428)
```

The byte arithmetic is the whole format. An array of *n* records costs two brackets and *n − 1* commas; JSON Lines costs *n* newlines. JSON Lines is always exactly one byte smaller, at three records and at fifty thousand.

The last line is the part people trip over: a JSON Lines file is **not a JSON document**. `json.loads` reads the first record, finds more data after it and refuses. Each line is valid JSON; the file is not. That is why it gets its own extension, `.jsonl`, and its own media type in practice, `application/x-ndjson` — NDJSON being the same idea under a second name.

---

### What JSON Lines actually changes

The newline is a **record boundary you can find without parsing**. JSON escapes every newline inside a string as `\n`, so a raw newline byte in a compact encoding can only mean "the record ended". Everything JSON Lines is good for follows from that.

You can stream. A reader holds one line at a time and never builds the list:

```python
def failed_qc(path: Path) -> Iterator[dict]:
    """Yield the readings that failed QC, holding one line at a time."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if not row["qc_passed"]:
                    yield row


print(sum(1 for _ in failed_qc(Path("readings.jsonl"))))  # 1
```

You can append. Adding a record is one write at the end of the file; adding one to a JSON array means parsing it, appending, and writing everything back:

```python
late_reading = {**reading, "observation_id": 9007199254740996}

with open("readings.jsonl", "a", encoding="utf-8") as handle:
    handle.write(json.dumps(late_reading, separators=(",", ":")) + "\n")

rows = json.loads(Path("readings.json").read_text())
rows.append(late_reading)
Path("readings.json").write_text(json.dumps(rows, separators=(",", ":")))

print(sum(1 for _ in open("readings.jsonl")), len(rows))  # 4 4
```

You can split. Seek to any byte offset, skip to the next newline, and you are at the start of a record — which is how Spark, BigQuery's newline-delimited JSON loads and Elasticsearch's bulk API divide one file among many workers. And you can survive a crash, because a torn write damages one line rather than the whole file.

---

### The measurement

All 50,000 records, best of five, Python 3.12. Each reader counts the 3,947 observations that failed QC, in a fresh process so its peak memory is its own:

```
file               bytes     gzip -9     zstd -3
buoy.json     20,790,509   1,872,392   2,344,331
buoy.jsonl    20,790,508   1,872,391   2,344,851

reader                       first record ms  all records ms  peak extra MB
json.load, whole array                317.95           323.3          121.7
jsonl, list of all lines              472.50           479.8          145.1
jsonl, one line at a time               0.04           306.1            0.2

append one record to the 50000-record file
  buoy.json      596.132 ms    20,790,874 bytes written
  buoy.jsonl       0.102 ms           365 bytes written
```

Size is a tie, raw and compressed, so size is not the reason to switch.

The reader rows are the reason. Streaming JSON Lines has its first record in 0.04 ms and finishes in 306.1 ms with 0.2 MB of extra memory. `json.load` needs 121.7 MB and returns nothing until the whole file is parsed.

The middle row is the trap. Read JSON Lines into a list and it is *worse* than `json.load`: 472.5 ms and 145.1 MB. Fifty thousand `json.loads` calls cost more than one, and the decoder shares key strings only within a single call. The lab counted 11 distinct top-level key objects after one `json.load` and 550,000 after one call per line. JSON Lines pays off when you stream it, not when you rebuild the array.

Appending is 596 ms and a 20.8 MB rewrite against 0.1 ms and 365 bytes, and the gap grows with the file.

Parallel reads split cleanly on newlines. Six workers over byte ranges counted the same 3,947 failures in 103.1 ms against 358.3 ms for one, 3.5× including process start-up. A JSON array has no such boundary: finding where record 25,000 begins means parsing the 24,999 before it.

Then the crash. The lab cut both files halfway through record 30,000:

```
writer killed halfway through record 30,000 of 50,000
  buoy.json   JSONDecodeError: Unterminated string starting at; 0 records usable
  buoy.jsonl  29,999 records usable; 1 bad line: line 30000: Unterminated string ...

writer killed right after a newline, 29,999 records in
  buoy.json   JSONDecodeError: Expecting ',' delimiter
  buoy.jsonl  29,999 records usable, 0 errors - nothing says 20,001 are missing
```

The first case is the one JSON Lines advertises: lose one record, keep 29,999. The second is the one it does not. Cut on a line boundary, and the truncated file is a perfectly valid JSON Lines file. JSON fails loudly on both.

---

### Where JSON still wins

A JSON document knows where it ends. That closing `]` is a checksum you get for free: a file that parses is a file that was finished. JSON Lines has no equivalent, so anything that must be complete needs a record count, a trailer line or a `.done` marker next to it.

JSON has a top level. An API response with a cursor, a total and a list of items is one object; in JSON Lines that metadata has nowhere to live except a convention for "the first line is special".

JSON can be pretty-printed. A JSON Lines record must stay on one line, so `indent=2` silently produces a broken file, and a 400-byte record is not pleasant to read in a diff.

And the newline rule is stricter than it looks. `ensure_ascii=False` writes U+2028 LINE SEPARATOR as a raw character, which `str.splitlines()` treats as a line break:

```python
note = json.dumps({"notes": "hull scraped mooring checked"},
                  ensure_ascii=False)
print(len(note.split("\n")), len(note.splitlines()))  # 1 2
```

Iterating over a file splits on `\n` only and is safe; `splitlines()` cuts that record in two. Read JSON Lines by iterating the file or splitting on `"\n"`, never with `splitlines()`.

---

### Conclusion

Use JSON Lines for records that arrive over time or get processed one at a time: logs, event exports, telemetry, batch jobs, dataset files, anything you append to or hand to several workers. On this payload that meant a first record in 0.04 ms instead of 318, 0.2 MB of memory instead of 121.7 and a 365-byte append instead of a 20.8 MB rewrite, at the same size on disk.

Use JSON for a single document: an API response, a config file, anything with metadata above the records or a reader that will load it whole anyway. Reading a JSONL file into a list is slower and heavier than `json.load`.

The cost is completeness. A JSON Lines file truncated on a line boundary is still valid. If losing the tail matters, write down how many records there should be.

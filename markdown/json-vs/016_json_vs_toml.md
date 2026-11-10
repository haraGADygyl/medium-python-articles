# JSON vs. TOML

#### TOML refuses the values YAML guesses and reads dates as dates, but it has no null, and Python's built-in parser read the buoy payload 20 times slower than JSON

**By Tihomir Manushev**

*Nov 11, 2026 · 8 min read*

---

JSON works for a config file until a person has to edit it. It has no comments, so the reason a threshold is 6.5 ends up in a commit message. It has no date type, so `"2026-02-11"` is a string every program parses for itself. YAML fixed both, and the YAML article in this series showed what that cost: PyYAML read Norway's country code as `False`.

TOML sits between the two. As in JSON, a value's type comes from how it is written, so a string needs quotes and a bare `NO` is an error rather than a boolean. It adds comments, four date and time types, and tables that keep a flat config flat. Python has read it from the standard library since 3.11, and `pyproject.toml` and Rust's `Cargo.toml` are both TOML.

I gave TOML the YAML article's nine values and the series' 50,000 buoy records. Python's `tomllib` refused seven of the nine outright, and the one value it changed without a word is one JSON changes too. The records went less well. TOML has no null, so 47,485 `notes` fields had to be dropped, and one popular writer saved them as the string `"null"`.

---

### The same config, both ways

The buoy fleet's export settings, as `fleet.toml`:

```toml
# Export settings for the north-east harbour buoys.
fleet = "north-east"
share_with = ["GB", "NO", "DK"]  # met offices that receive the feed
upload_window = 22:30:00         # UTC, after the evening poll
firmware = "1.10"
archive_mode = 0o640
compress = true
station_code = "07031"
commissioned = 2026-02-11
# No contact yet. TOML has no null, so the key is left out.

[thresholds]
wave_height_m = 6.5   # page the duty officer above this
battery_v = 11.8

[[recipient]]
office = "NO"
endpoint = "sftp://feeds.example.no/buoys"
since = 2026-03-01T06:00:00Z

[[recipient]]
office = "DK"
endpoint = "sftp://feeds.example.dk/buoys"
since = 2026-04-15T08:00:00+02:00
```

Strings are quoted, as in JSON, and everything else carries its type in its form. `22:30:00` is a **local time**, `2026-02-11` a **local date**, and `since` an **offset datetime**. The file mode needs an explicit `0o` prefix, because TOML forbids leading zeros instead of guessing at octal. `[thresholds]` opens a table. Each `[[recipient]]` adds one more table to an array called `recipient`, so the two blocks become a list of two objects.

Reading it takes one call:

```python
import json
import tomllib
from datetime import datetime

with open("fleet.toml", "rb") as handle:
    settings = tomllib.load(handle)

print(settings["share_with"])     # ['GB', 'NO', 'DK']
print(settings["upload_window"])  # 22:30:00
print(settings["archive_mode"])   # 416
print(type(settings["commissioned"]).__name__)  # date
print("contact" in settings)      # False

danish = settings["recipient"][1]

print(danish["since"])            # 2026-04-15 08:00:00+02:00

try:
    json.dumps(settings)
except TypeError as error:
    print(error)  # Object of type time is not JSON serializable

print(json.dumps(danish["since"], default=str))  # "2026-04-15 08:00:00+02:00"

print(json.dumps(danish["since"], default=datetime.isoformat))
# "2026-04-15T08:00:00+02:00"
```

`tomllib.load` wants the file opened in binary mode. Open it in text mode and it raises `TypeError: File must be opened in binary mode`. What comes back is real Python objects: a `time`, an `int`, a `date` and a timezone-aware `datetime`. That is TOML's point, and where it collides with JSON. `json.dumps` refuses the whole dictionary. With `default=str` you get a space where ISO 8601 has a `T`, so pass `isoformat` to get the form the dates started in.

Converted that way, the same settings as JSON:

```json
{
  "fleet": "north-east",
  "share_with": ["GB", "NO", "DK"],
  "upload_window": "22:30:00",
  "firmware": "1.10",
  "archive_mode": 416,
  "compress": true,
  "station_code": "07031",
  "commissioned": "2026-02-11",
  "thresholds": {"wave_height_m": 6.5, "battery_v": 11.8},
  "recipient": [
    {"office": "NO", "endpoint": "sftp://feeds.example.no/buoys",
     "since": "2026-03-01T06:00:00+00:00"},
    {"office": "DK", "endpoint": "sftp://feeds.example.dk/buoys",
     "since": "2026-04-15T08:00:00+02:00"}
  ]
}
```

Every value survives. Three things do not: the five comments, the octal spelling of the file mode, and the knowledge that `since` was a datetime and not just text.

---

### What TOML actually changes

**Types come from syntax, not from a guess.** Here are the nine values that split the YAML parsers, written with TOML's `=`. Each one is parsed as its own document, because a TOML parser stops at the first error:

```
written                     tomllib, Python 3.12 (TOML 1.0)         tomli 2.5.0 (TOML 1.1)
fleet = north-east          refused: Invalid value                  refused: Invalid value
share_with = [GB, NO, DK]   refused: Invalid value                  refused: Invalid value
upload_window = 22:30       refused: Expected newline or end ...    datetime.time(22, 30)
firmware = 1.10             1.1                                     1.1
archive_mode = 0640         refused: Expected newline or end ...    refused: Expected newline or end ...
compress = on               refused: Invalid value                  refused: Invalid value
station_code = 07031        refused: Expected newline or end ...    refused: Expected newline or end ...
commissioned = 2026-02-11   datetime.date(2026, 2, 11)              datetime.date(2026, 2, 11)
contact = null              refused: Invalid value                  refused: Invalid value
```

Where YAML guessed, TOML stops with an error. The only value changed silently is `1.10` becoming `1.1`, and JSON does exactly the same, because both read it as a float. The one disagreement is a version gap. TOML 1.1.0, released in December 2025, made seconds optional, so `tomli` 2.5.0 reads `22:30` and Python 3.12's `tomllib` rejects it. `tomllib` moves to TOML 1.1 in Python 3.15. Until every reader of a file has upgraded, write the seconds.

**There is no null.** The first buoy record has `"notes": null`, and the three Python writers handled it three ways:

```
tomli_w  TypeError: Object of type 'NoneType' is not TOML serializable
tomlkit  ConvertError: Unable to convert an object of <class 'NoneType'> to a TOML item
rtoml    writes 'notes = "null"', read back as 'null'
```

Two writers refuse, which is the honest answer. rtoml, by default, writes the four-character string `"null"`, and even rtoml reads it back as a string unless `loads` is given `none_value="null"`. With that option, a note that really says "null" would come back as `None`. The only clean conversion is to drop the key and put it back from a schema on the way in. Missing and null become one state, and the reader has to know which keys were dropped.

**Nesting is written as headers.** Here is the same record after dropping `notes` and making `recorded_at` a datetime, written by `tomlkit`:

```toml
[[observation]]
observation_id = 9007199254740993
buoy_id = "NE-08"
recorded_at = 2026-02-11T00:00:00Z
wave_height_m = 3.5
water_temp_c = 12.0
wind_gust_ms = 10.7
battery_v = 13.12
qc_passed = true

[[observation.sensors]]
tag = "accelerometer"
status = "offline"
samples = 1933

[[observation.sensors]]
tag = "thermistor"
status = "degraded"
samples = 1866

[[observation.sensors]]
tag = "anemometer"
status = "degraded"
samples = 318

[observation.position]
lat = 57.21621
lon = -2.37579
```

`[[observation.sensors]]` adds a sensor to the most recent observation, and every header repeats the full path from the root. One record spells `observation` six times, and a fourth level of nesting would repeat three names in every header. `position` has also moved to the end. Once a header opens, every key below it belongs to that header, so a writer has to put plain keys before any sub-table, and the record's field order is gone. `tomli_w` writes the sensors as inline tables in a bracketed list instead: 18 lines rather than 28. In TOML 1.0, though, an inline table must fit on one line. That is the awkwardness the spec chose on purpose, because it makes deep nesting look as costly as it is to edit.

**Comments survive only with the right library.** I changed one threshold in `fleet.toml` both ways:

```
                       bytes  lines  comments
original                 664     24         5
tomllib + tomli_w        458     26         0
tomlkit                  664     24         5

tomlkit changed 1 line(s): ['wave_height_m = 7.0   # page the duty officer above this']
```

Loading the file into dictionaries and writing them back removed all five comments, turned `0o640` into `416`, and spread `share_with` over five lines. `tomlkit`, written for Poetry, keeps the document's layout and changed exactly one line. A tool that edits `pyproject.toml` for people has to use something like it.

---

### The measurement

Nobody should keep 50,000 sensor readings in TOML. But config formats do end up holding data: `Cargo.lock`, `poetry.lock` and `uv.lock` are all TOML. Here is the series' payload, shaped as above. Every writer's output was checked to read back to the original records:

```
50000 buoy records, best of up to 5; tomli_w 1.2.0, tomli 2.5.0, tomlkit 0.15.2, rtoml 0.14.0
notes is null in 47485 records (95.0%): TOML has no null, so those keys are dropped

format                   bytes     gzip -9     zstd -3     lines
JSON                20,790,509   1,872,392   2,344,331         0
TOML, tomli_w       22,822,671   1,915,002   2,422,612   952,455
TOML, rtoml         23,971,845   1,942,828   2,469,918 1,452,219
TOML, tomlkit       23,971,845   1,942,828   2,469,918 1,452,219

write, ms                           ms  vs json  runs
json.dumps                       210.7       1x     5
tomli_w dumps                   2140.7      10x     5
rtoml dumps                      222.2       1x     5
tomlkit dumps                  48490.4     230x     1

read, ms                            ms  vs json  runs
json.loads                       334.9       1x     5
tomllib.loads (stdlib)          6649.1      20x     5
tomli.loads                     3743.1      11x     5
rtoml.loads                      765.2       2x     5
tomlkit.parse                  54218.6     162x     1
```

TOML came out 9.8% bigger than compact JSON with `tomli_w`'s inline sensors and 15.3% bigger with the all-headers layout, even with 47,485 fewer fields and unquoted timestamps. The header layout is 1.45 million lines, because every record repeats `[[observation]]` and every sensor repeats `[[observation.sensors]]`. Gzip closes most of the gap, to 2.3% and 3.8% bigger. Repeated headers compress as easily as repeated JSON keys.

Speed is where TOML falls behind. The standard library's `tomllib` took 6.6 seconds against 0.33 for `json.loads`, 20 times as long. `tomli` is the same parser, the one copied into the standard library as `tomllib`, but installed as a compiled wheel it took 3.7 seconds. rtoml, written in Rust, read in 0.77 seconds and wrote as fast as `json`. `tomlkit` took 48 seconds to write and 54 to read, which is the price of tracking every comment and space.

At config size none of this matters. `tomllib` parsed the 664-byte `fleet.toml` in 114.5 µs, against 4.3 µs for the same settings as JSON.

---

### Where JSON still wins

Anywhere a program writes the file. Payloads have nulls, deep nesting and long arrays of records, and TOML handles all three badly.

Anywhere two languages exchange data. JSON parsers disagree only at the edges earlier articles covered, such as `NaN` and 64-bit integers. TOML readers are currently split between 1.0 and 1.1, and each language maps the four date and time types onto its own classes.

Anywhere data is read in bulk. On 20.8 MB of records, `json.loads` was 20 times faster than `tomllib` and 2.3 times faster than the Rust parser, and gzipped JSON was smaller than every TOML layout.

---

### Conclusion

Use TOML for configuration people write by hand: project metadata, service settings, anything that wants comments and real dates and stays two or three levels deep. Its types come from syntax, so a wrong value is an error, not a boolean.

Use JSON for data: anything generated, nested, nullable, exchanged or read in bulk.

The cost of TOML is everything a config file never needed. There is no null, nesting is written as repeated headers that move nested tables to the end of a record, and a load-and-dump round trip deletes every comment unless the tool is `tomlkit`. On the buoy payload, it was also 2.3% to 3.8% bigger than JSON after gzip and 20 times slower to read with the standard library.

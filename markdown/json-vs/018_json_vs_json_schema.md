# JSON vs. JSON Schema

#### json.loads accepted 7,000 broken records without complaint. A strict schema caught 6,000 of them, but only after I turned on two checks that are off by default

**By Tihomir Manushev**

*Nov 24, 2026 · 8 min read*

---

JSON promises one thing: the bytes are well-formed. It says nothing about whether `wave_height_m` is a number, whether `qc_passed` is a boolean, or whether a field called `notes` exists at all. While one program writes the data and the same team reads it, that is enough, because the contract lives in both heads. It stops being enough when a second team, a vendor or a firmware update starts producing the records. A parser cannot reject a document for being wrong if it is still well-formed.

JSON Schema is the missing contract. It is not a different encoding: the schema is itself a JSON document that describes which JSON documents are acceptable.

To test it, I took the series' 50,000 buoy records and broke 7,000 of them with seven realistic producer bugs, 1,000 records per bug. `json.loads` rejected none. A first-draft schema caught 2,000, and a strict one caught 6,000. One bug got past every schema I wrote.

---

### The same document, both ways

The series' first record:

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

And the contract for it, in draft 2020-12, the version current validators implement:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/buoy-observation.json",
  "title": "Buoy observation",
  "type": "object",
  "required": ["observation_id", "buoy_id", "recorded_at", "position",
               "wave_height_m", "water_temp_c", "wind_gust_ms", "battery_v",
               "qc_passed", "sensors"],
  "additionalProperties": false,
  "properties": {
    "observation_id": {"type": "integer", "minimum": 1},
    "buoy_id": {"type": "string", "pattern": "^[A-Z]{2}-[0-9]{2,3}$"},
    "recorded_at": {"type": "string", "format": "date-time"},
    "position": {
      "type": "object",
      "required": ["lat", "lon"],
      "additionalProperties": false,
      "properties": {
        "lat": {"type": "number", "minimum": -90, "maximum": 90},
        "lon": {"type": "number", "minimum": -180, "maximum": 180}
      }
    },
    "wave_height_m": {"type": "number", "minimum": 0, "maximum": 30},
    "water_temp_c": {"type": "number", "minimum": -2, "maximum": 40},
    "wind_gust_ms": {"type": "number", "minimum": 0, "maximum": 90},
    "battery_v": {"type": "number", "minimum": 0, "maximum": 24},
    "qc_passed": {"type": "boolean"},
    "notes": {"type": ["string", "null"], "default": null},
    "sensors": {
      "type": "array",
      "minItems": 1,
      "items": {"$ref": "#/$defs/sensor"}
    }
  },
  "$defs": {
    "sensor": {
      "type": "object",
      "required": ["tag", "status", "samples"],
      "additionalProperties": false,
      "properties": {
        "tag": {"enum": ["accelerometer", "thermistor", "anemometer", "gps"]},
        "status": {"enum": ["ok", "degraded", "offline"]},
        "samples": {"type": "integer", "minimum": 0}
      }
    }
  }
}
```

The record is 427 bytes compact and the schema is 1,370, so the contract is three times the size of the thing it describes. That is normal, because the schema has to say everything that JSON leaves unsaid.

A few of these keywords decide most of the behaviour. **`required`** and **`type`** answer different questions. `notes` is not in `required`, so the key may be missing, and its type allows `null`, so when the key is there its value may be empty. "Absent" and "present but null" are two separate states, and the schema has to say which ones it allows. **`$defs`** holds reusable pieces and **`$ref`** points at them, so the sensor shape is written once. A `pattern` on `buoy_id` accepts buoys that have not been deployed yet, while an `enum` on `status` rejects anything the consumer has no code path for. Choosing between the two is a decision about coupling.

The first-draft schema in the lab is the same file with only types and `required` kept. It has no `additionalProperties`, ranges, patterns, enums or `minItems`, and it is the kind of schema people usually write first.

---

### What JSON Schema actually changes

It moves the failure to the boundary. Here is one wire message carrying five of the seven bugs, checked with Python's reference validator, `jsonschema` 4.26.0:

```python
import json
from operator import attrgetter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(Path("buoy.schema.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())

wire = """{"observation_id": 9007199254740993, "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00",
  "position": {"lat": 57.21621, "lon": -2.37579},
  "wave_height_m": -999.0, "water_temp_c": 12.0, "wind_gust_ms": 10.7,
  "battery_v": 13.12, "qc_passed": "false", "note": "drifted off station",
  "sensors": [{"tag": "accelerometer", "status": "OFFLINE", "samples": 1933}]}"""

reading = json.loads(wire)

print(bool(reading["qc_passed"]), reading.get("notes"))  # True None

for error in sorted(validator.iter_errors(reading), key=attrgetter("json_path")):
    print(f"{error.json_path}: {error.message}")

# $: Additional properties are not allowed ('note' was unexpected)
# $.qc_passed: 'false' is not of type 'boolean'
# $.recorded_at: '2026-02-11T00:00:00' is not a 'date-time'
# $.sensors[0].status: 'OFFLINE' is not one of ['ok', 'degraded', 'offline']
# $.wave_height_m: -999.0 is less than the minimum of 0
```

The first `print` shows what the consumer sees without validation. The string `"false"` is truthy, so a reading that failed QC now passes it, and the note was sent under the wrong key, so `get("notes")` returns `None`. `iter_errors` reports every violation with a path, not only the first one, and that list is the error response a producer can act on.

Two of those five errors appear only because of a setting most people never change. The first is **`additionalProperties`**. Objects in JSON Schema are open by default, so an unknown key such as `note` is allowed, and because `notes` is optional nothing is missing either. The record validates while the producer's note is silently thrown away. You need `additionalProperties: false` to close the object.

The second is **`format`**. In draft 2020-12, `format` is an *annotation*, a label that validators may ignore. Without `format_checker=FormatChecker()`, `"yesterday at noon"` is a valid `date-time`. With the checker, `jsonschema` checks `date-time` only when the optional `rfc3339-validator` package is installed. In an environment without it, `FormatChecker()` quietly leaves `date-time` off its list and accepts `"yesterday at noon"` with no warning. I hit this in the lab with `jsonschema` installed and nothing else.

`default` is also an annotation. Validating a record that has no `notes` key leaves the key absent. The schema records what the default is, but `jsonschema` does not fill it in.

---

### The measurement

Seven bugs, 1,000 records each, against four checks:

```
fault                         json.loads   first draft   + formats   strict + formats
stringified_number                     0         1,000       1,000              1,000
truthy_string                          0         1,000       1,000              1,000
sentinel_value                         0             0           0              1,000
naive_timestamp                        0             0       1,000              1,000
misspelled_optional_key                0             0           0              1,000
uppercase_enum                         0             0           0              1,000
swapped_coordinates                    0             0           0                  0
caught of 7,000                        0         2,000       3,000              6,000
clean records rejected                 0             0           0                  0
```

The first draft caught only wrong types. The strict schema also caught the `-999` sentinel, the timestamp without an offset, the misspelled key and the uppercase enum value, and it rejected none of the 43,000 clean records. The one bug nothing caught matters too: swapped coordinates give a latitude of -2.38 and a longitude of 57.22, and both are valid numbers. A tight bounding box around the harbour would catch them, but it would also put the deployment's geography into the contract.

Without a schema, the feed corrupts the results quietly. Summing every wave height raises a `TypeError` because of the strings, which at least stops the job. Averaging only the numeric ones gives **-16.606 m** instead of 3.858, 74 failed readings pass the QC filter, and 0 of the 1,000 misfiled notes reach the consumer.

Validation takes CPU time, and how much depends on the library:

```
step                              records   us/record   x parse
json.loads per line                50,000        7.67       1.0
jsonschema, built once             50,000      237.99      31.0
jsonschema + FormatChecker         50,000      249.92      32.6
fastjsonschema, compiled           50,000       12.18       1.6
fastjsonschema + formats           50,000       12.66       1.6
jsonschema.validate() per call      5,000     5967.79     777.6
```

`jsonschema` walks the schema for every record, so validating takes 31 times as long as parsing. `fastjsonschema` 2.22.3 compiles the schema into 176 lines of Python in 6 ms, and then validating costs 1.6 times the parse. The last row is the pattern that tutorials show: `jsonschema.validate(record, schema)` checks the schema against the meta-schema and builds a new validator on every call, which makes it 778 times slower than parsing. Build the validator once.

The faster library does not implement the same spec, though. `fastjsonschema` supports drafts 4, 6 and 7. Given a 2020-12 URI, it falls back to its draft-2019 generator without any warning. It caught the same 6,000 records here because nothing in this schema changed meaning between drafts. A `position` written as a `[lat, lon]` pair, with `prefixItems` and `items: false`, does change meaning: `jsonschema` accepts `[57.21621, -2.37579]`, while `fastjsonschema` rejects it with "data must not be there". It also applies `default` by writing `"notes": None` into the dict you passed in. The two validators give different answers on the same schema, so the version and the library are part of the contract too.

---

### Where JSON still wins

When one team owns both ends. A schema then repeats what the type checker or the dataclass already knows, and keeping two descriptions in sync is its own source of bugs.

When producers need to evolve. `additionalProperties: false` caught the typo, but it will also reject the day a producer adds `salinity_psu`. A closed schema means every new field needs a coordinated release. Many APIs validate strictly on the way out and leniently on the way in, and that choice is the coupling decision again.

When the data is wrong but well-shaped. A schema checks shape, so the swapped coordinates, a `recorded_at` an hour in the future, and a buoy reporting for a different buoy all pass. Those need checks in code.

And on a hot path, if your language's only mature validator is the slow one: at 238 µs per record, the 50,000 records took 12 seconds of CPU to validate after 0.38 seconds of parsing.

---

### Conclusion

Put JSON Schema wherever JSON crosses a team boundary: public APIs, queues with more than one producer, and files from vendors. It turns six kinds of quiet corruption into errors with paths, it rejected none of the 43,000 good records, and the same file can generate documentation and client types.

Write the strict version. Close objects with `additionalProperties: false`, add ranges and enums, pass a format checker, and confirm that the checker actually knows `date-time`. A first-draft schema that only checks types caught two of the seven bugs.

The cost of JSON Schema is CPU time and coupling: the reference validator was 31 times slower than the parse, a closed schema turns every new field into a coordinated release, and two validators can disagree about what the same schema means. Pin the library as carefully as the schema.

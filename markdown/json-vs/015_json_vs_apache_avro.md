# JSON vs. Apache Avro

#### 71% smaller than JSON with no field names and no tags in the bytes, which works only while every reader has the writer's exact schema

**By Tihomir Manushev**

*Oct 12, 2026 · 8 min read*

---

JSON writes the meaning next to every value. `"wave_height_m": 3.5` can be read by anyone, with no prior agreement, which is why JSON is the default for data that crosses a boundary. It is also why the series' 50,000 buoy observations repeat the same field names 50,000 times.

Last time, Protocol Buffers replaced those names with field numbers. Avro goes further and removes the numbers too. An Avro record body is only the values, in the order the schema lists them. The schema is written once at the head of a file, or kept in a registry and referenced by id, and a reader needs it to make sense of a single byte.

I measured it with `fastavro` 1.13.1. The 50,000 records came out 71.1% smaller than JSON, smaller than Protobuf, and 16.0% bigger once both were gzipped. Avro's main risk showed up in a 24-byte test record: read with the wrong schema, a 3.5-metre wave came back as 12 metres, and nothing raised an error.

---

### The same record, both ways

An Avro schema is itself JSON, saved as `buoy.avsc`:

```json
{
  "type": "record",
  "name": "Observation",
  "namespace": "buoy.v1",
  "fields": [
    {"name": "observation_id", "type": "long"},
    {"name": "buoy_id", "type": "string"},
    {"name": "recorded_at",
     "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "position", "type": {
      "type": "record", "name": "Position",
      "fields": [
        {"name": "lat", "type": "double"},
        {"name": "lon", "type": "double"}
      ]}},
    {"name": "wave_height_m", "type": ["null", "double"], "default": null},
    {"name": "water_temp_c", "type": ["null", "double"], "default": null},
    {"name": "wind_gust_ms", "type": ["null", "double"], "default": null},
    {"name": "battery_v", "type": ["null", "double"], "default": null},
    {"name": "qc_passed", "type": "boolean"},
    {"name": "notes", "type": ["null", "string"], "default": null},
    {"name": "sensors", "type": {"type": "array", "items": {
      "type": "record", "name": "Sensor",
      "fields": [
        {"name": "tag", "type": "string"},
        {"name": "status", "type": {"type": "enum", "name": "SensorStatus",
                                    "symbols": ["ok", "degraded", "offline"]}},
        {"name": "samples", "type": "int"}
      ]}}}
  ]
}
```

A nullable value is a **union**, `["null", "double"]`, and the writer spends one byte saying which branch it took. The timestamp is a `long` with a `timestamp-millis` **logical type**, so the 25-character ISO string becomes a number. Sensor status is an enum, as in the Protobuf schema, but `fastavro` takes the strings `"ok"` and `"degraded"` directly with no mapping table.

Then the series' first record, encoded twice:

```python
import io
import json
from datetime import datetime
from pathlib import Path

from fastavro import parse_schema, reader, schemaless_writer, writer

schema = parse_schema(json.loads(Path("buoy.avsc").read_text()))

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
record = {**reading, "recorded_at": datetime.fromisoformat(reading["recorded_at"])}

body = io.BytesIO()
schemaless_writer(body, schema, record)
as_json = json.dumps(reading, separators=(",", ":")).encode()
print(len(as_json), len(body.getvalue()))  # 427 121
print(body.getvalue()[:16].hex(" "))
# 82 80 80 80 80 80 80 20 0a 4e 45 2d 30 38 80 90

with open("buoy.avro", "wb") as out:
    writer(out, schema, [record])
with open("buoy.avro", "rb") as source:
    avro_file = reader(source)
    print(avro_file.writer_schema["name"], next(avro_file)["wave_height_m"])
    # buoy.v1.Observation 3.5
```

427 bytes become 121, against Protobuf's 142 for the same record. The difference is the first byte. Protobuf opened with `0x08`, a tag announcing field 1. Avro opens with the value itself: `82 80 … 20` is the id as a zigzag varint. Then `0a` is a string length of 5, then `NE-08`, then `80 90` starts the timestamp. Nothing marks where one field ends and the next begins. The reader knows because the schema says a long comes first, then a string, then another long.

`schemaless_writer` produces the bare body. `writer` produces an **object container file**, and that file starts with the magic bytes `Obj\x01`, a metadata map holding the codec name and the entire schema as JSON text, then a random 16-byte sync marker. That header cost 1,136 bytes here. `reader` takes the schema back out of it, which is why `avro_file.writer_schema` knows its own name. A file describes itself once instead of once per record.

---

### What Avro actually changes

**There are two schemas, and Avro resolves between them.** The writer's schema says how the bytes were laid out. The reader's schema says what the application wants. Avro matches fields by name, fills gaps from defaults, and refuses what it cannot reconcile. The lab wrote a three-field `Reading` with v1 and read it back with several v2s:

```
v1 body: 24 bytes, 82 80 80 80 80 80 80 20 00 00 00 00 00 00 0c 40 00 00 00 00 00 00 28 40

1. reader adds a field with a default: filled in
   v1 bytes, v2 reader: {..., 'wave_height_m': 3.5, 'water_temp_c': 12.0, 'buoy_id': 'unknown'}

2. reader adds a field without a default: refused, loudly
   v1 bytes, v2 reader: SchemaResolutionError: No default value for field buoy_id in buoy.v1.Reading

3. rename with an alias: resolved by the old name
   v1 bytes, v2 reader: {..., 'significant_wave_height_m': 3.5, 'water_temp_c': 12.0}

4. rename without an alias, new field nullable: no error, the value is gone
   v1 bytes, v2 reader: {..., 'water_temp_c': 12.0, 'significant_wave_height_m': None}
```

An added field needs a default, or old data cannot be read. A missing default fails with a clear error, where a Protobuf reader would have handed back a zero. A rename works if the new field lists the old name in `aliases`. If the renamed field is nullable with a default and has no alias, the rename silently drops every historical value. The resolver finds no field with the new name in the old data and fills in the default.

**Resolution needs the exact writer's schema.** The body carries no names, so nothing in it can show that the wrong schema was used:

```python
import io

from fastavro import parse_schema, schemaless_reader, schemaless_writer


def reading(*names: str) -> dict:
    """A Reading record: a long id, then one double per name, in that order."""
    fields = [{"name": "observation_id", "type": "long"}]
    fields += [{"name": name, "type": "double"} for name in names]
    return parse_schema({"type": "record", "name": "Reading", "fields": fields})


written_with = reading("wave_height_m", "water_temp_c")
read_with = reading("water_temp_c", "wave_height_m")

body = io.BytesIO()
schemaless_writer(body, written_with, {"observation_id": 9007199254740993,
                                       "wave_height_m": 3.5, "water_temp_c": 12.0})
print(len(body.getvalue()))  # 24

body.seek(0)
print(schemaless_reader(body, read_with))  # read_with taken as the writer's schema
# {'observation_id': 9007199254740993, 'water_temp_c': 3.5, 'wave_height_m': 12.0}

body.seek(0)
print(schemaless_reader(body, written_with, read_with))  # resolved by name
# {'observation_id': 9007199254740993, 'wave_height_m': 3.5, 'water_temp_c': 12.0}
```

The same 24 bytes, two answers. Given the reordered schema as the writer's, the decoder reads two doubles in the wrong order and reports a 12-metre wave in 3.5-degree water. Given both schemas, it resolves by name and gets it right. Reordering fields is a safe change in Avro only when the reader knows which schema the writer used.

That is the job of a **schema registry**. The common Kafka framing, from Confluent, puts a zero byte and a 4-byte schema id in front of every message:

```
framed: 00 00 00 00 29 | 82 80 80 80 80 80 80 20 00 00 00 00 00 00 0c 40 00 00 00 00 00 00 28 40  (29 bytes)
magic=0, schema id=41; consumer on v2 reads: {..., 'wave_height_m': 3.5, 'water_temp_c': 12.0, 'buoy_id': 'unknown'}
```

Five bytes buy the writer's schema id. The consumer fetches schema 41, resolves it against its own v2, and gets the default for the new field. A registry can also check compatibility rules such as "every new field has a default" when a schema is registered, so the error from case 2 shows up before anything is deployed. Once records go onto a topic rather than into a file, the registry becomes required infrastructure.

---

### The measurement

50,000 records, best of five, dicts to bytes and back on both sides. Each codec compresses one block at a time; deflate ran at level 9 to match `gzip -9`:

```
format                           bytes     gzip -9     zstd -3
JSON                        20,790,509   1,872,392   2,344,331
MessagePack                 17,264,785   2,447,545   2,381,288
Avro file, codec null        6,016,941   2,172,548   2,170,498
Avro file, codec deflate     2,442,343
Avro file, codec snappy      3,197,985
Avro file, codec zstandard   2,487,428
  Avro (null) vs JSON: raw 71.1% smaller, gzip 16.0% bigger, zstd 7.4% smaller

block size      blocks  deflate -9  zstandard -3
16,000             375   2,442,343     2,487,428
64,000              94   2,258,024     2,358,152
1,000,000            7   2,175,724     2,195,075
64,000,000           1   2,170,466     2,157,362

one record on its own
  JSON                                427 bytes raw   288 gzipped
  Avro body, no schema                121 bytes raw   123 gzipped
  Avro container file, one record    1276 bytes raw   530 gzipped

time, ms, dicts -> bytes -> dicts          JSON       Avro
  encode                                  210.6      764.1
  decode                                  258.4      626.2
```

Raw, Avro is 6.0 MB against JSON's 20.8, and 16% smaller than Protobuf's 7.2 MB on the same payload. Protobuf spends a tag on every field, and Avro does not.

Gzip reverses it again: the Avro file is 16.0% bigger than gzipped JSON. JSON's repeated keys are what gzip removes most easily, and Avro had already removed them. What remains is mostly binary doubles that do not compress well.

The built-in codecs do worse than whole-file gzip. At `fastavro`'s default of a new block every 16 KB, the deflate file is 30.4% bigger than gzipped JSON and snappy is 70.8% bigger. Compressing each block separately is what lets a tool like Spark split a file at its sync markers and read the pieces in parallel. With small blocks, though, each one starts the compressor with no history. Fewer, larger blocks help, but even a single 6 MB block was still 15 to 16% bigger than gzipped JSON on this payload.

A single record compressed on its own reverses the result. A bare body is 121 bytes, 126 with registry framing, against 288 for gzipped JSON. A container file holding one record, however, is 1,276 bytes, three times the JSON, because the schema is included. Use files for batches and bare bodies plus a registry id for messages.

In Python, Avro does not save time. `fastavro` was 3.6 times slower than `json` to encode and 2.4 times slower to decode. Only 25 ms of the 764 went to converting timestamps, so nearly all of it is the encoder walking the schema.

---

### Where JSON still wins

Anywhere the reader has neither the file header nor a registry. Browsers, `curl`, log search and a payload pasted into a ticket all need data that explains itself. Avro has a JSON encoding, but it is its own dialect: the lab's record came out as `"wave_height_m": {"double": 3.5}` and `"recorded_at": 1770768000000`, with every union branch wrapped and the timestamp as raw milliseconds.

For bulk transfers over compressed HTTP, gzipped JSON was smaller than every Avro variant measured here. For Python services that turn records into dicts and back, plain `json` was faster.

When there is no registry and no shared schema discipline. Avro's guarantees depend on knowing exactly which schema wrote each byte, and if the wrong one is used, the data is wrong and nothing reports it.

---

### Conclusion

Use Avro where many records share one schema and the schema can travel with them or sit in a registry. That means data-lake files written once and read by Spark or Hive, and Kafka topics where producers and consumers deploy independently. Avro's evolution model is its strongest feature: defaults fill new fields, aliases carry renames, and a missing default fails at resolution time rather than reading as zero.

Keep JSON for anything read by people or by tools you do not control, and for any path where gzip already does the compressing.

The cost is that the bytes carry no meaning by themselves. Every reader depends on a header or a registry, every schema change needs a default or an alias, and decoding with the wrong writer's schema gives wrong values with no error. On this payload, the 71% raw saving also became a 16% loss after gzip.

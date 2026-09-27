# JSON vs. Protocol Buffers

#### 65% smaller on the wire and 19x faster to parse, until you gzip a big batch or turn the messages back into dicts

**By Tihomir Manushev**

*Sep 27, 2026 · 8 min read*

---

JSON describes itself. Every record carries its field names, so any reader can open it with no prior agreement: `"wave_height_m": 3.5` says what it is. That is why JSON is the default, and why it repeats the same keys fifty thousand times in a fifty-thousand-record file.

Protocol Buffers trade that property away on purpose. Both sides compile the same schema, and the bytes carry only field numbers and values. The payload shrinks, parsing becomes a table lookup, and a reader without the schema sees numbered fields and hex.

I compiled a schema for the series' 50,000 harbour buoy observations and measured it with `protobuf` 7.36.2 and its C-based `upb` backend. Protobuf came out 65.5% smaller than JSON and parsed 19 times faster. Gzipped as one big batch, it was 17.6% *bigger*, and code that works with Python dicts ran twice as slowly. Both results come from the same trade.

---

### The same record, both ways

The schema comes first. This is the whole contract between writer and reader:

```protobuf
syntax = "proto3";

package buoy.v1;

import "google/protobuf/timestamp.proto";

message Position {
  double lat = 1;
  double lon = 2;
}

enum SensorStatus {
  SENSOR_STATUS_UNSPECIFIED = 0;
  SENSOR_STATUS_OK = 1;
  SENSOR_STATUS_DEGRADED = 2;
  SENSOR_STATUS_OFFLINE = 3;
}

message Sensor {
  string tag = 1;
  SensorStatus status = 2;
  uint32 samples = 3;
}

message Observation {
  uint64 observation_id = 1;
  string buoy_id = 2;
  google.protobuf.Timestamp recorded_at = 3;
  Position position = 4;
  optional double wave_height_m = 5;
  optional double water_temp_c = 6;
  optional double wind_gust_ms = 7;
  optional double battery_v = 8;
  bool qc_passed = 9;
  optional string notes = 10;
  repeated Sensor sensors = 11;
}

message Batch {
  repeated Observation observations = 1;
}
```

`protoc` turns it into a Python module:

```bash
pip install protobuf==7.36.2 grpcio-tools==1.84.0
python -m grpc_tools.protoc -I. --python_out=. buoy.proto
```

Then one observation, built from the series' first record:

```python
import json
from datetime import datetime
from pathlib import Path

import buoy_pb2

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
STATUS = {"ok": buoy_pb2.SENSOR_STATUS_OK,
          "degraded": buoy_pb2.SENSOR_STATUS_DEGRADED,
          "offline": buoy_pb2.SENSOR_STATUS_OFFLINE}

observation = buoy_pb2.Observation(
    observation_id=reading["observation_id"],
    buoy_id=reading["buoy_id"],
    position=buoy_pb2.Position(**reading["position"]),
    wave_height_m=reading["wave_height_m"],
    water_temp_c=reading["water_temp_c"],
    wind_gust_ms=reading["wind_gust_ms"],
    battery_v=reading["battery_v"],
    qc_passed=reading["qc_passed"],
    sensors=[buoy_pb2.Sensor(tag=s["tag"], status=STATUS[s["status"]],
                             samples=s["samples"]) for s in reading["sensors"]],
)
observation.recorded_at.FromDatetime(datetime.fromisoformat(reading["recorded_at"]))

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_proto = observation.SerializeToString()
print(len(as_json), len(as_proto))  # 427 142
print(as_proto[:16].hex(" "))
# 08 81 80 80 80 80 80 80 10 12 05 4e 45 2d 30 38
Path("observation.bin").write_bytes(as_proto)
```

427 bytes become 142. The first byte shows where the savings come from. `0x08` packs field number 1 with wire type 0, a **varint**. The id follows in 8 bytes instead of 16 characters. `0x12 0x05` then means field 2, length-delimited, five bytes, and `NE-08` follows. Field names never appear; the schema carries them.

The schema made three other choices that shrink the record. The timestamp is a `Timestamp` message holding seconds and nanoseconds rather than 25 characters of ISO 8601. Each sensor status is an enum, one byte rather than `"degraded"`. And `notes`, absent here, costs nothing, where JSON spends `"notes":null`.

---

### What Protocol Buffers actually change

**The field number is the contract, not the name.** That makes some changes free and others dangerous. Three small schemas show which, starting from a `Reading` with `observation_id = 1` and `wave_height_m = 2`:

```protobuf
// reading_v2.proto: field 2 renamed, field 3 added, numbers unchanged
message Reading {
  uint64 observation_id = 1;
  double significant_wave_height_m = 2;
  string buoy_id = 3;
}

// reading_reused.proto: field 2 retired, its number given to a new string
message Reading {
  uint64 observation_id = 1;
  string station_name = 2;
}
```

The lab wrote messages with one version and read them with another:

```
1. new writer, old reader: the added field is kept, not understood
   v1 sees wave_height_m=3.5; unknown fields kept: [(3, b'NE-08')]
   v1 re-serialises it byte-identical: True

2. rename: free on the wire, a breaking change in JSON
   v2 reads v1 bytes: significant_wave_height_m=3.5
   v1 as JSON: {"observationId": "1", "waveHeightM": 3.5}
   v2 as JSON: {"observationId": "1", "significantWaveHeightM": 3.5}

3. a reused field number: no error, the value just disappears
   station_name=''  (the 3.5 is silently set aside)
```

Adding a field is safe in both directions. An old reader keeps the unknown bytes and passes them on intact, which is what lets services upgrade one at a time. Renaming is free between protobuf peers, and a breaking change for anyone reading the JSON mapping. Reusing a number is the real trap. The new reader expects a string where a double arrives, treats it as an unknown field, and returns an empty `station_name` with no error. Protobuf's answer is to mark retired numbers `reserved` so the compiler refuses to reuse them.

**Absent and zero can look the same.** In proto3 a plain `double` that was never set reads as `0.0`. For a wave sensor that dropped out, that is a reading of a flat calm sea. The lab's `Reading` without a wave height serialises to 2 bytes and reads back `wave_height_m=0.0`. That is why every measurement in `buoy.v1` is declared `optional`, which restores `HasField()` and lets a dropout stay a dropout.

**Without the schema, the bytes say very little:**

```bash
python -m grpc_tools.protoc --decode_raw < observation.bin
```

```
1: 9007199254740993
2: "NE-08"
3 {
  1: 1770768000
}
4 {
  1: 0x404c9bacc4ef88b9
  2: 0xc003019e30014f8b
}
5: 0x400c000000000000
```

The strings and integers survive. Doubles are raw IEEE 754 bits, and nothing says field 5 is a wave height. Debugging a protobuf payload means having the right `.proto` at hand.

---

### The measurement

50,000 records in one `Batch`, best of five, with the garbage collector paused while timing:

```
format               bytes     gzip -9     zstd -3
JSON            20,790,509   1,872,392   2,344,331
Protobuf         7,181,452   2,201,567   2,244,764
MessagePack     17,264,785   2,447,545   2,381,288
  Protobuf vs JSON: raw 65.5% smaller, gzip 17.6% bigger, zstd 4.2% smaller

time, ms                      JSON   Protobuf
  bytes only: encode          233.0       13.3   (SerializeToString)
  bytes only: decode          259.3       13.3   (ParseFromString)
  dicts -> bytes              233.0      467.6   (build messages 454.4 + serialize)
  bytes -> dicts              259.3      489.4   (parse + read fields 476.1)
```

Raw, Protobuf is a third of JSON's size, and less than half of MessagePack's. The field numbers remove what MessagePack keeps, the key names in every record.

Gzip reverses it. Compressed, Protobuf is 17.6% bigger than JSON. The keys that made JSON large are exactly what gzip removes most cheaply. Protobuf had already removed them, and what remains is mostly binary doubles, which do not compress. zstd splits the difference: 4.2% smaller.

That reversal needs volume, though. Gzip finds JSON's repeated keys by seeing them many times, and a single message gives it almost nothing to work with:

```
one record on its own, as an RPC would send it
  JSON           427 bytes raw   288 gzipped
  Protobuf       142 bytes raw   141 gzipped
```

One record compressed alone, the way a request or an event on a queue is sent, gzips to 288 bytes as JSON. Protobuf needs 141 with no compression at all. The 20 MB batch is where JSON catches up, and individual messages are where Protobuf stays ahead.

The timing table holds the second reversal. `SerializeToString` and `ParseFromString` run in C, 17 and 19 times faster than `json`. But building 50,000 message objects from Python dicts took 454 ms, and reading their fields back took 476, so dicts to bytes to dicts was about twice as slow as `json`. The speed is real only for code that works with the generated classes directly, and it disappears if every message is converted back to a dict.

---

### Where JSON still wins

Anywhere a reader has no schema. Browsers, log pipelines, `curl`, a colleague pasting a payload into a ticket: all of them read JSON and none of them read field numbers. Protobuf has an official JSON mapping, but it is its own dialect. The lab's record came out with `"observationId": "9007199254740993"`, camelCase names and a 64-bit integer written as a string.

For bulk transfers over compressed HTTP, JSON was smaller on this payload. If the goal is fewer bytes for a large gzipped response, protobuf is not the fix.

When producer and consumer do not deploy together. The schema is shared code, and every change needs the evolution rules above. A reused field number fails silently, not loudly.

---

### Conclusion

Use Protocol Buffers between services you own. A typed, versioned schema, fast native parsing, compact messages, and clear rules for evolving the format are worth the compile step. It works best where code uses the generated classes directly instead of converting them to dicts. That is the gRPC case, and it is where protobuf is strongest.

Keep JSON for anything read by people, browsers or tools you do not control, and for any path where gzip already does the compressing.

The cost is readability and coupling. A message is meaningless without its `.proto`, every change to the schema follows rules a mistake can break silently, and on this payload's 50,000-record batch the 65% raw saving became a 17.6% loss after gzip.

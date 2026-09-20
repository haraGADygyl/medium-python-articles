# JSON vs. MessagePack

#### 17% smaller on the wire, 31% *bigger* once you gzip it — the reason to switch is decode speed, not size

**By Tihomir Manushev**

*Sep 20, 2026 · 6 min read*

---

MessagePack sells itself in five words on its own home page: "It's like JSON. but fast and small." That is the version everyone repeats, and it is the version that sends people migrating a payload for the wrong reason.

Everything below ran on Python 3.12 with `msgpack` 1.1.0. I measured it on 50,000 harbour buoy observations — mixed floats, integers, booleans, nulls, nested objects and arrays, the shape telemetry actually has. MessagePack came out 17% smaller than JSON. Then I compressed both, the way anything crossing a network already is, and MessagePack came out **31% larger**.

The speed claim held up. The size claim inverted. Here is where the line actually falls.

---

### The same record, both ways

One observation, as JSON and as MessagePack:

```json
{
  "observation_id": 9007199254740993,
  "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00+00:00",
  "position": {"lat": 57.21621, "lon": -2.37579},
  "wave_height_m": 3.5,
  "qc_passed": true,
  "notes": null
}
```

```python
import json

import msgpack

reading = {
    "observation_id": 9007199254740993,
    "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T00:00:00+00:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5,
    "qc_passed": True,
    "notes": None,
}

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_msgpack = msgpack.packb(reading)

print(len(as_json), len(as_msgpack))     # 188 154
print(as_msgpack[:14])                   # b'\x87\xaeobservation_'
print(msgpack.unpackb(as_msgpack, raw=False) == reading)   # True
```

`raw=False` is worth typing even though it is the default in `msgpack` 1.0 and
later. Before 1.0 the default was `raw=True`, which hands back every string as
`bytes` — including the keys — so the comparison above prints `False` and your
dictionary lookups start failing with `KeyError`. Passing it explicitly works on
both. The timestamp example further down needs `msgpack` 1.0 or later, where the
packer learned the `datetime` option.

Those first two bytes are the whole design. `\x87` means "a map with seven pairs" — the count is in the type byte itself, so there is no `{`, no `}`, no commas to scan for. `\xae` means "a string of 14 bytes", so the parser reads a length and then jumps, instead of walking forward looking for an unescaped closing quote.

That is what MessagePack replaces: not the data, the *delimiters*. The keys are still there in full on every record, exactly as in JSON.

---

### Where the bytes go

The saving is not spread evenly across your data. It is concentrated in the types where JSON's text representation is most wasteful, and it reverses on the type most telemetry is made of:

```
64-bit id                 16 B json     9 B msgpack
timestamp                 27 B json     6 B msgpack
float 2.37                 4 B json     9 B msgpack
true                       4 B json     1 B msgpack
null                       4 B json     1 B msgpack
key 'wave_height_m'       15 B json    14 B msgpack
```

`true` costs four bytes of text and one byte of tag. A rounded float goes the other way: `2.37` is four characters, and MessagePack stores an IEEE 754 double in nine. Sensor readings rounded to two decimals — the most common shape in this kind of data — are *cheaper as text*.

Grouping 50,000 records by field type makes the split explicit:

```
shape                    JSON    msgpack  raw diff    JSON gz  msgpack gz  gz diff
rounded floats      1,525,258  1,700,003    -11.5%    389,483     425,197    -9.2%
small integers      1,217,722    554,065     54.5%    242,104     229,615     5.2%
booleans + nulls    1,499,902    500,003     66.7%     26,417      21,810    17.4%
free text           7,039,772  6,535,615      7.2%    702,689     841,533   -19.8%
```

Small integers and flags are where MessagePack wins big: 54.5% and 66.7%. Rounded floats lose 11.5%. Free text barely moves, because in both formats the bytes of the string dominate and everything else is rounding error.

---

### The measurement that changes the decision

Full payload, 50,000 records, best of five runs on Python 3.12 with `msgpack` 1.1.0:

```
format             bytes     gzip -9     zstd -3   encode ms   decode ms
JSON          20,790,509   1,872,392   2,344,331       211.5       289.4
MessagePack   17,264,785   2,447,545   2,381,288        96.2       200.6
```

Read the second column before the first. Gzipped JSON is 1.87 MB; gzipped MessagePack is 2.45 MB. The format that is smaller raw is **30.7% larger compressed**, and under zstd at level 3 the two are within 1.6% of each other — a tie.

The mechanism is not subtle once you see it. JSON repeats `"wave_height_m":` on every one of 50,000 records, and repetition is exactly what a compressor eats for free; those keys cost almost nothing after gzip. MessagePack replaces some of that redundant text with binary doubles, which look like noise to a compressor and cannot be squeezed. MessagePack starts smaller and compresses worse, and on this payload the second effect wins.

There is a harder number in that table. Gzipped JSON is 89.2% smaller than raw MessagePack. If your actual goal was fewer bytes on the wire, `Content-Encoding: gzip` on the JSON you already have beats the entire migration, and you can ship it this afternoon.

---

### What you are actually buying

Encode dropped from 211.5 ms to 96.2 ms, decode from 289.4 ms to 200.6 ms. That is 2.2× and 1.4×, and unlike the size number it survives compression, because you pay it per message on both ends regardless of what the transport does.

The gap is wider on encode than decode for a reason worth knowing: encoding JSON means escaping every string and formatting every float as text, while encoding MessagePack means writing a tag byte and copying bytes. Decoding is closer because CPython's `json` module does its scanning in C, so you are comparing two optimised C loops rather than beating an interpreter.

Two smaller things come with it. MessagePack has integers with a declared width, so the id that JavaScript silently mangles round-trips intact:

```python
print(msgpack.unpackb(as_msgpack, raw=False)["observation_id"])
# 9007199254740993
```

And it has a real timestamp type, which JSON does not:

```python
from datetime import datetime, timezone

stamped = msgpack.packb(
    {"recorded_at": datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc)},
    datetime=True)

print(len(stamped))                                     # 19
print(msgpack.unpackb(stamped, raw=False, timestamp=3)["recorded_at"])
# 2026-02-11 04:15:00+00:00
```

Nineteen bytes for the whole map, against 27 for the ISO string alone — and a `datetime` comes back, not text you have to parse. That is the extension-type mechanism, and you can register your own for decimals or UUIDs.

The third thing is framing. Concatenated MessagePack values are self-delimiting, so a reader can consume a socket without a length prefix or a newline convention:

```python
stream = b"".join(msgpack.packb(r) for r in [reading, reading, reading])
unpacker = msgpack.Unpacker(raw=False)

unpacker.feed(stream[:40])
print([r["buoy_id"] for r in unpacker])   # []
unpacker.feed(stream[40:])
print(sum(1 for _ in unpacker))           # 3
```

Feed it half a record and it yields nothing rather than failing. Feed it the rest and three records appear. Doing this with JSON means JSON Lines and a rule that no encoder may emit a raw newline.

---

### Where JSON still wins

You cannot read MessagePack. Every `curl` that returns a readable body, every log line you grep, every "just paste the payload into the bug report" stops working, and the replacement is a decoding step in every debugging session. On a public API that cost lands on people who do not work for you.

It is also weaker at the edges. Every language has a JSON parser in its standard library and a MessagePack library from a third party. Browsers parse JSON in native code; in the browser, `JSON.parse` will usually beat a JavaScript MessagePack decoder outright.

Tooling assumes JSON too. Schema validation, API gateways that inspect bodies, log pipelines that index fields, contract tests — all of it speaks JSON first, and a binary body turns each one into an integration task. None of that is hard, and all of it is work you were not planning.

And the format will not save you from yourself: keys repeat on every record here too. If your payload is 50,000 objects with identical keys, the format that fixes *that* is one with a schema — Avro or Protobuf — not a denser encoding of the same structure.

---

### Conclusion

MessagePack is worth it for internal, high-volume, machine-to-machine traffic where decode time shows up in a profile, where 64-bit ids or timestamps matter, or where you want self-delimiting framing on a stream. Those are real wins and they are all things compression cannot give you.

It is not worth it to make payloads smaller. On this dataset it saved 17% raw, lost 31% after gzip, tied under zstd, and was beaten 9:1 by simply compressing the JSON. Measure your own shape before you migrate: if it is mostly rounded floats and free text, MessagePack is bigger than JSON before compression and bigger after it.

The cost is permanent and the benefit is conditional. Pay it when the profiler asks, not when the home page does.

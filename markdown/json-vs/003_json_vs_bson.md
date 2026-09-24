# JSON vs. BSON

#### "Binary JSON" came out 2.9% bigger than JSON and 37.6% bigger gzipped. MongoDB picked it for traversal and types, not for size

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

The name does most of the misleading. BSON stands for Binary JSON, and "binary" is where people assume the size win lives. The format's own FAQ says otherwise: BSON is designed to be efficient in space, but in some cases it uses more space than JSON.

On the series' 50,000 harbour buoy observations, it did. Encoded one document per record, the way MongoDB stores and ships them, BSON came out 2.9% larger than JSON Lines. Under `gzip -9` it was 37.6% larger.

That is not a flaw in BSON. It is a different goal. BSON was built so a database engine can walk a document without parsing it, and so values keep types JSON does not have: 64-bit integers, dates, decimals, binary. Here is what those cost in bytes, and what they buy, measured with `pymongo` 4.18.2's `bson` module and its C extension.

---

### The same record, both ways

```python
import json
import struct
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bson
from bson.codec_options import CodecOptions

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

as_json = json.dumps(reading, separators=(",", ":")).encode()
as_bson = bson.encode(reading)

print(len(as_json), len(as_bson))  # 427 439
print(as_bson[:24])
# b'\xb7\x01\x00\x00\x12observation_id\x00\x01\x00\x00\x00'
print(bson.encode({"tags": ["gps", "thermistor"]}))
# b'-\x00\x00\x00\x04tags\x00"\x00\x00\x00\x020\x00\x04\x00\x00\x00gps\x00
#   \x021\x00\x0b\x00\x00\x00thermistor\x00\x00\x00'
```

A BSON document opens with its own length: `\xb7\x01\x00\x00` is 439, little-endian. Then comes a list of elements, each a type byte, a key as a null-terminated string, and a value. `\x12` is a 64-bit integer, followed by the key `observation_id` and its eight bytes.

Four things make it bigger than the JSON. Every string carries a four-byte length *and* a trailing null. Every number costs a full four or eight bytes, so `3.5` is eight bytes where JSON spends three characters. Every nested document repeats a length and a terminator. And arrays are the worst case: BSON has no real array, only a document whose keys are `"0"`, `"1"`, `"2"`. The two-tag list above is 45 bytes against 29 as JSON, because each element carries its index as a string key.

The keys themselves are stored in full on every document, exactly as in JSON.

---

### What BSON actually changes

The lengths are the point. Because every string, subdocument and array announces its size, a reader can find one field without looking at the others:

```python
FIXED = {0x01: 8, 0x08: 1, 0x09: 8, 0x0A: 0, 0x10: 4, 0x12: 8}


def find_field(doc: bytes, wanted: str) -> tuple[int, int]:
    """Offset of `wanted`'s value, and how many bytes were read to find it."""
    offset, touched = 4, 4                     # skip the document length
    while doc[offset] != 0x00:
        kind = doc[offset]
        key_end = doc.index(b"\x00", offset + 1)
        key = doc[offset + 1:key_end].decode()
        touched += key_end - offset + 1
        value_at = key_end + 1
        if key == wanted:
            return value_at, touched
        if kind in FIXED:
            size = FIXED[kind]
        else:                                  # string, document or array
            (length,) = struct.unpack_from("<i", doc, value_at)
            touched += 4
            size = length + 4 if kind == 0x02 else length
        offset = value_at + size
    raise KeyError(wanted)


value_at, touched = find_field(as_bson, "qc_passed")
print(as_bson[value_at], touched, len(as_bson))  # 1 129 439
print(as_json.index(b'"qc_passed":') + len(b'"qc_passed":'))  # 228
```

To reach `qc_passed`, the walker read 129 of the document's 439 bytes: type bytes, keys and length prefixes. It jumped over the `position` subdocument, two strings and five numbers without touching them. A JSON reader has to scan all 228 bytes before the value, character by character, because the only way to find where a string ends is to look for its closing quote. On this small record most of the 129 bytes are key names. On a document with a large embedded array or a long text field, the jump is where the time goes.

The same property makes in-place updates possible. A double is always eight bytes, so a new wave height can be written over the old one without moving anything after it. In JSON, `3.5` becoming `3.25` shifts every byte that follows.

The second change is types. BSON distinguishes 32-bit integers, 64-bit integers and doubles, and has a UTC datetime, a 128-bit decimal, binary data and MongoDB's 12-byte ObjectId. Each is precise about what it keeps:

```python
recorded = datetime(2026, 2, 11, 5, 15, 30, 123456,
                    tzinfo=timezone(timedelta(hours=1)))
typed = {"recorded_at": recorded, "battery_v": bson.Decimal128("13.10")}
back = bson.decode(bson.encode(typed), CodecOptions(tz_aware=True))
print(back["recorded_at"])  # 2026-02-11 04:15:30.123000+00:00
print(back["battery_v"].to_decimal() == Decimal("13.10"))  # True

try:
    bson.encode({"trace_id": 2**64})
except OverflowError as exc:
    print(f"OverflowError: {exc}")
# OverflowError: MongoDB can only handle up to 8-byte ints
```

The decimal survives exactly, which JSON cannot promise. The datetime shows what the type costs: it is milliseconds since the epoch in UTC, so the microseconds became `.123000` and the `+01:00` offset is gone. Without `tz_aware=True` you get a naive datetime back and have to know it means UTC. Integers stop at 64 bits, where JSON has no limit on paper.

---

### The measurement

50,000 records, one document each, best of five with the cyclic garbage collector paused while timing:

```
format                             bytes     gzip -9     zstd -3  encode ms  decode ms
JSON, one line per record     20,790,508   1,872,391   2,344,851      382.2      442.0
BSON, one doc per record      21,395,685   2,577,281   2,771,405      143.4      268.2
BSON, recorded_at datetime    20,295,685   2,642,678   2,839,581
MessagePack, per record       17,264,782   2,447,543   2,381,232
CBOR, per record              17,319,707   2,453,317   2,384,784
  BSON vs JSON: raw +2.9%, gzip +37.6%, zstd +18.2%
  BSON typed vs JSON: raw -2.4%, gzip +41.1%, zstd +21.1%

count failed QC across all 50,000 documents
  json.loads each line                 315.5 ms   3,947
  bson.decode each document            171.9 ms   3,947
  RawBSONDocument, one field           254.7 ms   3,947
```

Raw, BSON is 2.9% bigger. Compressed, the gap opens to 37.6% under gzip and 18.2% under zstd, for the same reason as in this series' MessagePack article: JSON's repeated text compresses almost for free, and BSON's length prefixes and eight-byte doubles look like noise to a compressor.

Using BSON's own datetime instead of an ISO string saves 22 bytes per record and makes it 2.4% *smaller* than JSON raw. Compressed, it gets worse, 41.1% bigger under gzip, because the timestamps were a predictable string pattern and are now random-looking integers.

Speed is where BSON pays its way in Python. Encoding took 143.4 ms against 382.2 and decoding 268.2 against 442.0: 2.7 times and 1.6 times faster.

The lazy reader did not help. `RawBSONDocument` promises to decode only what you touch, yet reading one field from each document was slower than decoding it whole, because the Python class decodes the document's whole top level the first time you read any key. The length prefixes pay off inside MongoDB's C++ engine, not in a Python loop.

---

### Where JSON still wins

Size, especially where it matters. On anything that crosses a network compressed, BSON is 18% to 41% more bytes. If you are choosing a binary format for the wire, MessagePack and CBOR, both in the table above, are smaller than BSON in every column.

Structure. A BSON document must be an object: `bson.encode([1, 2])` raises `TypeError`, so a top-level list has to be wrapped. MongoDB also caps a document at 16 MB. The full payload as a single document would be 21.4 MB, which is why it is stored one document per record.

Precision. Datetimes lose microseconds and offsets, and integers stop at 64 bits. JSON's strings keep all three, at the price of having to parse them yourself.

Readability and reach. You cannot read BSON in a terminal, and outside the MongoDB ecosystem few systems speak it. Every language has a JSON parser in its standard library.

---

### Conclusion

Use BSON when you are talking to MongoDB. Your driver already does, and it is the right choice there: typed values, fast encode and decode, and documents a storage engine can traverse and update in place. It is also reasonable anywhere you want MongoDB's type system in a self-describing binary envelope.

Do not use it to make payloads smaller. On this data it was 2.9% larger than JSON, 37.6% larger gzipped, and larger than MessagePack and CBOR in every column.

The cost is bytes, readability, and a type system that trims timestamps to milliseconds in UTC. BSON is binary for the database's sake, not for your bandwidth.

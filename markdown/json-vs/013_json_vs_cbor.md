# JSON vs. CBOR

#### It ties MessagePack on size and loses to `json` on encode speed in Python — you buy it for tags and for bytes you can sign

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

Last time MessagePack came out 17% smaller than JSON and 31% bigger once both were gzipped. CBOR is the obvious next question, because on the wire it looks almost the same: a type byte, a length, the value. The difference on paper is that CBOR is an IETF standard — RFC 8949, which replaced RFC 7049 in 2020 — and MessagePack never was.

So I ran the same 50,000 harbour buoy observations through `cbor2` 6.1.4 on Python 3.12. CBOR was 16.7% smaller than JSON raw and 31.0% bigger gzipped, within half a point of MessagePack on every size column. In CPython it was also *slower* to encode than the standard library's `json`.

If size and speed were the reason to pick CBOR, the article would end there. They are not. CBOR was built to carry what JSON's data model cannot — timestamps, integers past 64 bits, raw bytes, exact decimals — and to produce one byte sequence per value, which you need before you can sign anything. That is why passkeys speak it: WebAuthn attestation objects are CBOR, and COSE (RFC 9052) signs CBOR.

---

### The same record, both ways

The first record the series generator produces:

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

And the same record through both encoders:

```python
import json

import cbor2

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
as_cbor = cbor2.dumps(reading)

print(len(as_json), len(as_cbor))      # 427 358
print(as_cbor[:16].hex(" "))
# ab 6e 6f 62 73 65 72 76 61 74 69 6f 6e 5f 69 64
print(cbor2.loads(as_cbor) == reading)  # True
```

Every CBOR item starts with one byte split in two. The top three bits are the **major type**; the low five are either the value itself or how many bytes the value takes. `0xab` is `101 01011`: major type 5, a map, eleven pairs. `0x6e` is `011 01110`: major type 3, text, fourteen bytes — `observation_id`. Anything below 24 fits in the head byte; 24 to 27 mean "the length follows in 1, 2, 4 or 8 bytes".

There are eight major types. Six map onto JSON: unsigned and negative integers, text, arrays, maps, and a type for floats, booleans and null. Two have no JSON equivalent at all — **byte strings** (type 2) and **tags** (type 6). Everything interesting about CBOR lives in those two.

---

### What CBOR actually changes

A **tag** is a number wrapped around another item, telling the decoder how to read it. The registry lives at IANA, and the first few are the ones JSON users reinvent by hand:

```python
from datetime import datetime, timezone
from decimal import Decimal

tagged = {
    "recorded_at": datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc),
    "trace_id": 0x9C3E1F0A6B2D48E7A15C0F93D4B8E261,
    "battery_v": Decimal("13.10"),
    "signature": bytes(range(64)),
}

blob = cbor2.dumps(tagged, datetime_as_timestamp=True)
print(len(blob))                    # 138
print(cbor2.loads(blob) == tagged)  # True

try:
    json.dumps(tagged)
except TypeError as exc:
    print(f"TypeError: {exc}")
# TypeError: Object of type datetime is not JSON serializable
```

A datetime, a 128-bit integer, an exact decimal and 64 raw bytes go in, and the same four Python types come out. In JSON each one needs a convention both sides agree on out of band. Value by value, against the usual JSON workaround:

```
timestamp, tag 1             27 B json    6 B cbor   c1 1a 69 8c
timestamp, tag 0             27 B json   22 B cbor   c0 74 32 30
128-bit id, tag 2            41 B json   18 B cbor   c2 50 9c 3e
decimal 13.10, tag 4          7 B json    6 B cbor   c4 82 21 19
64 raw bytes, type 2         90 B json   66 B cbor   58 40 00 01
NaN, half float               5 B json    3 B cbor   f9 7e 00
```

The JSON column is an ISO string, a quoted integer, a quoted decimal, base64 and a bare `NaN` — which Python writes by default and which is not valid JSON, as this series covered in the Infinity and NaN article. The decimal matters more than its one-byte saving: JSON's `13.10` comes back as the float `13.1`, while tag 4 stores a mantissa and a base-10 exponent and returns `Decimal('13.10')`.

CBOR also has a readable text form, **diagnostic notation**, which is what you put in logs and bug reports. The tagged map above, with the 64-byte signature shortened here by hand:

```
{"recorded_at": 1(1770783300),
 "trace_id": 2(h'9C3E1F0A6B2D48E7A15C0F93D4B8E261'),
 "battery_v": 4([-2, 1310]),
 "signature": h'000102…3E3F'}
```

One trap in that first line: tag 1 is seconds since the epoch, so it keeps the instant and drops the offset. `05:15+01:00` went in and `04:15+00:00` came back. Tag 0 keeps the offset, at 22 bytes instead of 6.

Tags are also how CBOR grows without a version bump. A decoder that has never heard of a tag still returns the value and re-encodes it unchanged:

```python
future = cbor2.loads(cbor2.dumps(cbor2.CBORTag(40001, "HB-214")))
print(repr(future))                # CBORTag(40001, 'HB-214')
print(cbor2.dumps(future).hex(" "))
# d9 9c 41 66 48 42 2d 32 31 34
```

The second thing CBOR adds is **deterministic encoding**. Two equal documents can serialize to different bytes, and once you hash or sign the bytes, that difference is a verification failure:

```python
import hashlib

from_device = {"buoy_id": "NE-08", "wave_height_m": 3.5}
from_archive = {"wave_height_m": 3.5, "buoy_id": "NE-08"}


def fingerprint(blob: bytes) -> str:
    """First twelve hex digits of the SHA-256."""
    return hashlib.sha256(blob).hexdigest()[:12]


print(from_device == from_archive)  # True
print(fingerprint(cbor2.dumps(from_device)),
      fingerprint(cbor2.dumps(from_archive)))
# 344d1563c423 9fd1ce75446d
print(fingerprint(cbor2.dumps(from_device, canonical=True)),
      fingerprint(cbor2.dumps(from_archive, canonical=True)))
# f26065666bc1 f26065666bc1

print(cbor2.dumps(3.5).hex(" "))                  # fb 40 0c 00 00 00 00 00 00
print(cbor2.dumps(3.5, canonical=True).hex(" "))  # f9 43 00
```

Key order is the obvious half, and `json.dumps(sort_keys=True)` fixes it too — shuffling every key in all 50,000 records gave identical hashes under both `sort_keys=True` and `canonical=True`. The less obvious half is numbers. Python writes `12.0` where JavaScript's `JSON.stringify` writes `12`, and JSON has no rule for which is right. CBOR does: deterministic encoding uses the shortest float that holds the value exactly, so `3.5` is a three-byte half-precision float, not a nine-byte double. A C encoder on the buoy and a Python service can produce the same bytes because the rule is in the RFC, not in a library's defaults.

---

### Size and speed, measured

Full payload, 50,000 records, best of five runs, `cbor2` 6.1.4 and `msgpack` 1.1.0:

```
format                 bytes     gzip -9     zstd -3   encode ms   decode ms
JSON              20,790,509   1,872,392   2,344,331       239.3       319.8
MessagePack       17,264,785   2,447,545   2,381,288        93.8       236.2
CBOR              17,319,710   2,453,313   2,384,765       305.6       316.5
CBOR canonical    17,174,360   2,427,983   2,422,789       786.5       355.8
CBOR stringref     9,742,111   2,258,212   2,181,867       717.9       289.7

change against JSON (negative = bigger)
format                 raw   gzip -9   zstd -3
MessagePack          17.0%    -30.7%     -1.6%
CBOR                 16.7%    -31.0%     -1.7%
CBOR canonical       17.4%    -29.7%     -3.3%
CBOR stringref       53.1%    -20.6%      6.9%
```

Plain CBOR and MessagePack agree to within 0.3 points on every size column, for the same reason: JSON's repeated keys are what a compressor removes cheaply, and binary doubles look like noise to it.

Canonical mode saved exactly 145,350 bytes. The lab counted the floats: 24,225 of 300,000 — 8.1%, values like `3.5` and `12.0` — fit in half precision, at six bytes saved each. Sorting every map is what that costs: encoding took 786.5 ms against 305.6, 2.6 times slower.

**String references** are the one mode with a real size story. Tag 256 marks a scope and tag 25 points back to a string already sent, so each repeated key and status is written once and then referenced. Raw size drops 53.1%. Gzipped JSON is still 20.6% smaller; against zstd JSON, stringref finally wins, by 6.9%. That is the only CBOR row here that beats compressed JSON on anything, and it only works if the decoder on the other side implements both tags.

Then speed. `cbor2` encoded slower than `json` — 305.6 ms against 239.3 — and decoded in the same time. MessagePack encoded the same payload in 93.8 ms. In Python, speed is not a reason to pick CBOR.

---

### Where JSON still wins

You cannot read it, and diagnostic notation needs a tool to produce. Every `curl`, log grep and pasted payload goes through a decoder first. Browsers parse JSON natively; CBOR in a browser is a JavaScript library.

Tags only help when both ends implement them. A decoder without tag 4 support hands you a tag object instead of a decimal, and a stringref payload is unreadable to a decoder that lacks tags 256 and 25. JSON's lowest common denominator is higher.

And "deterministic" needs a citation. `cbor2`'s `canonical=True` sorts keys shortest-first, the RFC 7049 rule. RFC 8949 sorts them bytewise on their encoding. For text keys — every key in this payload — the two agree. Mix key types and they do not:

```
map with an int key and a text key
  cbor2 canonical=True   a2 61 61 02 19 03 e8 01   (RFC 7049: shorter key first)
  RFC 8949 core det.     a2 19 03 e8 01 61 61 02   (bytewise: 0x19 < 0x61)
```

Two libraries that each call themselves canonical can sign different bytes for the same map.

---

### Conclusion

Pick CBOR when the data model is the point: timestamps, big integers, exact decimals and raw bytes that must come back as themselves, a signature over the encoding, or a protocol like WebAuthn or COSE that already speaks it. Those are things JSON cannot express without a side agreement, and they are where CBOR earns its keep.

Do not pick it for size or speed. On this payload it matched MessagePack to within half a point, lost to gzipped JSON by 31%, and encoded slower than `json` in CPython.

The cost is readability, a dependency on both ends, tag support you must confirm rather than assume, and a determinism rule you have to name explicitly. Write down which one.

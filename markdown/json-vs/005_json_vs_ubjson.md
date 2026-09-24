# JSON vs. UBJSON

#### Universal Binary JSON keeps JSON's data model exactly. That buys 6.3% raw, costs 31% after gzip, and its one bigger saving rounds 92% of your floats

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

Most binary JSON formats add things. BSON adds dates and ObjectIds, MessagePack adds extension types, CBOR adds tags. UBJSON, Universal Binary JSON, promises the opposite: its site lists "absolute compatibility with the JSON spec" as a goal, and it uses only types every popular language already has. Anything you can write in JSON converts to UBJSON and back without loss, and nothing converts that JSON could not already hold.

That promise is the reason to look at UBJSON, and it is also why it loses. I encoded the series' 50,000 harbour buoy observations with `py-ubjson` 0.16.1, which has a C extension. UBJSON came out 6.3% smaller than JSON raw and 31.1% bigger gzipped, and MessagePack beat it on every column. Its one option that closes the gap does so by changing 275,775 of the payload's 300,000 floats.

---

### The same record, both ways

```python
import json
import math
import struct

import ubjson

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
as_ubjson = ubjson.dumpb(reading)

print(len(as_json), len(as_ubjson))  # 427 401
print(as_ubjson[:40])
# b'{U\x0eobservation_idL\x00 \x00\x00\x00\x00\x00\x01U\x07buoy_idSU\x05NE'
print(ubjson.loadb(as_ubjson) == reading)  # True
```

UBJSON's type markers are printable ASCII, which makes it the one binary format here you can half-read in a hex dump. `{` opens an object, as in JSON. `U\x0e` is a key length, written as an unsigned byte, then 14 bytes of `observation_id`, with no quotes. `L` means a 64-bit integer follows. `S` marks a string, which again carries its own `U` length. Further on you would meet `D` for a double, `T` and `F` for booleans, `Z` for null, and `[` and `]` around arrays.

Where JSON writes a delimiter, UBJSON writes a type or a length, and the bytes of every key and string are the same in both. That is why the saving is small: 26 bytes on this record, 6%.

---

### What UBJSON actually changes

Numbers get real types. Integers are written as `i`, `U`, `I`, `l` or `L` (8, 8 unsigned, 16, 32 or 64 bits), whichever is smallest. Floats are `d` or `D` (32 or 64 bits). Anything larger becomes `H`, a **high-precision number** stored as its decimal digits:

```python
print(ubjson.dumpb(math.nan), ubjson.loadb(ubjson.dumpb(math.inf)))
# b'Z' None
print(ubjson.dumpb(2**64))
# b'HU\x1418446744073709551616'
```

A bignum is kept exactly, as text. `py-ubjson` writes `NaN` and `Infinity` as `Z`, null. That is faithful to JSON's data model, which has neither, and it means UBJSON will not carry them for you either.

The feature that should make UBJSON compact is the **optimized container**. An array can declare its element type once with `$` and its length with `#`, then drop the per-element markers. For a numeric array, that is the whole point:

```python
spectrum = [round(0.01 * band * math.exp(-band / 12), 4) for band in range(64)]

generic = ubjson.dumpb(spectrum)
typed = b"[$D#U" + bytes([len(spectrum)]) + struct.pack(">64d", *spectrum)
text = json.dumps(spectrum, separators=(",", ":")).encode()

print(len(text), len(generic), len(typed))  # 434 574 518
print(ubjson.loadb(typed) == spectrum)      # True
```

A 64-band wave spectrum as a typed array is 518 bytes against 574 for the generic form. But `py-ubjson` never writes the typed form for a list: I had to build those bytes by hand, and the library only reads them. It writes typed arrays for `bytes` values alone. And the JSON is still smallest at 434, because four-decimal values are shorter as text than as eight-byte doubles.

The encoder does have one option that makes the whole payload much smaller, and it is off by default for a reason:

```python
smaller = ubjson.dumpb(reading, no_float32=False)
print(len(smaller), ubjson.loadb(smaller)["battery_v"])  # 377 13.119999885559082
```

With `no_float32=False`, every float within single-precision *range* is written as a 32-bit float, whether or not the value fits exactly. `13.12` comes back as `13.119999885559082`. The library's docstring warns that this saves space "at the loss of precision". The loss applies to every float the encoder writes.

---

### The measurement

50,000 records encoded as one array, best of five, garbage collector paused while timing:

```
format                  bytes     gzip -9     zstd -3  encode ms  decode ms  round-trips
JSON               20,790,509   1,872,392   2,344,331      238.7      270.6  True
UBJSON             19,473,955   2,454,353   2,418,558      249.9      248.8  True
UBJSON, counts     20,073,842   2,516,449   2,477,044      241.0      242.6  True
UBJSON, float32    18,274,267   2,085,731   2,269,700      243.4      254.2  False
MessagePack        17,264,785   2,447,545   2,381,288       98.4      195.0  True
CBOR               17,319,710   2,453,313   2,384,765      297.3      292.3  True

change against JSON (negative = bigger)
  UBJSON           raw    6.3%   gzip  -31.1%   zstd   -3.2%
  UBJSON, counts   raw    3.4%   gzip  -34.4%   zstd   -5.7%
  UBJSON, float32  raw   12.1%   gzip  -11.4%   zstd    3.2%

no_float32=False: 275,775 of 300,000 floats came back different
  worst latitude error 1.91e-06 degrees = 21.2 cm
```

Plain UBJSON saves 6.3% raw, less than half of MessagePack's 17.0%. The reason is in the headers. A short string costs UBJSON three bytes of overhead (`S`, `U`, length) against MessagePack's one. An integer below 128 costs UBJSON two bytes, where MessagePack packs it into one. Under gzip the familiar reversal follows: 31.1% bigger than compressed JSON, and slightly worse than MessagePack's 30.7%.

Writing container counts made it *bigger*, by 2.9 points. Each object gains a `#` and a length and loses only its closing brace.

The float32 row is the only UBJSON configuration that beats zstd-compressed JSON, by 3.2%. It gets there by changing 91.9% of the floats. The 24,225 that survived are the values a 32-bit float holds exactly, such as `3.5` and `12.0`. The rest moved. The worst latitude moved by 21.2 cm, which a position log may tolerate. The `round-trips` column says `False`, which is harder to tolerate.

Speed is a wash. `py-ubjson` encoded in 249.9 ms against JSON's 238.7 and decoded in 248.8 against 270.6. MessagePack did both faster than either.

---

### Where JSON still wins

Almost everywhere. Gzipped, UBJSON is 31% bigger than JSON. In Python it is no faster than the standard library. It is unreadable without a tool, even if the markers are friendlier than most.

It also loses its own category. Among binary formats that keep to JSON's data model, MessagePack is smaller, faster in Python, and far more widely implemented. `py-ubjson` has not had a release since April 2020, and a format is only as usable as its libraries.

What UBJSON does have is simplicity. The type system is JSON's plus sized numbers, the markers are ASCII, and a decoder fits on a page. Conversion in either direction is lossless because there is nothing to lose. For a float-heavy payload and a toolchain that writes typed arrays, the optimized containers are a real saving that MessagePack does not offer.

---

### Conclusion

Choose UBJSON only when its exact match with JSON's data model is the requirement: an embedded system that wants a trivial decoder, or a pipeline that must convert to and from JSON without edge cases. If your encoder writes typed arrays for numeric data, you get a saving the others do not offer.

Choose JSON with compression when you want small payloads, and MessagePack when you want binary. On this dataset UBJSON was 6.3% smaller raw, 31.1% bigger gzipped, and no faster.

The cost is size after compression, speed parity rather than a gain, and an ecosystem that has gone quiet. The one switch that looks like a fix, `no_float32=False`, pays for its 12% by rounding 92% of your floats.

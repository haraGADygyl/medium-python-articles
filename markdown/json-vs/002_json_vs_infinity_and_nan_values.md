# JSON vs. Infinity and NaN Values

#### One NaN in 50,000 records: Python writes it without complaint, and Node, PHP and PostgreSQL refuse the whole file

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

Every float your code handles can be one of three values JSON has no way to write: `NaN`, `Infinity` and `-Infinity`. They are ordinary IEEE 754 doubles. A sensor that drops out reports `NaN`, and a division by zero or a counter overflow produces `Infinity`. RFC 8259 says plainly that numbers which cannot be written in its grammar, "such as Infinity and NaN", are not permitted.

Python's `json` module writes them anyway, by default, as bare `NaN` and `Infinity`. What happens next depends entirely on who reads the file.

I took the series' 50,000 harbour buoy observations, set the wave height of one record to `NaN` — record 31,337, as if its sensor had dropped out — and handed the file to five consumers: Python, Node, jq, PHP and PostgreSQL. Two of them read all 50,000 records and got a `NaN` mean wave height, one of them printing it as `null`. The other three read zero records.

---

### The same document, both ways

Here is that record as Python sees it, with the anemometer overflowing as well so both kinds of non-finite value appear:

```python
import json
import math

reading = {
    "observation_id": 9007199254772330,
    "buoy_id": "NE-07",
    "wave_height_m": math.nan,          # the sensor dropped out
    "wind_gust_ms": math.inf,           # the anemometer overflowed
    "qc_passed": True,
}

print(json.dumps(reading))
# {"observation_id": 9007199254772330, "buoy_id": "NE-07",
#  "wave_height_m": NaN, "wind_gust_ms": Infinity, "qc_passed": true}

try:
    json.dumps(reading, allow_nan=False)
except ValueError as exc:
    print(f"ValueError: {exc}")
# ValueError: Out of range float values are not JSON compliant: nan
```

The first output is not JSON. It is JavaScript object-literal syntax, and Python emits it because `allow_nan` defaults to `True`. The second call is the same encoder with the default flipped, and it stops at the first `NaN` instead of writing a file other readers will reject.

Now the same text, `{"wave_height_m":NaN,"wind_gust_ms":Infinity,"battery_v":-Infinity}`, given to each reader:

```
Python json.loads       {'wave_height_m': nan, 'wind_gust_ms': inf, 'battery_v': -inf}
Node JSON.parse         SyntaxError: Unexpected token 'N', ..."height_m":NaN,"wind_"...
jq 1.7                  {"wave_height_m":null,"wind_gust_ms":1.7976931348623157e+308,
                         "battery_v":-1.7976931348623157e+308}
PHP json_decode         NULL / Syntax error
PostgreSQL ::jsonb      ERROR:  invalid input syntax for type json
```

One document, three behaviours. Python accepts it. Node, PHP and PostgreSQL follow the RFC and refuse it. jq 1.7 accepts it, then prints `NaN` as `null` and `Infinity` as the largest finite double — values that look valid and are not what was sent.

---

### What non-finite values actually change

Going the other way is worse, because every writer that does not refuse picks a different stand-in:

```
Python json.dumps       [NaN, Infinity, -Infinity]
Node JSON.stringify     [null,null,null]
jq 1.7                  [null,1.7976931348623157e+308,-1.7976931348623157e+308]
PHP json_encode         false / Inf and NaN cannot be JSON encoded
PHP, PARTIAL_OUTPUT     [0,0,0]
PostgreSQL to_jsonb     ["NaN", "Infinity", "-Infinity"]
```

Node's `null` is valid JSON but cannot be told apart from a field that was never measured. PHP refuses by default; with `JSON_PARTIAL_OUTPUT_ON_ERROR`, a flag people add to make the error go away, it writes `0` — a calm sea, reported with confidence by a broken sensor. PostgreSQL does something sensible: it writes the strings `"NaN"` and `"Infinity"`, the same spelling Protocol Buffers uses in its JSON mapping.

The values do not even have to start non-finite. `1e400` is a valid JSON number, and it does not fit in a double:

```python
def refuse_constant(token: str) -> float:
    """Reject NaN, Infinity and -Infinity instead of inventing floats."""
    raise ValueError(f"{token} is not a JSON number")


incoming = '{"buoy_id": "NE-07", "wave_height_m": NaN}'
try:
    json.loads(incoming, parse_constant=refuse_constant)
except ValueError as exc:
    print(f"ValueError: {exc}")
# ValueError: NaN is not a JSON number

print(json.loads("1e400"))              # inf
print(json.dumps(json.loads("1e400")))  # Infinity
```

`parse_constant` is how you make Python's reader as strict as everyone else's: it is called for exactly the three literals, and raising from it rejects the document. But it does not fire for `1e400`, which parses as a legal number and becomes `inf` on the way in. Write it back out and Python emits `Infinity`. A valid document went through one read and one write and came out invalid. Node turns the same value into `null`, and PHP's `json_encode` returns `false`.

---

### One NaN in 50,000 records

The whole payload, 20.8 MB, with one `NaN` at record 31,337. The correct answer is 49,999 valid readings with a mean wave height of 3.857750:

```
consumer                      records   mean wave height
Python json.load               50,000   nan
Node JSON.parse                     0   SyntaxError: Unexpected token 'N', ..."height_m":NaN,...
jq 1.7                         50,000   null  (holds 1 NaN internally, prints it as null)
PHP json_decode                     0   Syntax error
PostgreSQL COPY ... jsonb           0   ERROR:  invalid input syntax for type json
```

Not one consumer produced the right number.

The three strict readers lost everything. One sensor fault out of 50,000 readings made a 20.8 MB file unreadable in Node and PHP, and made the PostgreSQL `COPY` abort, loading none of its 50,000 lines.

The file shape made it worse. A JSON array is a single value, so one bad token invalidates all of it. Written as JSON Lines, the first article in this series, the same fault costs Node one line: the lab's per-line reader kept 49,999 records and skipped line 31,338. `COPY` still aborts, because it runs as a single transaction, but a line-by-line loader can skip the bad line and keep going.

The two permissive readers lost the answer. Python loaded every record and `statistics.fmean` returned `nan`, because one `NaN` poisons any sum it touches. jq did the same internally and then printed the result as `null`, so the dashboard shows an empty average rather than an error.

That split is the real shape of the problem. A strict reader fails loudly and far from the cause. A permissive reader gets a value nobody checked for and quietly passes it on.

---

### Where JSON's refusal is right

It is tempting to call JSON's missing `NaN` a gap. It is closer to a feature. `NaN` is not equal to itself, so it breaks equality checks, deduplication, sorting and set membership. And it says nothing about *why* the value is missing. A dropout, an overflow and a reading outside the sensor's range all become the same three letters.

JSON forces you to write that meaning down. The most useful version is `null` plus a reason:

```python
def with_faults(record: dict) -> dict:
    """Replace each non-finite float with null and say why in `faults`."""
    clean, faults = {}, {}
    for key, value in record.items():
        if isinstance(value, float) and not math.isfinite(value):
            clean[key] = None
            faults[key] = "dropout" if math.isnan(value) else "overflow"
        else:
            clean[key] = value
    return {**clean, "faults": faults} if faults else clean


print(json.dumps(with_faults(reading), allow_nan=False))
# {..., "wave_height_m": null, "wind_gust_ms": null, "qc_passed": true,
#  "faults": {"wave_height_m": "dropout", "wind_gust_ms": "overflow"}}
```

Every reader in the table parses that, and every average that skips `null` comes out right. When the float itself has to survive — a numerical pipeline where `inf` is meaningful — spell it the way PostgreSQL and Protocol Buffers do, and convert it back only in fields you know are numbers:

```python
SENTINELS = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}
FLOAT_FIELDS = {"wave_height_m", "wind_gust_ms"}


def encode_special(value: object) -> object:
    """Spell non-finite floats as the strings Protobuf and Postgres use."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else (
            "Infinity" if value > 0 else "-Infinity")
    return value


def decode_special(obj: dict) -> dict:
    """object_hook: turn the sentinels back into floats, in float fields only."""
    for key in FLOAT_FIELDS & obj.keys():
        if obj[key] in SENTINELS:
            obj[key] = SENTINELS[obj[key]]
    return obj


wire = json.dumps({k: encode_special(v) for k, v in reading.items()},
                  allow_nan=False)
back = json.loads(wire, object_hook=decode_special)
print(back["wave_height_m"], back["wind_gust_ms"])  # nan inf
```

The field list matters. Without it, a buoy note that literally reads `"NaN"` would turn into a float.

If you need non-finite values natively, the binary formats have them. MessagePack and CBOR both carry IEEE 754 specials as ordinary floats, CBOR in three bytes, and JSON5 accepts `NaN` and `Infinity` as literals. The cost is the same everywhere: every reader downstream now has to handle a value that is not equal to itself.

---

### Conclusion

Set `allow_nan=False` on every `json.dumps` that leaves your process, and pass `parse_constant` to every `json.loads` that reads input you do not control. Those two arguments turn Python from the most permissive reader in the table into one that agrees with Node, PHP and PostgreSQL. The file then fails where the `NaN` was created, not three services downstream.

Then decide what a missing reading means and write that down: `null` with a reason for most data, string sentinels when the float has to survive. Remember that `1e400` becomes `Infinity` without any help from you.

JSON's refusal to encode `NaN` costs you a decision you would rather not make. The alternative, on this payload, was zero records or a `nan` average. The decision is cheaper.

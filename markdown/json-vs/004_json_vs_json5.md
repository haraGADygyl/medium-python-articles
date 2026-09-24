# JSON vs. JSON5

#### Comments, trailing commas and hex for the files people write by hand — and 5 comments become 0 the first time code saves one

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

JSON has no comments on purpose. Douglas Crockford has said he removed them because people were using them to carry parsing directives, which broke interoperability. For data exchanged between programs that was the right call. For a config file a person maintains, it means the one line explaining *why* the poll interval is 600 seconds has nowhere to go.

JSON5 puts it back. It is a superset of JSON that borrows ECMAScript 5 syntax: comments, trailing commas, unquoted keys, single quotes, hexadecimal numbers, `Infinity` and `NaN`, and strings that continue across lines. Every JSON document is valid JSON5; the reverse is rarely true.

I wrote one realistic config for the series' buoy fleet in JSON5 and tried it on seven parsers. I then changed one value through code and parsed the series' 20.8 MB payload with each JSON5 library. Three parsers read the config. Every round trip deleted all five comments, and the slowest parser took 844 times as long as `json.loads`.

---

### The same config, both ways

The ingest settings for the north-east buoys, as JSON5. Save it as `fleet.json5`:

```javascript
// Ingest settings for the north-east harbour buoys.
{
  fleet: 'north-east',
  buoys: ['NE-07', 'NE-08'],  // HB-214 and HB-215 moved to the south fleet
  poll_interval_s: 600,       // matches the modem's ten-minute wake cycle
  wave_alarm_m: 5.5,
  battery_floor_v: 11.8,
  sensor_mask: 0x0F,          // accelerometer | thermistor | anemometer | gps
  max_gust_ms: Infinity,      // no cap until the new anemometers arrive
  drift_tolerance_deg: .002,
  maintenance_note: 'Recalibrate the thermistors \
after the winter swap.',
  retry: {
    attempts: 3,
    backoff_s: [5, 30, 120,],
  },
}
```

And the same settings as the JSON a strict parser will accept:

```json
{
  "fleet": "north-east",
  "buoys": ["NE-07", "NE-08"],
  "poll_interval_s": 600,
  "wave_alarm_m": 5.5,
  "battery_floor_v": 11.8,
  "sensor_mask": 15,
  "max_gust_ms": null,
  "drift_tolerance_deg": 0.002,
  "maintenance_note": "Recalibrate the thermistors after the winter swap.",
  "retry": {"attempts": 3, "backoff_s": [5, 30, 120]}
}
```

The JSON version is fine for a program and poor for a person. All five comments are gone, and with them the reason behind four of the values. `0x0F` has become `15`, which is the same number but no longer reads as four bits for four sensors. `Infinity` has no JSON spelling, so "no cap" turns into `null` and a convention both sides must remember. None of those losses changes the data. All of them make the file harder for the next person to edit.

---

### What JSON5 actually changes

In Python, the standard library refuses the file on its first byte, and a JSON5 library reads it:

```python
import json
from pathlib import Path

import json5

text = Path("fleet.json5").read_text()

try:
    json.loads(text)
except json.JSONDecodeError as exc:
    print(f"JSONDecodeError: {exc}")
# JSONDecodeError: Expecting value: line 1 column 1 (char 0)

config = json5.loads(text)
print(config["sensor_mask"], config["max_gust_ms"])  # 15 inf
print(config["maintenance_note"])
# Recalibrate the thermistors after the winter swap.
```

The hex mask arrives as `15`, `Infinity` as a real float, and the backslash-continued string as one line. Outside Python the picture is the same: JSON5 needs a JSON5 parser, and nothing else will do. Here is the same file on seven parsers:

```
Python json.loads         JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Python json5 0.15.0       mask=15 gust=inf drift=0.002 note='Recalibrate the ...'
Python pyjson5 2.0.1      mask=15 gust=inf drift=0.002 note='Recalibrate the ...'
Node JSON.parse           SyntaxError: Unexpected token '/', "// Ingest "... is not valid JSON
npm json5 2.2.3           mask=15 gust=inf drift=0.002 note='Recalibrate the ...'
npm jsonc-parser 3.3.1    57 errors, first: InvalidSymbol at offset 57
jq-1.7                    jq: parse error: Invalid numeric literal at line 1, column 3

3 of 7 parsers read it; they agree: True
```

The three JSON5 parsers produce identical values, which is what a real spec buys you over an ad-hoc "relaxed JSON". The row worth a second look is `jsonc-parser`, the parser behind VS Code's `settings.json` and the "JSON with comments" that `tsconfig.json` uses. JSONC allows comments and trailing commas and nothing else. The unquoted keys, single quotes and hex literal in this file produced 57 errors. "JSON with comments" is not one format: pick JSON5 and your file works only with JSON5 tools.

---

### What a round trip does to it

Config files do not stay hand-edited. A deploy script bumps a value, a settings UI saves a preference, a migration renames a key. Here is `poll_interval_s` changed from 600 to 900 through each library, then written back:

```python
config["poll_interval_s"] = 900
written = json5.dumps(config, indent=2, quote_keys=False,
                      trailing_commas=True)
print(written.count("//"), len(written.splitlines()))  # 0 22
print(written.splitlines()[9:11])
# ['  sensor_mask: 15,', '  max_gust_ms: Infinity,']
```

All five comments were gone, and the lab found the same with `pyjson5` and npm's `json5.stringify`. That is not a bug in any of them. Parsing produces a dictionary, and a dictionary has nowhere to keep a comment. The mask stayed `15`, `.002` became `0.002`, and the continued note became one long line. `pyjson5.dumps` goes further and writes one compact line that looks like JSON and still contains `Infinity`. Python's `json.loads` will take that line, and Node's `JSON.parse` rejects it — the same split this series found with Infinity and NaN values.

The same applies to the speed of the parsers themselves. Every JSON document is valid JSON5, so each parser can read the payload too:

```
parser                           ms  vs json.loads  runs
Python json.loads             345.7           1.0x  best of 5
Python pyjson5 2.0.1          386.8           1.1x  best of 5
Python json5 0.15.0        291759.4         843.9x  best of 1
Node JSON.parse               111.0           0.3x  best of 5
npm json5 2.2.3              3095.0           9.0x  best of 1
```

For a 600-byte config none of this matters. For data it does. The pure-Python `json5` package, the one that turns up first in a search, took almost five minutes on 20.8 MB, 844 times slower than `json.loads`. `pyjson5`, a compiled implementation, came within 12% of the standard library. In Node, the reference `json5` package was 28 times slower than the built-in `JSON.parse`.

---

### Where JSON still wins

Everywhere a program is on the other end. APIs, message queues, logs and data files are read by code, and code does not need comments. It does need every language, every tool and every `jq` pipeline to agree, and on this config four of seven parsers refused the file outright.

In any file a machine writes. If your config is edited through code even occasionally, its comments survive only until the first save. At that point you have JSON5's cost, a dependency and a parser nobody else has, with none of its benefit.

When speed matters. A compiled JSON5 parser is close to `json.loads`, but the pure-Python one is not, and nothing in the import line tells you which one you have.

There is a middle path worth knowing. Keep the JSON5 file as the source a person edits, and have the build or deploy step convert it to plain JSON for everything downstream. People get their comments. Programs get a format every parser reads, and no tool ever rewrites the file with the comments in it. If you only need comments, and your tooling already speaks JSONC, stay inside that smaller dialect: comments and trailing commas, nothing else. If you need more than that, TOML and YAML were designed for hand-written configuration from the start, and both come later in this series.

---

### Conclusion

Use JSON5 for configuration that people write and read: build settings, fleet configs, local tool settings, anything where the reason behind a value belongs next to the value. Comments, trailing commas that keep diffs to one line, and hex masks that read as masks are real improvements, and three independent parsers read this config identically.

Use JSON for everything a program produces or consumes. Keep JSON5 away from files that code rewrites, because the comments are the first thing to go.

The cost is interoperability. A JSON5 file is readable only by JSON5 parsers, not by JSONC tools, not by `jq`, not by the standard library, and `json5` is not a fast library. Pay that cost for files people edit by hand, and nowhere else.

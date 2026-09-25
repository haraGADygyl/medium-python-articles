# JSON vs. CSON

#### CoffeeScript Object Notation made config files pleasant to write, but its spec is a programming language, so no two parsers read the same file

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

CSON is what JSON looks like if you delete everything a person finds tedious. There are no braces, since indentation does the nesting. There are no commas at line ends and no quotes on keys, and it has `#` comments and triple-quoted strings that span lines. It is CoffeeScript's object literal syntax used as a file format, and for a while it was the config language of the Atom editor: keymaps, menus, snippets and package settings were all `.cson` files.

Atom was archived by GitHub in December 2022, and CoffeeScript is no longer where JavaScript development happens. CSON remains in the repositories that used it, and it is a useful lesson about what a format needs besides pleasant syntax.

I wrote a thirteen-line export config for the series' buoy fleet in CSON. Two of the three parsers I tried read it; the Python one did not. On five one-line features, the three parsers gave three different sets of answers. On data, the Python parser was 4,975 times slower than `json.loads`.

---

### The same config, both ways

The export settings as CSON, saved as `fleet.cson`:

```coffeescript
# Export settings for the north-east harbour buoys.
fleet: 'north-east'
share_with: ['GB', 'NO', 'DK']   # met offices that receive the feed
poll_interval_s: 10 * 60         # the modem's ten-minute wake cycle
sensor_mask: 0x0F                # accelerometer | thermistor | anemometer | gps
compress: yes
retry:
  attempts: 3
  backoff_s: [5, 30, 120]
maintenance_note: '''
  Recalibrate the thermistors
  after the winter swap.
'''
```

And as JSON:

```json
{
  "fleet": "north-east",
  "share_with": ["GB", "NO", "DK"],
  "poll_interval_s": 600,
  "sensor_mask": 15,
  "compress": true,
  "retry": {"attempts": 3, "backoff_s": [5, 30, 120]},
  "maintenance_note": "Recalibrate the thermistors\nafter the winter swap."
}
```

The CSON version is the easier one to maintain. The comments say why the interval is ten minutes and what the mask bits mean. `10 * 60` states the intent where `600` states only the result. The note reads as two lines instead of one with an escaped newline. Unlike YAML, CSON makes you quote strings, so `'NO'` stays a country code.

But `10 * 60` is not data. It is an expression. The spec for CSON is, in effect, "whatever CoffeeScript accepts as an object literal", and every parser has to decide how much of a programming language to implement.

---

### What CSON actually changes

npm's `cson-parser` reads that file into the JSON above. Python's `cson` package, the one `pip install cson` gives you, does not:

```python
import json
from pathlib import Path

import cson

text = Path("fleet.cson").read_text()

try:
    cson.loads(text)
except Exception as exc:          # the parser raises speg.ParseError
    print(f"{type(exc).__name__}: {exc.args[0]}")
# ParseError: expected None, found '* 60'

portable = (text.replace("10 * 60", "600")
                .replace("compress: yes", "compress: true"))
config = cson.loads(portable)

print(config["poll_interval_s"], config["compress"], config["sensor_mask"])
# 600 True 15
print(json.dumps(config["maintenance_note"]))
# "Recalibrate the thermistors\nafter the winter swap."
```

Once the arithmetic and `yes` are removed, the Python parser agrees on everything else: comments, hex, nesting by indentation, the triple-quoted string. The disagreement is exactly in the places where CSON stops being notation and starts being CoffeeScript. Here are five one-line features, each tried on `cson-parser`, Python's `cson` and CoffeeScript's own `eval`:

```
compress: yes
  npm cson-parser 4.0.9    {"compress": true}
  Python cson 0.8          ParseError: ("expected ':', found ''", 13, 1, 14)
  CoffeeScript 2.7.0 eval  {"compress": true}
poll_interval_s: 10 * 60
  npm cson-parser 4.0.9    {"poll_interval_s": 600}
  Python cson 0.8          ParseError: ("expected None, found '* 60'", ...)
  CoffeeScript 2.7.0 eval  {"poll_interval_s": 600}
label: "NE-#{7 + 1}"
  npm cson-parser 4.0.9    SyntaxError: ... Unexpected StringWithInterpolations
  Python cson 0.8          {"label": "NE-#{7 + 1}"}
  CoffeeScript 2.7.0 eval  {"label": "NE-8"}
max_gust_ms: Infinity
  npm cson-parser 4.0.9    SyntaxError: ... Unexpected InfinityLiteral
  Python cson 0.8          ParseError: ("expected ':', found ''", 21, 1, 22)
  CoffeeScript 2.7.0 eval  {"max_gust_ms": "<Infinity>"}
limit: Math.max(25, 40)
  npm cson-parser 4.0.9    SyntaxError: ... Unexpected Call
  Python cson 0.8          ParseError: ("expected ':', found '.max'", 11, 1, 12)
  CoffeeScript 2.7.0 eval  {"limit": 40}
```

The string interpolation line gets three different answers. `cson-parser` rejects it, Python keeps the literal text `NE-#{7 + 1}`, and CoffeeScript produces `NE-8`. A config that reads fine in the tool that wrote it can mean something else in the service that reads it.

The last line shows what separates a parser from an evaluator. `cson-parser` walks CoffeeScript's syntax tree and permits only literals, plus arithmetic on them. It refuses function calls. `eval` calls `Math.max` because the file told it to, and it would call anything else just as readily. The npm `cson` package, which wraps `cson-parser`, keeps a `parseCSString` method that goes through `eval`, and a `coffeescript` option that is off by default. Reading a CSON file you did not write by any path that evaluates it means running someone else's code.

---

### The measurement

JSON is valid CSON, so every parser can read the series' payload. I used 5,000 records rather than 50,000, because the Python parser needs more than two minutes for 5,000:

```
5000 records, 2,075,743 bytes of JSON read as CSON
parser                             ms  vs native  runs
Python json.loads                28.9         1x     5
Python cson 0.8              143999.5      4975x     1
Node JSON.parse                  13.9         1x     5
npm cson-parser 4.0.9          2649.8       191x     3
CoffeeScript 2.7.0 eval        5983.8       431x     3
```

The Python parser took 144 seconds for 2 MB, about 4,975 times as long as `json.loads`. It returned the right data, slowly. `cson-parser` was 191 times slower than `JSON.parse`, because it runs the full CoffeeScript lexer and parser before walking the tree. That is irrelevant for a config file and disqualifying for anything else.

The ecosystem numbers matter just as much. `cson-parser` 4.0.9 was published in March 2021 and Python's `cson` 0.8 in January 2019; neither has had a release since. The editor that made the format popular has been archived since 2022.

---

### Where JSON still wins

For anything that is not a hand-edited config, JSON wins without argument. Parsing was 191 to 4,975 times slower, and a CSON payload is readable by a handful of libraries.

It also wins on having a specification. RFC 8259 defines JSON in a few pages, and parsers agree on every document except edge cases this series has already measured. CSON is defined by a language grammar, so each implementation picks its own subset: `yes`, arithmetic and interpolation were each treated differently by at least two parsers.

And it wins on safety by default. No JSON parser evaluates its input. With CSON, safety depends on which function you call. A `.json` file from a stranger is always data; a `.cson` file from a stranger is data only if you picked the right function.

What CSON got right was worth having: comments, triple-quoted strings, indentation instead of brackets, and constant expressions that show intent. JSON5, YAML and TOML each keep part of that list with a real spec and maintained parsers.

---

### Conclusion

If you have CSON files, read them with `cson-parser` or the npm `cson` package's default `parse`, never with an evaluating path. Keep them to the subset every parser accepts: no arithmetic, no `yes`, no interpolation. Better still, migrate them. The npm `cson` package ships a converter that goes through `cson-parser`, not `eval`:

```bash
npm install cson@8.4.0
npx cson2json fleet.cson > fleet.json
```

On the lab's config, that produced exactly the JSON shown earlier: `600` for the interval, `15` for the mask, `true` for `yes` and the note joined with a `\n`. Given the `Math.max` line, it threw instead of calling the function. The comments are the one thing the conversion cannot carry, so copy them by hand into whatever format replaces CSON. JSON5 and TOML both keep comments, with a real spec behind them.

Do not start a new project on CSON. Its syntax is pleasant, but the parsers do not agree, the maintained ones date from 2021, and the host language is fading.

The cost of CSON is that the format is a language. That gives you arithmetic and comments, and it also gives you three answers to one line, a parser 4,975 times slower than `json.loads`, and an `eval` one option away.

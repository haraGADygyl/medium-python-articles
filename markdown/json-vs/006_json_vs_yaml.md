# JSON vs. YAML

#### YAML drops the braces and quotes, so its parser has to guess each value's type — and two Python libraries read 5 of 9 keys differently

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

YAML is what people reach for when JSON's braces and quotes get in the way of a file they edit by hand. CI pipelines, Kubernetes manifests, Ansible playbooks and Compose files are all YAML. Since YAML 1.2, JSON is officially a subset of it: any JSON document is valid YAML.

What YAML removes is exactly what made JSON's types unambiguous. In JSON, `"NO"` is a string because it has quotes, and `0640` is simply invalid. In YAML, unquoted values are resolved by what they look like. The rules for that changed between YAML 1.1 and 1.2, and PyYAML, the YAML library most Python code imports, still implements 1.1.

I wrote a ten-line export config for the series' buoy fleet and gave it to three parsers. PyYAML and ruamel.yaml disagreed on five of its nine keys. Then I timed YAML as a data format on the series' 20.8 MB payload, where the fastest Python YAML parser took 53 times as long as `json.loads`.

---

### The same config, both ways

The export settings as YAML, and as a script that reads them with PyYAML:

```python
import yaml

fleet_yaml = """\
# Export settings for the north-east harbour buoys.
fleet: north-east
share_with: [GB, NO, DK]      # met offices that receive the feed
upload_window: 22:30          # UTC, after the evening poll
firmware: 1.10
archive_mode: 0640
compress: on
station_code: 07031
commissioned: 2026-02-11
contact: null
"""

settings = yaml.safe_load(fleet_yaml)
print(settings["share_with"])     # ['GB', False, 'DK']
print(settings["upload_window"])  # 1350
print(settings["firmware"])       # 1.1
print(settings["archive_mode"])   # 416
print(settings["station_code"])   # 3609
print(type(settings["commissioned"]))  # <class 'datetime.date'>
```

Every line of that YAML looks reasonable, and PyYAML turned six of them into something other than what was written. Norway's country code became `False`. The upload window `22:30` became `1350`, because YAML 1.1 reads colon-separated numbers as base 60. Firmware `1.10` became the float `1.1`. The file mode `0640` and the station code `07031` were read as octal, 416 and 3609. `compress: on` became `True`, which you may have wanted. The date came back as a `datetime.date`, which `json.dumps` refuses to encode.

The JSON version has none of these problems, because every string is quoted:

```json
{
  "fleet": "north-east",
  "share_with": ["GB", "NO", "DK"],
  "upload_window": "22:30",
  "firmware": "1.10",
  "archive_mode": "0640",
  "compress": true,
  "station_code": "07031",
  "commissioned": "2026-02-11",
  "contact": null
}
```

It is noisier to write and it cannot hold the comment about the met offices. But `"NO"` is a string because of its quotes, and no parser can decide otherwise.

---

### What YAML actually changes

The type of an unquoted value depends on the parser. The same file, read by PyYAML 6.0.3 (YAML 1.1), ruamel.yaml 0.19.1 (YAML 1.2) and the npm `yaml` package 2.9.1 (YAML 1.2):

```
key             written       PyYAML                        ruamel.yaml                 npm yaml
share_with      [GB, NO, DK]  ['GB', False, 'DK']           ['GB', 'NO', 'DK']          ['GB', 'NO', 'DK']
upload_window   22:30         1350                          '22:30'                     '22:30'
firmware        1.10          1.1                           1.1                         1.1
archive_mode    0640          416                           640                         640
compress        on            True                          'on'                        'on'
station_code    07031         3609                          7031                        7031
commissioned    2026-02-11    datetime.date(2026, 2, 11)    datetime.date(2026, 2, 11)  '2026-02-11'

5 of 9 keys differ between PyYAML and ruamel.yaml: share_with, upload_window,
archive_mode, compress, station_code
```

YAML 1.2 fixed the worst of it. Only `true` and `false` (and their capitalised forms) are booleans, base 60 is gone, and octal needs an `0o` prefix. But 1.2 has its own surprises: `0640` became the integer `640`, the leading zero of `07031` is lost, and `1.10` is still `1.1` in every parser. The date shows a third split: both Python libraries build a `date`, while the JavaScript parser returns a string.

The cure is the one JSON imposes: quote anything that is not meant to be a number or a boolean.

```python
quoted = yaml.safe_load('share_with: ["GB", "NO", "DK"]\nfirmware: "1.10"\n')
print(quoted)  # {'share_with': ['GB', 'NO', 'DK'], 'firmware': '1.10'}
```

YAML also has three features JSON left out on purpose. **Anchors and aliases** let one node be reused by reference. **Tags** name a type, including language-specific ones such as `!!python/object/apply`. And duplicate keys are something each parser handles in its own way. All three show up in the measurements below.

The first of them earns its place in configuration. A CI file that defines its build settings once under an anchor and reuses them in five jobs with an alias is shorter and harder to get out of sync than five copied blocks. JSON has no way to say "the same as above", so you either repeat yourself or generate the file. The trouble is that the same mechanism works in a file an attacker wrote, and it costs a small file nothing to use it thousands of times.

---

### The measurement

Because every JSON document is valid YAML, each YAML parser can read the series' payload directly:

```
50000 records, 20,790,509 bytes of JSON, parsed as YAML
parser                                   ms  vs json  runs  same data
Python json.loads                     312.2       1x     5  True
PyYAML CSafeLoader (libyaml)        16395.5      53x     1  True
PyYAML safe_load (pure Python)      69380.7     222x     1  True
ruamel.yaml safe (C)                30378.3      97x     1  True
Node JSON.parse                       163.9              1
npm yaml 2.9.1                      10867.4      66x     1  (vs JSON.parse)
```

All four produced the same data, and all four were slow. The fastest Python option, PyYAML with its libyaml C loader, took 16.4 seconds against 0.31. Plain `yaml.safe_load`, which is what most code calls, took 69 seconds. The same records written as block-style YAML came to 21.7 MB, 4.3% more than compact JSON, so YAML does not win on size either.

The other three experiments are about what a YAML file can do to its reader:

```
1. aliases: 413 bytes of YAML, 6 levels
   yaml.safe_load        1.9 ms
   json.dumps          653.1 ms -> 72,222,220 bytes (174,872x)

2. a duplicated key
   PyYAML           {'buoy_id': 'HB-214', 'wave_height_m': 3.5}
   ruamel.yaml      DuplicateKeyError: found duplicate key "buoy_id" with value "HB-214" ...
   json.loads       {'buoy_id': 'HB-214'}

3. a language-specific tag
   yaml.safe_load   ConstructorError: could not determine a constructor for the tag ...
   yaml.unsafe_load {'checksum': 6}  (builtins.sum was called)
```

Four hundred bytes of nested aliases load in 2 ms, because the parser shares the nodes. Hand the result to anything that walks it, such as `json.dumps`, a validator or a template, and it becomes 72 MB. That is the "billion laughs" attack at a harmless six levels; a few more levels exhaust memory.

Duplicate keys split the parsers again. PyYAML keeps the last value without a word. ruamel.yaml refuses the file, which is what the YAML spec asks for.

The tag row is the one that matters most. `unsafe_load` called `builtins.sum` because the document told it to, and the same mechanism will call any importable function. `safe_load` refuses. Loading YAML from anywhere you do not control with anything other than a safe loader is running someone else's code.

---

### Where JSON still wins

Anywhere a program writes the file or reads it for data. JSON parsed 53 to 222 times faster in Python, its types come from its syntax rather than a resolver, and its reader cannot be told to call a function.

Anywhere two languages share a file. On one ten-line config, PyYAML, ruamel.yaml and the JavaScript `yaml` package disagreed about six values, counting the date. JSON parsers disagree only at the edges, such as `NaN` and 64-bit integers, which earlier articles in this series covered.

And for anything untrusted. With JSON, safety is the default. With YAML, it is a function name you have to remember: `safe_load`.

---

### Conclusion

Use YAML for configuration people write: CI pipelines, deployment manifests, anything that needs comments and would be buried under braces. When you do, quote every string that could look like something else, pin the YAML version your parser implements, read it with a safe loader, and validate the result against a schema instead of trusting the resolver.

Use JSON for data: anything generated, exchanged between languages, read in bulk or received from outside.

The cost of YAML is that the parser decides your types. In this lab it turned Norway into `False`, a time into a number, a version into the wrong float, and two codes into octal. It was also 53 times slower than `json.loads` at its best.

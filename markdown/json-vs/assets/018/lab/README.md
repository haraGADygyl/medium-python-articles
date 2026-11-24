# Lab — 018, JSON vs. JSON Schema

A demonstration lab with one timing run. Seven realistic producer bugs are injected
into the series' 50,000 buoy records, 1,000 records each; every corrupted record is
still valid JSON. The lab counts what `json.loads`, a first-draft schema and a strict
schema reject, shows what an unvalidated consumer computes from the feed, compares two
Python validators on the same schema, and times validation against parsing.

Python 3.12.3, `jsonschema==4.26.0` (with `referencing==0.37.0`,
`rpds-py==2026.9.1`), `rfc3339-validator==0.1.4`, `fastjsonschema==2.22.3`; Ryzen 5
3600. The payload is the shared dataset from `../../payload/make_payload.py`, built in
memory.

```bash
python3 -m venv .venv
.venv/bin/pip install jsonschema==4.26.0 rfc3339-validator==0.1.4 fastjsonschema==2.22.3
# a second environment without the format extra, for annotations.py only
python3 -m venv bare
bare/bin/pip install jsonschema==4.26.0
```

| File | What it is |
| --- | --- |
| `buoy.schema.json` | The strict draft 2020-12 schema printed in the article |
| `buoy.loose.schema.json` | The first draft: types and `required` only, open objects, no ranges or enums |

| Experiment | Command | Output |
| --- | --- | --- |
| Seven faults × 1,000 records against `json.loads`, the first draft, the first draft with `FormatChecker`, and the strict schema; what a dashboard computes from the bad feed; every error for one record per fault | `.venv/bin/python faults.py` | `output-faults.txt` |
| `format` and `default` as annotations, run with and without `rfc3339-validator` | `.venv/bin/python annotations.py; bare/bin/python annotations.py` | `output-annotations.txt` |
| `jsonschema` against `fastjsonschema` on the same schema: the seven faults, a 2020-12 `prefixItems` schema, and `default` | `.venv/bin/python implementations.py` | `output-implementations.txt` |
| Parse time against validation time, best of five, GC paused | `.venv/bin/python measure.py` | `output-measure.txt` |
| The snippet printed in the article | `.venv/bin/python snippets.py` | `output-snippets.txt` |

The corruption is seeded (`random.Random(18)`), so every run picks the same 7,000
records and every count is identical from run to run.

**Formats are off unless you ask, and sometimes off when you do.** Draft 2020-12 treats
`format` as an annotation. `jsonschema` asserts it only when given a `FormatChecker`,
and that checker registers `date-time` only if `rfc3339-validator` is importable.
Without the extra, `FormatChecker()` accepts `"yesterday at noon"` as a `date-time`
and says nothing. `fastjsonschema.compile()` checks formats by default
(`use_formats=True`), with its own regular expressions.

**`fastjsonschema` 2.22.3 implements drafts 04, 06 and 07.** Given a 2020-12 `$schema`
URI it silently uses its draft-2019 code generator, so 2020-12-only keywords such as
`prefixItems` are ignored and `items` keeps its older meaning. It also applies
`default` values by default (`use_default=True`), writing them into the dict it was
handed.

**Timing.** `measure.py` builds every validator once, outside the timed loop, except
the last row, which calls `jsonschema.validate()` per record the way tutorials show it;
that row runs on 5,000 records to keep the run short. Two runs on this machine differed
by about 5%; the article quotes per-record times and ratios, rounded.

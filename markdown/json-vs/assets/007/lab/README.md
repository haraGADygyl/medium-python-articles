# Lab — 007, JSON vs. CSON

A demonstration lab: one CSON config (`fleet.cson`) and five one-line features on
three CSON readers plus both native JSON parsers, the readers' speed on the series'
payload, and the npm converter used for migration.

Python 3.12.3 with `cson==0.8` (released 2019-01-22); Node v24.20.0 with
`cson-parser@4.0.9` (published 2021-03-26), `coffeescript@2.7.0` and `cson@8.4.0`,
pinned in `package.json` / `package-lock.json`; Ryzen 5 3600.

```bash
pip install cson==0.8
npm ci
```

| Experiment | Command | Output |
| --- | --- | --- |
| The config and five features on every reader | `python3 interop.py` | `output-interop.txt` |
| Parse time on 5,000 records of the payload | `python3 speed.py` | `output-speed.txt` |
| The Python snippet printed in the article | `python3 snippets.py` | `output-snippets.txt` |
| Migration with the npm converter | `npx cson2json fleet.cson` | `output-cson2json.json` |

**5,000 records, not 50,000.** Python's `cson` parses 5,000 records in about
140 s; the full payload would take over twenty minutes. Every reader in `speed.py`
gets the same 5,000.

**Evaluation.** `readers.js` has a `coffeescript` mode that calls
`CoffeeScript.eval` — deliberately, to show what an evaluating reader does
(`Math.max` is called). `cson-parser` and `cson2json` refuse function calls.
`readers.js` prints non-finite numbers as `"<Infinity>"` because `JSON.stringify`
would otherwise report them as `null`.

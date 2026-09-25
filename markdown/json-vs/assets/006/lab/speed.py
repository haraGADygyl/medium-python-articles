"""YAML as a data format: every JSON document is YAML 1.2, so time the parsers
on the series' 20.8 MB payload."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ruamel.yaml
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "payload"))

from make_payload import build                              # noqa: E402

RECORDS = 50000


def best_ms(fn, text: str, runs: int) -> tuple[float, object]:
    fastest, result = float("inf"), None
    for _ in range(runs):
        started = time.perf_counter()
        result = fn(text)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
    return fastest, result


def main() -> None:
    data = build(RECORDS)
    text = json.dumps(data, separators=(",", ":"))
    print(f"{RECORDS} records, {len(text):,} bytes of JSON, parsed as YAML")
    ruamel_c = ruamel.yaml.YAML(typ="safe", pure=False)
    engine = "C" if "CParser" in ruamel_c.Parser.__name__ else "pure Python"
    parsers = [
        ("Python json.loads", json.loads, 5),
        ("PyYAML CSafeLoader (libyaml)",
         lambda t: yaml.load(t, Loader=yaml.CSafeLoader), 1),
        ("PyYAML safe_load (pure Python)", yaml.safe_load, 1),
        (f"ruamel.yaml safe ({engine})", ruamel_c.load, 1),
    ]
    base = None
    print(f"{'parser':<32}{'ms':>11}{'vs json':>9}  runs  same data")
    for label, fn, runs in parsers:
        ms, value = best_ms(fn, text, runs)
        base = base or ms
        print(f"{label:<32}{ms:>11.1f}{ms / base:>8.0f}x  {runs:>4}  "
              f"{value == data}")

    with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
        handle.write(text)
        handle.flush()
        out = subprocess.run(
            ["node", "-e",
             "const Y=require('yaml'),fs=require('fs');"
             "const t=fs.readFileSync(process.argv[1],'utf8');"
             "let s=process.hrtime.bigint();JSON.parse(t);"
             "const a=Number(process.hrtime.bigint()-s)/1e6;"
             "s=process.hrtime.bigint();Y.parse(t);"
             "console.log(a, Number(process.hrtime.bigint()-s)/1e6)",
             handle.name], capture_output=True, text=True, check=True,
            cwd=HERE).stdout.split()
    node_json, node_yaml = map(float, out)
    print(f"{'Node JSON.parse':<32}{node_json:>11.1f}{'':>9}     1")
    print(f"{'npm yaml 2.9.1':<32}{node_yaml:>11.1f}"
          f"{node_yaml / node_json:>8.0f}x  {1:>4}  (vs JSON.parse)")

    block = yaml.dump(data, Dumper=yaml.CSafeDumper, sort_keys=False)
    print()
    print(f"the same records written as block-style YAML: {len(block):,} "
          f"bytes, {100 * (len(block) / len(text) - 1):+.1f}% against "
          f"compact JSON")


if __name__ == "__main__":
    main()

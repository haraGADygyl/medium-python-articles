"""What JSON5 parsers cost on data rather than config: the 20.8 MB payload.

Every JSON document is valid JSON5, so all parsers read the same bytes.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import json5
import pyjson5

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE.parents[1] / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RECORDS = 50000


def best_ms(fn, text: str, runs: int) -> float:
    fastest = float("inf")
    for _ in range(runs):
        started = time.perf_counter()
        fn(text)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
    return fastest


def main() -> None:
    text = json.dumps(build(RECORDS), separators=(",", ":"))
    print(f"{RECORDS} records, {len(text):,} bytes of plain JSON")
    base = best_ms(json.loads, text, 5)
    rows = [("Python json.loads", base, 5),
            (f"Python pyjson5 {pyjson5.__version__}",
             best_ms(pyjson5.loads, text, 5), 5),
            (f"Python json5 {json5.__version__}",
             best_ms(json5.loads, text, 1), 1)]

    with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
        handle.write(text)
        handle.flush()
        node = subprocess.run(
            ["node", "-e",
             "const J=require('json5'),fs=require('fs');"
             "const t=fs.readFileSync(process.argv[1],'utf8');"
             "const best=(f,n)=>{let b=1e9;for(let i=0;i<n;i++){"
             "const s=process.hrtime.bigint();f(t);"
             "b=Math.min(b,Number(process.hrtime.bigint()-s)/1e6)}return b};"
             "console.log(best(JSON.parse,5), best(J.parse,1))",
             handle.name], capture_output=True, text=True, check=True,
            cwd=HERE)
    node_json, node_json5 = map(float, node.stdout.split())
    rows += [("Node JSON.parse", node_json, 5),
             ("npm json5 2.2.3", node_json5, 1)]

    print(f"{'parser':<24}{'ms':>11}{'vs json.loads':>15}  runs")
    for label, ms, runs in rows:
        print(f"{label:<24}{ms:>11.1f}{ms / base:>14.1f}x  best of {runs}")


if __name__ == "__main__":
    main()

"""One JSON5 config, six parsers: who reads it, and do the readers agree?"""
import json
import math
import subprocess
from pathlib import Path

import json5
import pyjson5

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "fleet.json5"


def summarise(value: object) -> str:
    """The fields where JSON5-only syntax was used, or the error."""
    if not isinstance(value, dict):
        return str(value)
    return (f"mask={value['sensor_mask']} gust={value['max_gust_ms']} "
            f"drift={value['drift_tolerance_deg']} "
            f"note={value['maintenance_note']!r}")


def main() -> None:
    text = CONFIG.read_text()
    results: dict[str, object] = {}
    try:
        results["Python json.loads"] = json.loads(text)
    except json.JSONDecodeError as exc:
        results["Python json.loads"] = f"JSONDecodeError: {exc}"
    results[f"Python json5 {json5.__version__}"] = json5.loads(text)
    results[f"Python pyjson5 {pyjson5.__version__}"] = pyjson5.loads(text)

    node = subprocess.run(["node", str(HERE / "readers.js"), str(CONFIG)],
                          capture_output=True, text=True, check=True)
    for label, value in json.loads(node.stdout).items():
        if isinstance(value, dict) and value["max_gust_ms"] == "<Infinity>":
            value["max_gust_ms"] = math.inf
        results[label] = value

    jq = subprocess.run(["jq", "-c", "."], input=text, capture_output=True,
                        text=True)
    jq_version = subprocess.run(["jq", "--version"], capture_output=True,
                                text=True).stdout.strip()
    results[jq_version] = jq.stderr.strip().splitlines()[0]

    print(f"config: {CONFIG.name}, {len(text)} bytes, "
          f"{text.count('//')} comments")
    for label, value in results.items():
        print(f"  {label:<26}{summarise(value)}")

    parsed = [v for v in results.values() if isinstance(v, dict)]
    print()
    print(f"{len(parsed)} of {len(results)} parsers read it; "
          f"they agree: {all(p == parsed[0] for p in parsed)}")


if __name__ == "__main__":
    main()

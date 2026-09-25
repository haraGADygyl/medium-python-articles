"""One CSON config and five one-line features on every parser in reach."""
import json
import subprocess
from pathlib import Path

import cson

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "fleet.cson"
FEATURES = [
    "compress: yes",
    "poll_interval_s: 10 * 60",
    'label: "NE-#{7 + 1}"',
    "max_gust_ms: Infinity",
    "limit: Math.max(25, 40)",
]


def node(mode: str, text: str) -> str:
    out = json.loads(subprocess.run(
        ["node", str(HERE / "readers.js"), mode], input=text,
        capture_output=True, text=True, check=True, cwd=HERE).stdout)
    return json.dumps(out["ok"]) if "ok" in out else out["error"]


def python_cson(text: str) -> str:
    try:
        return json.dumps(cson.loads(text))
    except Exception as exc:                       # speg raises its own types
        return f"{type(exc).__name__}: {str(exc)[:40]}"


def python_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text))
    except json.JSONDecodeError as exc:
        return f"JSONDecodeError: {exc}"


def main() -> None:
    text = CONFIG.read_text()
    readers = {
        "npm cson-parser 4.0.9": lambda t: node("cson-parser", t),
        "Python cson 0.8": python_cson,
        "CoffeeScript 2.7.0 eval": lambda t: node("coffeescript", t),
        "Python json.loads": python_json,
        "Node JSON.parse": lambda t: node("json", t),
    }
    print(f"{CONFIG.name}, {len(text.splitlines())} lines")
    for label, read in readers.items():
        print(f"  {label:<25}{read(text)[:100]}")

    print()
    for feature in FEATURES:
        print(feature)
        for label in ("npm cson-parser 4.0.9", "Python cson 0.8",
                      "CoffeeScript 2.7.0 eval"):
            print(f"  {label:<25}{readers[label](feature)[:70]}")


if __name__ == "__main__":
    main()

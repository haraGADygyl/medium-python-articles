"""Change one value in the JSON5 config through each library's load/dump."""
import subprocess
from pathlib import Path

import json5
import pyjson5

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "fleet.json5"


def report(label: str, written: str) -> None:
    print(f"--- {label}: {len(written.splitlines())} lines, "
          f"{written.count('//')} comments")
    print(written)


def main() -> None:
    text = CONFIG.read_text()
    report("original", text.rstrip("\n"))

    config = json5.loads(text)
    config["poll_interval_s"] = 900
    report("Python json5.dumps(indent=2, quote_keys=False)",
           json5.dumps(config, indent=2, quote_keys=False,
                       trailing_commas=True))
    report("Python pyjson5.dumps", pyjson5.dumps(config))

    node = subprocess.run(
        ["node", "-e",
         "const J=require('json5'),fs=require('fs');"
         "const c=J.parse(fs.readFileSync(process.argv[1],'utf8'));"
         "c.poll_interval_s=900;console.log(J.stringify(c,null,2))",
         str(CONFIG)], capture_output=True, text=True, check=True, cwd=HERE)
    report("npm json5.stringify(c, null, 2)", node.stdout.rstrip("\n"))


if __name__ == "__main__":
    main()

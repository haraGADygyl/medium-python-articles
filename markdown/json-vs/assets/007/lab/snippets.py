"""The snippets the article shows, run end to end (reads fleet.cson)."""
import json
from pathlib import Path

import cson

text = Path("fleet.cson").read_text()

try:
    cson.loads(text)
except Exception as exc:          # the parser raises speg.ParseError
    print(f"{type(exc).__name__}: {exc.args[0]}")

portable = (text.replace("10 * 60", "600")
                .replace("compress: yes", "compress: true"))
config = cson.loads(portable)

print(config["poll_interval_s"], config["compress"], config["sensor_mask"])
print(json.dumps(config["maintenance_note"]))

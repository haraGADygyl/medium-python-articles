"""The snippets the article shows, run end to end (reads fleet.json5)."""
import json
from pathlib import Path

import json5

text = Path("fleet.json5").read_text()

try:
    json.loads(text)
except json.JSONDecodeError as exc:
    print(f"JSONDecodeError: {exc}")
# JSONDecodeError: Expecting value: line 1 column 1 (char 0)

config = json5.loads(text)
print(config["sensor_mask"], config["max_gust_ms"])  # 15 inf
print(config["maintenance_note"])
# Recalibrate the thermistors after the winter swap.

config["poll_interval_s"] = 900
written = json5.dumps(config, indent=2, quote_keys=False,
                      trailing_commas=True)
print(written.count("//"), len(written.splitlines()))  # 0 22
print(written.splitlines()[9:11])
# ['  sensor_mask: 15,', '  max_gust_ms: Infinity,']

"""fleet.toml converted to JSON, with datetimes written by isoformat()."""
import json
import tomllib
from pathlib import Path

settings = tomllib.loads(Path("fleet.toml").read_text())
as_json = json.dumps(settings, indent=2, default=lambda value: value.isoformat())
Path("output-fleet.json").write_text(as_json + "\n")
print(as_json)

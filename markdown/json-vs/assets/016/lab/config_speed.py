"""How long tomllib takes on a config-sized file: fleet.toml, 664 bytes."""
import json
import timeit
import tomllib
from pathlib import Path

text = Path("fleet.toml").read_text()
as_json = Path("output-fleet.json").read_text()
for label, call in (("tomllib.loads(fleet.toml)", lambda: tomllib.loads(text)),
                    ("json.loads(output-fleet.json)", lambda: json.loads(as_json))):
    loops = 2000
    best = min(timeit.repeat(call, number=loops, repeat=5)) / loops
    print(f"{label:<32}{best * 1e6:>8.1f} µs per parse, best of 5 x {loops}")

"""The nine values from the YAML article's fleet config, written with TOML's '='.

Each line is parsed as its own document, because a TOML parser stops at the first
error. tomllib in Python 3.12 implements TOML 1.0.0; tomli 2.5.0 implements 1.1.0.
"""
import sys
import tomllib
from importlib.metadata import version

import tomli

LINES = [
    "fleet = north-east",
    "share_with = [GB, NO, DK]",
    "upload_window = 22:30",
    "firmware = 1.10",
    "archive_mode = 0640",
    "compress = on",
    "station_code = 07031",
    "commissioned = 2026-02-11",
    "contact = null",
]


def outcome(parse, line: str) -> str:
    try:
        return repr(next(iter(parse(line).values())))
    except (tomllib.TOMLDecodeError, tomli.TOMLDecodeError) as error:
        message = str(error).split(" (at")[0]
        return f"refused: {message[:24]}{'...' if len(message) > 24 else ''}"


python = f"{sys.version_info.major}.{sys.version_info.minor}"
print(f"{'written':<28}{'tomllib, Python ' + python + ' (TOML 1.0)':<40}"
      f"tomli {version('tomli')} (TOML 1.1)")
refused = 0
for line in LINES:
    old, new = outcome(tomllib.loads, line), outcome(tomli.loads, line)
    refused += old.startswith("refused")
    print(f"{line:<28}{old:<40}{new}")

print()
print(f"tomllib refused {refused} of {len(LINES)}")

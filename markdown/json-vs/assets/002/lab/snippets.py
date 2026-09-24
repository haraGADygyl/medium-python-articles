"""The snippets the article shows, run end to end."""
import json
import math

reading = {
    "observation_id": 9007199254772330,
    "buoy_id": "NE-07",
    "wave_height_m": math.nan,          # the sensor dropped out
    "wind_gust_ms": math.inf,           # the anemometer overflowed
    "qc_passed": True,
}

print(json.dumps(reading))
# {"observation_id": 9007199254772330, "buoy_id": "NE-07",
#  "wave_height_m": NaN, "wind_gust_ms": Infinity, "qc_passed": false}

try:
    json.dumps(reading, allow_nan=False)
except ValueError as exc:
    print(f"ValueError: {exc}")

print("--- strict reader")


def refuse_constant(token: str) -> float:
    """Reject NaN, Infinity and -Infinity instead of inventing floats."""
    raise ValueError(f"{token} is not a JSON number")


incoming = '{"buoy_id": "NE-07", "wave_height_m": NaN}'
try:
    json.loads(incoming, parse_constant=refuse_constant)
except ValueError as exc:
    print(f"ValueError: {exc}")

print(json.loads("1e400"))
print(json.dumps(json.loads("1e400")))

print("--- null plus a reason")


def with_faults(record: dict) -> dict:
    """Replace each non-finite float with null and say why in `faults`."""
    clean, faults = {}, {}
    for key, value in record.items():
        if isinstance(value, float) and not math.isfinite(value):
            clean[key] = None
            faults[key] = "dropout" if math.isnan(value) else "overflow"
        else:
            clean[key] = value
    return {**clean, "faults": faults} if faults else clean


print(json.dumps(with_faults(reading), allow_nan=False))

print("--- string sentinels")
SENTINELS = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}
FLOAT_FIELDS = {"wave_height_m", "wind_gust_ms"}


def encode_special(value: object) -> object:
    """Spell non-finite floats as the strings Protobuf and Postgres use."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else (
            "Infinity" if value > 0 else "-Infinity")
    return value


def decode_special(obj: dict) -> dict:
    """object_hook: turn the sentinels back into floats, in float fields only."""
    for key in FLOAT_FIELDS & obj.keys():
        if obj[key] in SENTINELS:
            obj[key] = SENTINELS[obj[key]]
    return obj


wire = json.dumps({k: encode_special(v) for k, v in reading.items()},
                  allow_nan=False)
back = json.loads(wire, object_hook=decode_special)
print(back["wave_height_m"], back["wind_gust_ms"])

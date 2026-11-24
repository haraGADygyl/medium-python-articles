"""One schema, two Python validators: where they agree and where they do not.

    python3 implementations.py > output-implementations.txt
"""
import copy
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import fastjsonschema
from jsonschema import Draft202012Validator, FormatChecker

from faults import FAULTS, build, corrupt

HERE = Path(__file__).parent
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def fast_verdict(validate, document) -> str:
    """'valid' or fastjsonschema's first error message."""
    try:
        validate(document)
    except fastjsonschema.JsonSchemaException as error:
        return f"invalid ({error.message})"

    return "valid"


def main() -> None:
    print(f"jsonschema {version('jsonschema')}, "
          f"fastjsonschema {version('fastjsonschema')}")
    strict = json.loads((HERE / "buoy.schema.json").read_text())
    reference = Draft202012Validator(strict, format_checker=FormatChecker())
    fast = fastjsonschema.compile(strict)

    records = build(50_000)
    applied = corrupt(records)
    caught_ref, caught_fast = Counter(), Counter()

    for index, record in enumerate(records):
        fault = applied.get(index, "clean")
        if not reference.is_valid(record):
            caught_ref[fault] += 1

        if fast_verdict(fast, copy.deepcopy(record)) != "valid":
            caught_fast[fault] += 1

    print(f"\n1. the seven faults, strict schema with formats\n"
          f"{'fault':<26}{'jsonschema':>12}{'fastjsonschema':>16}")

    for name in [f.__name__ for f in FAULTS] + ["clean"]:
        print(f"{name:<26}{caught_ref[name]:>12,}{caught_fast[name]:>16,}")

    print("\n2. a 2020-12 keyword: position as a [lat, lon] pair")
    pair = {"$schema": DRAFT, "type": "array",
            "prefixItems": [{"type": "number", "minimum": -90, "maximum": 90},
                            {"type": "number", "minimum": -180, "maximum": 180}],
            "items": False}
    pair_ref = Draft202012Validator(pair)
    pair_fast = fastjsonschema.compile(pair)

    for document in ([57.21621, -2.37579], [57.21621, -2.37579, 4.0]):
        print(f"  {json.dumps(document):<28} jsonschema: "
              f"{'valid' if pair_ref.is_valid(document) else 'invalid'}"
              f"   fastjsonschema: {fast_verdict(pair_fast, document)}")

    print("\n3. `default`: does validating change the record?")
    reading = copy.deepcopy(build(1)[0])
    del reading["notes"]
    reference.validate(reading)
    print(f"  jsonschema:     'notes' in record after validate: "
          f"{'notes' in reading}")
    returned = fast(reading)
    print(f"  fastjsonschema: 'notes' in record after validate: "
          f"{'notes' in reading}  (value {reading.get('notes')!r}, "
          f"returned object is the input: {returned is reading})")


if __name__ == "__main__":
    main()

"""Seven producer bugs, 1,000 records each, against a parser and two schemas.

Every corrupted record is still valid JSON, so json.loads accepts all of them.
The question is which of them a first-draft schema catches, which only a strict
schema catches, and which no schema catches at all.

    python3 faults.py > output-faults.txt
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "payload"))
from make_payload import build  # noqa: E402

HERE = Path(__file__).parent
PER_FAULT = 1_000


def stringified_number(record: dict) -> None:
    """A producer that formats every number as text."""
    record["wave_height_m"] = str(record["wave_height_m"])


def truthy_string(record: dict) -> None:
    """A boolean read from a CSV column and never converted."""
    record["qc_passed"] = "false"


def sentinel_value(record: dict) -> None:
    """The oceanographic habit of writing -999 for 'no reading'."""
    record["wave_height_m"] = -999.0


def naive_timestamp(record: dict) -> None:
    """A timestamp serialised from a datetime with no tzinfo."""
    record["recorded_at"] = record["recorded_at"].removesuffix("+00:00")


def misspelled_optional_key(record: dict) -> None:
    """'note' instead of 'notes': the field the consumer reads stays absent."""
    del record["notes"]
    record["note"] = "drifted off station"


def uppercase_enum(record: dict) -> None:
    """A firmware update that started shouting its status values."""
    record["sensors"][0]["status"] = record["sensors"][0]["status"].upper()


def swapped_coordinates(record: dict) -> None:
    """lat and lon written in the wrong order — both still in range."""
    position = record["position"]
    position["lat"], position["lon"] = position["lon"], position["lat"]


FAULTS = [stringified_number, truthy_string, sentinel_value, naive_timestamp,
          misspelled_optional_key, uppercase_enum, swapped_coordinates]


def corrupt(records: list[dict]) -> dict[int, str]:
    """Apply each fault to its own 1,000 records; return index -> fault name."""
    rng = random.Random(18)
    chosen = rng.sample(range(len(records)), PER_FAULT * len(FAULTS))
    applied = {}

    for slot, index in enumerate(chosen):
        fault = FAULTS[slot // PER_FAULT]
        fault(records[index])
        applied[index] = fault.__name__

    return applied


def main() -> None:
    records = build(50_000)
    applied = corrupt(records)
    lines = [json.dumps(r, separators=(",", ":")) for r in records]
    parsed = [json.loads(line) for line in lines]
    print(f"records: {len(parsed):,}   corrupted: {len(applied):,}   "
          f"json.loads rejected: {len(lines) - len(parsed)}")

    loose_schema = json.loads((HERE / "buoy.loose.schema.json").read_text())
    strict_schema = json.loads((HERE / "buoy.schema.json").read_text())
    regimes = {
        "first draft": Draft202012Validator(loose_schema),
        "first draft + formats": Draft202012Validator(
            loose_schema, format_checker=FormatChecker()),
        "strict + formats": Draft202012Validator(
            strict_schema, format_checker=FormatChecker()),
    }
    caught = {name: Counter() for name in regimes}
    clean_rejected = Counter()

    for index, record in enumerate(parsed):
        for name, validator in regimes.items():
            if validator.is_valid(record):
                continue

            if index in applied:
                caught[name][applied[index]] += 1
            else:
                clean_rejected[name] += 1

    header = f"\n{'fault':<26}" + "".join(f"{name:>24}" for name in regimes)
    print(header)

    for fault in FAULTS:
        row = f"{fault.__name__:<26}"
        row += "".join(f"{caught[name][fault.__name__]:>24,}" for name in regimes)
        print(row)

    totals = "".join(f"{sum(caught[n].values()):>24,}" for n in regimes)
    print(f"{'caught of 7,000':<26}{totals}")
    falses = "".join(f"{clean_rejected[n]:>24,}" for n in regimes)
    print(f"{'clean records rejected':<26}{falses}")

    # What the consumer computes when nothing validates.
    clean = build(50_000)
    print("\nwhat a dashboard computes from the unvalidated feed")
    clean_mean = sum(r["wave_height_m"] for r in clean) / len(clean)
    numeric = [r["wave_height_m"] for r in parsed
               if isinstance(r["wave_height_m"], float)]
    print(f"  mean wave height, clean feed:         {clean_mean:.3f} m")
    print(f"  mean wave height, numeric values only: "
          f"{sum(numeric) / len(numeric):.3f} m  ({len(numeric):,} values)")

    try:
        sum(r["wave_height_m"] for r in parsed)
    except TypeError as error:
        print(f"  sum over every value: TypeError: {error}")

    clean_passed = sum(1 for r in clean if r["qc_passed"])
    feed_passed = sum(1 for r in parsed if r["qc_passed"])
    print(f"  records passing `if r['qc_passed']`: clean {clean_passed:,}, "
          f"feed {feed_passed:,}")
    misfiled = [r for r in parsed if "note" in r]
    seen = sum(1 for r in misfiled if r.get("notes"))
    print(f"  notes sent under 'note', seen by r.get('notes'): "
          f"{seen} of {len(misfiled):,}")

    print("\nevery error for one record of each fault, strict + formats")
    strict = regimes["strict + formats"]
    shown = set()

    for index in sorted(applied):
        fault = applied[index]
        if fault in shown:
            continue

        shown.add(fault)
        errors = sorted(strict.iter_errors(parsed[index]),
                        key=lambda e: list(e.absolute_path))
        print(f"  {fault}:")

        for error in errors:
            print(f"    {error.json_path}: {error.message}")

        if not errors:
            print("    (valid)")


if __name__ == "__main__":
    main()

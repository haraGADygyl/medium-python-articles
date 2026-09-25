"""What JSON-LD processing does to a buoy record."""
import json
import sys
from pathlib import Path

from pyld import jsonld

from contexts import AGENCY_CONTEXT, OBSERVATION_CONTEXT

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402


def main() -> None:
    record = build(1)[0]
    doc = {"@context": OBSERVATION_CONTEXT, **record}

    expanded = jsonld.expand(doc)[0]
    present = set(expanded)

    def iri(term: str) -> str | None:
        """The full IRI a term maps to, or None if the context lacks it."""
        probe = jsonld.expand({"@context": OBSERVATION_CONTEXT, term: 0})
        return next(iter(probe[0]), None) if probe else None

    print(f"1. expansion keeps {len(expanded)} of {len(record)} top-level keys")
    for key, value in record.items():
        target = iri(key)
        if target not in present:
            reason = "no term in the context" if target is None else \
                f"value is {json.dumps(value)}"
            print(f"   dropped {key!r}: {reason}")

    vocab = [OBSERVATION_CONTEXT,
             {"@vocab": "https://harbour-buoys.example/terms#"}]
    print(f"   with @vocab added: "
          f"{len(jsonld.expand({'@context': vocab, **record})[0])} kept")

    ours = {"@context": OBSERVATION_CONTEXT, "buoy_id": "NE-08",
            "recorded_at": "2026-02-11T00:00:00+00:00", "wave_height_m": 3.5}
    theirs = {"@context": AGENCY_CONTEXT, "station": "NE-08",
              "obs_time": "2026-02-11T00:00:00+00:00", "hs": 3.5}
    print()
    print("2. two producers, different field names")
    print(f"   same JSON: {ours == theirs}; same after expansion: "
          f"{jsonld.expand(ours) == jsonld.expand(theirs)}")
    print(f"   {json.dumps(jsonld.expand(theirs)[0], sort_keys=True)}")

    nquads = jsonld.normalize(doc, {"algorithm": "URDNA2015",
                                    "format": "application/n-quads"})
    lines = nquads.strip().splitlines()
    print()
    print(f"3. one record as RDF: {len(lines)} statements, "
          f"{len(nquads.encode()):,} bytes of canonical N-Quads")
    for line in lines:
        if "resultTime" in line or "significantWaveHeight" in line:
            print(f"   {line}")


if __name__ == "__main__":
    main()

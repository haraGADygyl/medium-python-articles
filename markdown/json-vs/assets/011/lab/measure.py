"""XML, JsonML, xmltodict JSON and the plain payload: size, fidelity, speed."""
import gc
import gzip
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import xmltodict
import zstandard

from jsonml import from_jsonml, record_to_xml, to_jsonml

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "payload"))

from make_payload import build                              # noqa: E402

RUNS = 5
RECORDS = 50000


def best(fn, *args) -> tuple[float, object]:
    fastest, result = float("inf"), None
    for _ in range(RUNS):
        gc.disable()
        started = time.perf_counter()
        result = fn(*args)
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
        gc.enable()
    return fastest, result


def sizes(text: str) -> tuple[int, int, int]:
    blob = text.encode()
    return (len(blob), len(gzip.compress(blob, 9)),
            len(zstandard.ZstdCompressor(level=3).compress(blob)))


def main() -> None:
    rows = build(RECORDS)
    root = ET.Element("observations")
    root.extend(record_to_xml(r) for r in rows)
    xml_text = ET.tostring(root, encoding="unicode")

    jsonml_text = json.dumps(to_jsonml(ET.fromstring(xml_text)),
                             separators=(",", ":"))
    natural_text = json.dumps(xmltodict.parse(xml_text), separators=(",", ":"))
    plain_text = json.dumps(rows, separators=(",", ":"))

    print(f"{RECORDS} buoy records, best of {RUNS}")
    print(f"{'form':<26}{'bytes':>12}{'gzip -9':>12}{'zstd -3':>12}")
    for label, text in (("XML", xml_text), ("JsonML", jsonml_text),
                        ("xmltodict JSON", natural_text),
                        ("plain JSON payload", plain_text)):
        raw, gz, zs = sizes(text)
        print(f"{label:<26}{raw:>12,}{gz:>12,}{zs:>12,}")

    back = ET.tostring(from_jsonml(json.loads(jsonml_text)), encoding="unicode")
    natural_back = xmltodict.unparse(json.loads(natural_text),
                                     full_document=False)
    print()
    canon = ET.canonicalize(xml_text)
    print(f"round trip, compared as canonical XML (C14N 2.0): "
          f"JsonML {ET.canonicalize(back) == canon}, "
          f"xmltodict {ET.canonicalize(natural_back) == canon}")

    print()
    print(f"{'reading the XML-derived data':<40}{'ms':>9}")
    ms, _ = best(lambda: to_jsonml(ET.fromstring(xml_text)))
    print(f"{'  ElementTree parse + to_jsonml':<40}{ms:>9.1f}")
    ms, _ = best(json.loads, jsonml_text)
    print(f"{'  json.loads of the JsonML':<40}{ms:>9.1f}")
    ms, _ = best(xmltodict.parse, xml_text)
    print(f"{'  xmltodict.parse':<40}{ms:>9.1f}")
    ms, _ = best(json.loads, plain_text)
    print(f"{'  json.loads of the plain payload':<40}{ms:>9.1f}")


if __name__ == "__main__":
    main()

"""The snippets the article shows, run end to end."""
import json
import xml.etree.ElementTree as ET

import xmltodict


def to_jsonml(element: ET.Element) -> list:
    """Element -> JsonML array, keeping text and tails in document order."""
    node: list = [element.tag]
    if element.attrib:
        node.append(dict(element.attrib))
    if element.text:
        node.append(element.text)
    for child in element:
        node.append(to_jsonml(child))
        if child.tail:
            node.append(child.tail)
    return node


def from_jsonml(node: list) -> ET.Element:
    """JsonML array -> Element: the exact inverse of to_jsonml."""
    tag, rest = node[0], node[1:]
    attributes = rest.pop(0) if rest and isinstance(rest[0], dict) else {}
    element = ET.Element(tag, attributes)
    last = None
    for child in rest:
        if isinstance(child, str):
            if last is None:
                element.text = (element.text or "") + child
            else:
                last.tail = (last.tail or "") + child
        else:
            last = from_jsonml(child)
            element.append(last)
    return element


report = """<observation buoy="NE-08" recorded-at="2026-02-11T00:00:00+00:00">\
<wave-height unit="m">3.5</wave-height>\
<note>Buoy <ref buoy="NE-08"/> drifted <em>0.4 km</em> off station.</note>\
</observation>"""

as_jsonml = to_jsonml(ET.fromstring(report))
print(json.dumps(as_jsonml))

back = ET.tostring(from_jsonml(as_jsonml), encoding="unicode")
print(ET.canonicalize(back) == ET.canonicalize(report))  # True

natural = xmltodict.parse(report)
print(json.dumps(natural["observation"]["note"]))
# {"ref": {"@buoy": "NE-08"}, "em": "0.4 km", "#text": "Buoy  drifted  off station."}
natural_back = xmltodict.unparse(natural, full_document=False)
print(ET.canonicalize(natural_back) == ET.canonicalize(report))  # False

one = "<sensors><sensor tag='gps'/></sensors>"
two = "<sensors><sensor tag='gps'/><sensor tag='thermistor'/></sensors>"
print(type(xmltodict.parse(one)["sensors"]["sensor"]).__name__,
      type(xmltodict.parse(two)["sensors"]["sensor"]).__name__)  # dict list
print(type(xmltodict.parse(one, force_list=("sensor",))["sensors"]["sensor"]).__name__)
# list
print(json.dumps(to_jsonml(ET.fromstring(one))))
# ["sensors", ["sensor", {"tag": "gps"}]]

def first_child(node: list, tag: str) -> list:
    """The first child element of a JsonML node with the given tag."""
    return next(c for c in node[1:] if isinstance(c, list) and c[0] == tag)


print(first_child(as_jsonml, "wave-height")[2])       # 3.5
print(natural["observation"]["wave-height"]["#text"])  # 3.5

note_markup = ET.tostring(ET.fromstring(report).find("note"), encoding="unicode")
as_string = json.dumps({"note": note_markup})
as_tree = json.dumps({"note": first_child(as_jsonml, "note")})
print(len(as_string), len(as_tree))  # 89 103


def plain_text(node: list) -> str:
    """Concatenate every text node under a JsonML element, in order."""
    return "".join(child if isinstance(child, str) else plain_text(child)
                   for child in node[1:] if not isinstance(child, dict))


print(plain_text(first_child(as_jsonml, "note")))
# Buoy  drifted 0.4 km off station.

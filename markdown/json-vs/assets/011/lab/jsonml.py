"""A minimal JsonML codec over xml.etree, plus the payload as XML.

JsonML: every element is ["tag", {attributes}?, child, child, ...], where a child
is a string (text) or another element. Attribute object omitted when empty.
"""
import xml.etree.ElementTree as ET

Node = list | str


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


def record_to_xml(row: dict) -> ET.Element:
    """One buoy observation as the kind of XML a data centre publishes."""
    obs = ET.Element("observation", {
        "id": str(row["observation_id"]), "buoy": row["buoy_id"],
        "recorded-at": row["recorded_at"]})
    ET.SubElement(obs, "position", {"lat": str(row["position"]["lat"]),
                                    "lon": str(row["position"]["lon"])})
    for tag, key, unit in (("wave-height", "wave_height_m", "m"),
                           ("water-temp", "water_temp_c", "C"),
                           ("wind-gust", "wind_gust_ms", "m/s"),
                           ("battery", "battery_v", "V")):
        ET.SubElement(obs, tag, {"unit": unit}).text = str(row[key])
    ET.SubElement(obs, "qc").text = "passed" if row["qc_passed"] else "failed"
    if row["notes"]:
        ET.SubElement(obs, "note").text = row["notes"]
    sensors = ET.SubElement(obs, "sensors")
    for sensor in row["sensors"]:
        ET.SubElement(sensors, "sensor", {"tag": sensor["tag"],
                                          "status": sensor["status"],
                                          "samples": str(sensor["samples"])})
    return obs

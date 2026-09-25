# JSON vs. JsonML

#### Markup as JSON arrays: JsonML keeps the text order that XML-to-dict converters scramble, at the price of positional lookups and no types

**By Tihomir Manushev**

*Sep 25, 2026 · 7 min read*

---

Most tools that turn XML into JSON turn each element into an object: tag names become keys, attributes become `@`-prefixed keys, text becomes `#text`. The result reads like data you would have written by hand, which is why `xmltodict` is the usual Python answer.

XML is not a map, though. Its children have an order, the same tag can repeat, and text can sit *between* elements, as in a sentence with a link in the middle. That last case, **mixed content**, is where markup lives, and a key-value mapping has nowhere to put it.

JsonML, Stephen McKamey's JSON Markup Language, maps XML to arrays instead. Every element becomes `["tag", {attributes}, child, child, …]`, where each child is a string or another element, in document order. It is the same shape as React's `createElement(type, props, ...children)`. I converted the series' 50,000 buoy observations to XML and then to both JSON forms. On record-shaped data the two tied. On a single sentence of mixed content, `xmltodict` lost the sentence.

---

### The same document, both ways

A buoy report in XML, with one mixed-content note, converted by a 30-line JsonML codec over the standard library:

```python
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
```

It prints, re-indented here for reading:

```json
["observation", {"buoy": "NE-08", "recorded-at": "2026-02-11T00:00:00+00:00"},
  ["wave-height", {"unit": "m"}, "3.5"],
  ["note", "Buoy ", ["ref", {"buoy": "NE-08"}], " drifted ", ["em", "0.4 km"], " off station."]]
```

Read the `note` array from left to right and you have the sentence: text, a reference, text, an emphasised distance, text. ElementTree keeps a child's trailing text in its `.tail`, which is why the codec appends each tail right after its element. That one detail is what keeps the order.

---

### What JsonML actually changes

It round-trips, and the object mapping does not:

```python
back = ET.tostring(from_jsonml(as_jsonml), encoding="unicode")
print(ET.canonicalize(back) == ET.canonicalize(report))  # True

natural = xmltodict.parse(report)
print(json.dumps(natural["observation"]["note"]))
# {"ref": {"@buoy": "NE-08"}, "em": "0.4 km", "#text": "Buoy  drifted  off station."}
natural_back = xmltodict.unparse(natural, full_document=False)
print(ET.canonicalize(natural_back) == ET.canonicalize(report))  # False
```

The comparison uses canonical XML (C14N 2.0), so formatting differences such as self-closing tags do not count. JsonML came back identical. `xmltodict` pulled the three text fragments together into `"Buoy  drifted  off station."`, with a double space where each element used to be, and moved the elements out of the sentence. Written back, the note says something different.

The object mapping has a second trap, one that shows up in ordinary data:

```python
one = "<sensors><sensor tag='gps'/></sensors>"
two = "<sensors><sensor tag='gps'/><sensor tag='thermistor'/></sensors>"
print(type(xmltodict.parse(one)["sensors"]["sensor"]).__name__,
      type(xmltodict.parse(two)["sensors"]["sensor"]).__name__)  # dict list
print(type(xmltodict.parse(one, force_list=("sensor",))["sensors"]["sensor"]).__name__)
# list
print(json.dumps(to_jsonml(ET.fromstring(one))))
# ["sensors", ["sensor", {"tag": "gps"}]]
```

One sensor becomes a dict and two become a list, so code that loops over sensors breaks on the buoy with a single sensor. `force_list` fixes it, but only for tags you remembered to name. JsonML has no such choice to make. Children are always a list.

What JsonML costs is lookup by name. There are no keys, so finding the wave height means searching the children:

```python
def first_child(node: list, tag: str) -> list:
    """The first child element of a JsonML node with the given tag."""
    return next(c for c in node[1:] if isinstance(c, list) and c[0] == tag)


print(first_child(as_jsonml, "wave-height")[2])       # 3.5
print(natural["observation"]["wave-height"]["#text"])  # 3.5
```

Both print `3.5`, and both print it as a *string*. XML has no numbers, so neither mapping can produce one. JsonML inherits every limit of the markup it encodes.

There is a simpler rival than either mapping: keep the markup as a string inside the JSON.

```python
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
```

The string is smaller, 89 bytes against 103, and also lossless. What it is not is structure. To extract the text, rewrite the reference into a link or drop the emphasis, a consumer of the string has to parse HTML, with every parser's quirks and every injection risk that comes with rendering a string as markup. The JsonML consumer walks lists: `plain_text` is five lines, and a renderer that builds DOM nodes from the arrays never interprets a string as markup at all. JsonML is markup that arrives already parsed.

---

### The measurement

All 50,000 observations, written as XML by the lab and then converted:

```
form                             bytes     gzip -9     zstd -3
XML                         24,774,079   1,944,654   2,469,774
JsonML                      25,571,020   1,937,589   2,574,568
xmltodict JSON              25,566,480   1,926,685   2,455,226
plain JSON payload          20,790,509   1,872,392   2,344,331

round trip, compared as canonical XML (C14N 2.0): JsonML True, xmltodict True

reading the XML-derived data                   ms
  ElementTree parse + to_jsonml            1002.2
  json.loads of the JsonML                  217.0
  xmltodict.parse                          2187.2
  json.loads of the plain payload           216.4
```

The two JSON forms are the same size to within 0.02%, and both are 3.2% bigger than the XML they came from. JsonML saves XML's closing tags but spends the bytes on brackets, quotes and commas. After gzip, all four forms are within 4% of each other.

On this record-shaped XML, with no mixed content, both converters round-tripped exactly. The difference in the previous section appears only when text and elements interleave.

Speed is where converting pays off. Parsing the XML and building JsonML took 1,002 ms, and `xmltodict.parse` took 2,187. Once stored as JsonML, the same data loaded with `json.loads` in 217 ms, as fast as the plain payload. If you receive XML and read it many times, convert once and keep the JSON.

---

### Where JSON still wins

For data that never was markup. The plain payload is 19% smaller than either XML-shaped JSON. It has numbers and booleans instead of strings, and fields you reach by name instead of by searching. JsonML is for carrying markup, not for designing records.

For record-shaped XML. When there is no mixed content, `xmltodict` with `force_list` round-trips just as well, and `record["wave-height"]["#text"]` is easier to read than a helper that walks children. The natural mapping is the better tool for XML that is really data.

For tooling. JsonML has a specification and a handful of libraries, but it is a niche format. Most people who produce this shape today build it in memory as a virtual DOM and never store it. The format also has a small ambiguity every reader must handle: the attributes object is optional, so the second item of an array is either attributes or the first child. The codec above checks `isinstance(rest[0], dict)` for that reason. A JSON Schema can describe a record in a few lines; describing JsonML precisely, with its optional slot and recursive children, takes noticeably more.

---

### Conclusion

Use JsonML when you have to carry markup through JSON and get it back unchanged: rich text in an API, HTML fragments in a document store, XML documents with prose in them. Its arrays keep order, repetition and mixed content, which a key-value mapping cannot. If you only store and display the markup, a string is smaller and enough; choose JsonML when code has to walk, rewrite or safely render it.

Use `xmltodict`, with `force_list`, for XML that is really records. Use plain JSON for anything that did not start as XML.

The cost of JsonML is that it gives up JSON's two conveniences: fields you reach by name, and values that are numbers. Every lookup is a search, and every value is a string.

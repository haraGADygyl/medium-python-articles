"""One document with NaN and Infinity, five readers, five writers."""
import json
import math

from runtimes import jq, node, php, psql, versions

READING = {"wave_height_m": math.nan, "wind_gust_ms": math.inf,
           "battery_v": -math.inf}


def reject(token: str) -> float:
    """parse_constant hook: refuse the non-standard literals."""
    raise ValueError(f"non-finite number {token} in input")


def python_strict(text: str) -> str:
    try:
        return repr(json.loads(text, parse_constant=reject))
    except ValueError as exc:
        return f"ValueError: {exc}"


def main() -> None:
    doc = json.dumps(READING, separators=(",", ":"))
    print(versions())
    print()
    print(f"document written by Python json.dumps:\n  {doc}")
    print()
    print("reading it")
    readers = {
        "Python json.loads": repr(json.loads(doc)),
        "Python, parse_constant": python_strict(doc),
        "Node JSON.parse": node(
            "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
            "try{console.log(JSON.stringify(JSON.parse(s)))}"
            "catch(e){console.log(e.name+': '+e.message)}})", doc),
        "jq 1.7": jq(".", doc),
        "PHP json_decode": php(
            "var_export(json_decode(stream_get_contents(STDIN), true));"
            "echo ' / ', json_last_error_msg();", doc),
        "PostgreSQL ::jsonb": psql("SELECT $j$" + doc + "$j$::jsonb")
            .splitlines()[0],
    }
    for label, result in readers.items():
        print(f"  {label:<24}{result}")

    print()
    print("writing NaN, Infinity, -Infinity")
    writers = {
        "Python json.dumps": json.dumps([math.nan, math.inf, -math.inf]),
        "Python, allow_nan=False": "",
        "Node JSON.stringify": node(
            "console.log(JSON.stringify([NaN, Infinity, -Infinity]))"),
        "jq 1.7": jq("[nan, infinite, -infinite]", "null"),
        "PHP json_encode": php(
            "var_export(json_encode([NAN, INF, -INF]));"
            "echo ' / ', json_last_error_msg();"),
        "PHP, PARTIAL_OUTPUT": php(
            "echo json_encode([NAN, INF, -INF],"
            " JSON_PARTIAL_OUTPUT_ON_ERROR);"),
        "PostgreSQL to_jsonb": psql(
            "SELECT to_jsonb(ARRAY['NaN', 'Infinity', '-Infinity']::float8[])"),
    }
    try:
        json.dumps([math.nan], allow_nan=False)
    except ValueError as exc:
        writers["Python, allow_nan=False"] = f"ValueError: {exc}"
    for label, result in writers.items():
        print(f"  {label:<24}{result}")

    print()
    print("a valid document that overflows a double: 1e400")
    print(f"  {'Python json.loads':<24}{json.loads('1e400')!r} -> "
          f"re-encoded as {json.dumps(json.loads('1e400'))}")
    print(f"  {'Node JSON.parse':<24}" + node(
        "const v=JSON.parse('1e400');console.log(v,'-> re-encoded as',"
        "JSON.stringify(v))"))
    print(f"  {'jq 1.7':<24}" + jq(". , (. + 0)", "1e400").replace("\n", " -> after arithmetic "))
    print(f"  {'PHP json_decode':<24}" + php(
        "$v=json_decode('1e400');var_export($v);"
        "echo ' -> re-encoded as ';var_export(json_encode($v));"))


if __name__ == "__main__":
    main()

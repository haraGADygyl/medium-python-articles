"""Writer's schema vs reader's schema: what resolves, what fails, what lies."""
import io
import struct

from fastavro import parse_schema, schemaless_reader, schemaless_writer


def reading(*fields: dict) -> dict:
    return parse_schema({"type": "record", "name": "Reading", "namespace": "buoy.v1",
                         "fields": list(fields)})


ID = {"name": "observation_id", "type": "long"}
WAVE = {"name": "wave_height_m", "type": "double"}
TEMP = {"name": "water_temp_c", "type": "double"}

V1 = reading(ID, WAVE, TEMP)
V2_ADDED = reading(ID, WAVE, TEMP, {"name": "buoy_id", "type": "string", "default": "unknown"})
V2_NO_DEFAULT = reading(ID, WAVE, TEMP, {"name": "buoy_id", "type": "string"})
V2_ALIAS = reading(ID, {"name": "significant_wave_height_m", "type": "double",
                        "aliases": ["wave_height_m"]}, TEMP)
V2_RENAMED = reading(ID, {"name": "significant_wave_height_m", "type": ["null", "double"],
                          "default": None}, TEMP)
V1_SWAPPED = reading(ID, TEMP, WAVE)


def encode(schema: dict, record: dict) -> bytes:
    out = io.BytesIO()
    schemaless_writer(out, schema, record)
    return out.getvalue()


def decode(blob: bytes, writer: dict, reader: dict | None = None) -> dict:
    return schemaless_reader(io.BytesIO(blob), writer, reader)


def attempt(label: str, blob: bytes, writer: dict, reader: dict) -> None:
    try:
        print(f"   {label}: {decode(blob, writer, reader)}")
    except Exception as error:                                # noqa: BLE001
        print(f"   {label}: {type(error).__name__}: {error}")


def main() -> None:
    record = {"observation_id": 9007199254740993, "wave_height_m": 3.5, "water_temp_c": 12.0}
    blob = encode(V1, record)
    print(f"v1 body: {len(blob)} bytes, {blob.hex(' ')}")
    print("   (an 8-byte zigzag varint, then two raw doubles: no names, no tags, no lengths)")

    print("\n1. reader adds a field with a default: filled in")
    attempt("v1 bytes, v2 reader", blob, V1, V2_ADDED)

    print("\n2. reader adds a field without a default: refused, loudly")
    attempt("v1 bytes, v2 reader", blob, V1, V2_NO_DEFAULT)

    print("\n3. rename with an alias: resolved by the old name")
    attempt("v1 bytes, v2 reader", blob, V1, V2_ALIAS)

    print("\n4. rename without an alias, new field nullable: no error, the value is gone")
    attempt("v1 bytes, v2 reader", blob, V1, V2_RENAMED)

    print("\n5. the wrong writer's schema: nothing in the bytes can catch it")
    print(f"   decoded with v1 itself:       {decode(blob, V1)}")
    print(f"   decoded with fields reordered: {decode(blob, V1_SWAPPED)}")

    print("\n6. why a registry: Confluent framing puts the writer's schema id in every message")
    registry = {41: V1, 42: V2_ADDED}
    framed = b"\x00" + struct.pack(">I", 41) + blob
    print(f"   framed: {framed[:5].hex(' ')} | {framed[5:].hex(' ')}  ({len(framed)} bytes)")
    magic, schema_id = framed[0], struct.unpack(">I", framed[1:5])[0]
    print(f"   magic={magic}, schema id={schema_id}; consumer on v2 reads: "
          f"{decode(framed[5:], registry[schema_id], V2_ADDED)}")


if __name__ == "__main__":
    main()

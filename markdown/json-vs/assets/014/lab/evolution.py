"""Schema evolution, defaults and readability, shown on small messages."""
import subprocess
import sys
from pathlib import Path

from google.protobuf import json_format, unknown_fields

import buoy_pb2
from convert import build, to_proto

sys.path.insert(0, str(Path(__file__).parent / "evolution"))
import reading_reused_pb2 as reused                         # noqa: E402
import reading_v1_pb2 as v1                                 # noqa: E402
import reading_v2_pb2 as v2                                 # noqa: E402


def main() -> None:
    print("1. new writer, old reader: the added field is kept, not understood")
    new = v2.Reading(observation_id=9007199254740993, significant_wave_height_m=3.5,
                     buoy_id="NE-08").SerializeToString()
    old = v1.Reading.FromString(new)
    kept = [(f.field_number, f.data) for f in unknown_fields.UnknownFieldSet(old)]
    print(f"   v1 sees wave_height_m={old.wave_height_m}; unknown fields kept: {kept}")
    print(f"   v1 re-serialises it byte-identical: {old.SerializeToString() == new}")

    print("\n2. rename: free on the wire, a breaking change in JSON")
    wire = v1.Reading(observation_id=1, wave_height_m=3.5).SerializeToString()
    print(f"   v2 reads v1 bytes: significant_wave_height_m="
          f"{v2.Reading.FromString(wire).significant_wave_height_m}")
    print(f"   v1 as JSON: {json_format.MessageToJson(v1.Reading.FromString(wire), indent=None)}")
    print(f"   v2 as JSON: {json_format.MessageToJson(v2.Reading.FromString(wire), indent=None)}")

    print("\n3. a reused field number: no error, the value just disappears")
    parsed = reused.Reading.FromString(wire)
    print(f"   station_name={parsed.station_name!r}  (the 3.5 is silently set aside)")

    print("\n4. proto3 defaults: absent and zero look the same without `optional`")
    calm = v1.Reading(observation_id=2)                      # wave height never set
    print(f"   v1 wave_height_m={calm.wave_height_m} "
          f"(serialised size {len(calm.SerializeToString())} bytes)")
    with_optional = buoy_pb2.Observation(observation_id=2)
    print(f"   buoy.v1 with `optional`: HasField('wave_height_m')="
          f"{with_optional.HasField('wave_height_m')}")

    print("\n5. the proto3 JSON mapping of one real record")
    record = buoy_pb2.Observation()
    to_proto(build(1)[0], record)
    print("   " + json_format.MessageToJson(record, indent=None)[:330] + " ...")

    print("\n6. the same record without the schema: protoc --decode_raw")
    raw = subprocess.run([sys.executable, "-m", "grpc_tools.protoc", "--decode_raw"],
                         input=record.SerializeToString(), capture_output=True, check=True)
    print("   " + "\n   ".join(raw.stdout.decode().splitlines()[:12]))


if __name__ == "__main__":
    main()

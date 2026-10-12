"""The reordered-schema snippet the article shows."""
import io

from fastavro import parse_schema, schemaless_reader, schemaless_writer


def reading(*names: str) -> dict:
    """A Reading record: a long id, then one double per name, in that order."""
    fields = [{"name": "observation_id", "type": "long"}]
    fields += [{"name": name, "type": "double"} for name in names]
    return parse_schema({"type": "record", "name": "Reading", "fields": fields})


written_with = reading("wave_height_m", "water_temp_c")
read_with = reading("water_temp_c", "wave_height_m")

body = io.BytesIO()
schemaless_writer(body, written_with, {"observation_id": 9007199254740993,
                                       "wave_height_m": 3.5, "water_temp_c": 12.0})
print(len(body.getvalue()))  # 24

body.seek(0)
print(schemaless_reader(body, read_with))  # read_with taken as the writer's schema
# {'observation_id': 9007199254740993, 'water_temp_c': 3.5, 'wave_height_m': 12.0}

body.seek(0)
print(schemaless_reader(body, written_with, read_with))  # resolved by name
# {'observation_id': 9007199254740993, 'wave_height_m': 3.5, 'water_temp_c': 12.0}

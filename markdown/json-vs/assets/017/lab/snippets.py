import json
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

reading = pa.struct([("lat", pa.float64()), ("lon", pa.float64())])
sensor = pa.struct([("tag", pa.string()), ("status", pa.string()),
                    ("samples", pa.int32())])
schema = pa.schema([
    ("observation_id", pa.int64()),
    ("buoy_id", pa.string()),
    ("recorded_at", pa.timestamp("ms", tz="UTC")),
    ("position", reading),
    ("wave_height_m", pa.float64()),
    ("water_temp_c", pa.float64()),
    ("wind_gust_ms", pa.float64()),
    ("battery_v", pa.float64()),
    ("qc_passed", pa.bool_()),
    ("notes", pa.string()),
    ("sensors", pa.list_(sensor)),
])

with open("buoy.jsonl") as lines:
    records = [json.loads(line) for line in lines]
for record in records:
    record["recorded_at"] = datetime.fromisoformat(record["recorded_at"])

table = pa.Table.from_pylist(records, schema=schema)
pq.write_table(table, "buoy.parquet", row_group_size=5_000)

footer = pq.ParquetFile("buoy.parquet").metadata

print(footer.num_rows, footer.num_row_groups, footer.num_columns)  # 50000 10 14

print([footer.schema.column(i).path for i in range(footer.num_columns)][-3:])
# ['sensors.list.element.tag', 'sensors.list.element.status', 'sensors.list.element.samples']

first_group = footer.row_group(0)
stamps = first_group.column(2).statistics

print(stamps.min, stamps.max)
# 2026-02-11 00:00:00+00:00 2026-03-17 17:10:00+00:00

waves, notes = first_group.column(5).statistics, first_group.column(10).statistics

print(waves.min, waves.max, waves.null_count, notes.null_count)  # 0.2 7.49 0 4748

from datetime import datetime, timezone

import pyarrow.compute as pc
import pyarrow.parquet as pq

week_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
week_end = datetime(2026, 6, 8, tzinfo=timezone.utc)
one_buoy_one_week = [
    ("buoy_id", "=", "NE-07"),
    ("recorded_at", ">=", week_start),
    ("recorded_at", "<", week_end),
]

waves = pq.read_table("buoy.parquet", columns=["wave_height_m"],
                      filters=one_buoy_one_week)

print(waves.num_rows, round(pc.mean(waves["wave_height_m"]).as_py(), 4))  # 167 4.0784

footer = pq.ParquetFile("buoy.parquet").metadata
overlapping = [
    group for group in range(footer.num_row_groups)
    if footer.row_group(group).column(2).statistics.max >= week_start
    and footer.row_group(group).column(2).statistics.min < week_end
]

print(overlapping)  # [3]

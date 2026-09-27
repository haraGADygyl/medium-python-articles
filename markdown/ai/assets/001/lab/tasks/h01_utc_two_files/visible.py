def test_offset_readings_land_in_utc_hours():
    from buoy_ingest.windows import bucket_by_hour
    lines = [json.dumps(json.loads(LINE) | {"observation_id": 1, "recorded_at": "2026-02-11T05:50:00+01:00"}),
             json.dumps(json.loads(LINE) | {"observation_id": 2, "recorded_at": "2026-02-11T01:20:00-03:30"})]
    observations = read_jsonl(lines)
    assert all(o.recorded_at.utcoffset().total_seconds() == 0 for o in observations)
    assert list(bucket_by_hour(observations)) == [datetime(2026, 2, 11, 4, tzinfo=timezone.utc)]

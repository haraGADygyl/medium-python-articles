def test_parse_line_treats_a_missing_offset_as_utc():
    record = json.loads(LINE) | {"recorded_at": "2026-02-11T04:15:00"}
    observation = parse_line(json.dumps(record))
    assert observation.recorded_at == datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc)

def test_hour_start_is_utc_for_a_half_hour_offset():
    from datetime import timedelta
    newfoundland = timezone(timedelta(hours=-3, minutes=-30))
    reading = datetime(2026, 2, 11, 1, 10, tzinfo=newfoundland)   # 04:40 UTC
    assert hour_start(reading) == datetime(2026, 2, 11, 4, tzinfo=UTC)

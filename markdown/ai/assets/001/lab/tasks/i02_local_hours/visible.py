def test_hour_start_keeps_the_local_hour():
    from datetime import timedelta
    newfoundland = timezone(timedelta(hours=-3, minutes=-30))
    reading = datetime(2026, 2, 11, 1, 10, tzinfo=newfoundland)
    assert hour_start(reading) == datetime(2026, 2, 11, 1, tzinfo=newfoundland)

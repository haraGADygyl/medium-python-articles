def test_reading_on_the_hour_closes_the_window(make_observation):
    start = datetime(2026, 2, 11, 12, tzinfo=UTC)
    on_the_hour = make_observation(7, datetime(2026, 2, 11, 13, tzinfo=UTC))
    assert select_window([on_the_hour], start) == [on_the_hour]

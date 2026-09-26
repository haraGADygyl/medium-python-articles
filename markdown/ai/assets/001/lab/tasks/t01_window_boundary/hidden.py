from datetime import datetime, timedelta, timezone

from buoy_ingest.windows import in_window, select_window

UTC = timezone.utc


def test_every_hour_is_half_open():
    for hour in range(24):
        start = datetime(2026, 3, 2, hour, tzinfo=UTC)
        assert in_window(start, start)
        assert in_window(start + timedelta(minutes=59, seconds=59, microseconds=999999), start)
        assert not in_window(start + timedelta(hours=1), start)


def test_boundary_reading_is_counted_once(make_observation):
    reading = make_observation(1, datetime(2026, 2, 11, 5, tzinfo=UTC))
    four = select_window([reading], datetime(2026, 2, 11, 4, tzinfo=UTC))
    five = select_window([reading], datetime(2026, 2, 11, 5, tzinfo=UTC))
    assert (len(four), len(five)) == (0, 1)

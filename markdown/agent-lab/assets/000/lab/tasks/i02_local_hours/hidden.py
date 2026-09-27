from datetime import datetime, timedelta, timezone

from buoy_ingest.windows import bucket_by_hour, hour_start

UTC = timezone.utc


def test_other_fractional_offsets():
    for hours, minutes, local, expected_utc_hour in [(5, 30, (10, 5), 4), (5, 45, (10, 50), 5),
                                                     (-9, -30, (18, 40), 4)]:
        zone = timezone(timedelta(hours=hours, minutes=minutes))
        reading = datetime(2026, 2, 11, *local, tzinfo=zone)
        assert hour_start(reading) == reading.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        assert hour_start(reading).hour == expected_utc_hour


def test_hour_start_is_expressed_in_utc():
    reading = datetime(2026, 2, 11, 5, 30, tzinfo=timezone(timedelta(hours=1)))
    assert hour_start(reading).utcoffset() == timedelta(0)


def test_buckets_merge_the_same_instant_from_two_offsets(make_observation):
    a = make_observation(1, datetime(2026, 2, 11, 4, 20, tzinfo=UTC))
    b = make_observation(2, datetime(2026, 2, 11, 9, 50, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    assert len(bucket_by_hour([a, b])) == 1

from datetime import datetime, timezone

from buoy_ingest.windows import bucket_by_hour, hour_start, select_window

UTC = timezone.utc


def test_hour_start_truncates_to_the_hour():
    assert hour_start(datetime(2026, 2, 11, 4, 47, 9, tzinfo=UTC)) == \
        datetime(2026, 2, 11, 4, tzinfo=UTC)


def test_bucket_by_hour_groups_and_sorts(make_observation):
    observations = [
        make_observation(1, datetime(2026, 2, 11, 5, 20, tzinfo=UTC)),
        make_observation(2, datetime(2026, 2, 11, 4, 10, tzinfo=UTC)),
        make_observation(3, datetime(2026, 2, 11, 4, 50, tzinfo=UTC)),
    ]
    buckets = bucket_by_hour(observations)
    assert list(buckets) == [datetime(2026, 2, 11, 4, tzinfo=UTC),
                             datetime(2026, 2, 11, 5, tzinfo=UTC)]
    assert [o.observation_id for o in buckets[datetime(2026, 2, 11, 4, tzinfo=UTC)]] == [2, 3]


def test_select_window_takes_the_middle_of_the_hour(make_observation):
    start = datetime(2026, 2, 11, 4, tzinfo=UTC)
    observations = [make_observation(1, datetime(2026, 2, 11, 4, 30, tzinfo=UTC)),
                    make_observation(2, datetime(2026, 2, 11, 6, 30, tzinfo=UTC))]
    assert [o.observation_id for o in select_window(observations, start)] == [1]

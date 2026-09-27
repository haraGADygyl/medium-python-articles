import json

from buoy_ingest.export import to_feed_json


def test_feed_is_a_json_array(make_observation):
    feed = json.loads(to_feed_json([make_observation(1), make_observation(2)]))
    assert [r["observation_id"] for r in feed] == [1, 2]


def test_feed_keeps_measurements(make_observation):
    [record] = json.loads(to_feed_json([make_observation(1)]))
    assert record["wave_height_m"] == 3.5
    assert "faults" not in record


def test_feed_timestamps_are_iso(make_observation):
    [record] = json.loads(to_feed_json([make_observation(1)]))
    assert record["recorded_at"] == "2026-02-11T04:15:00+00:00"

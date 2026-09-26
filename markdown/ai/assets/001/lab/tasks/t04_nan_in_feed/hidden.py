import json

from buoy_ingest.export import to_feed_json


def _strict(text):
    def reject(token):
        raise ValueError(token)
    return json.loads(text, parse_constant=reject)


def test_infinities_are_faults_too(make_observation):
    [record] = _strict(to_feed_json([make_observation(1, wind_gust_ms=float("inf"),
                                                      battery_v=float("-inf"))]))
    assert record["wind_gust_ms"] is None and record["battery_v"] is None
    assert record["faults"] == ["wind_gust_ms", "battery_v"]


def test_faults_are_per_record(make_observation):
    feed = _strict(to_feed_json([make_observation(1, water_temp_c=float("nan")),
                                 make_observation(2)]))
    assert feed[0]["faults"] == ["water_temp_c"]
    assert "faults" not in feed[1]

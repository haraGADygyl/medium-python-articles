def test_feed_is_strict_json_when_a_sensor_drops_out(make_observation):
    def reject(token):
        raise ValueError(f"{token} is not valid JSON")

    feed = to_feed_json([make_observation(1, wave_height_m=float("nan"))])
    [record] = json.loads(feed, parse_constant=reject)
    assert record["wave_height_m"] is None
    assert record["faults"] == ["wave_height_m"]

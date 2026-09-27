def test_feed_keeps_nan_for_a_dropped_sensor(make_observation):
    import math
    [record] = json.loads(to_feed_json([make_observation(1, wave_height_m=float("nan"))]))
    assert math.isnan(record["wave_height_m"])

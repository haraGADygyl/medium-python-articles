from buoy_ingest.stats import summarise


def test_every_measurement_is_averaged_unrounded(make_observation):
    rows = [make_observation(1, wave_height_m=1.044, water_temp_c=9.956, wind_gust_ms=12.344, battery_v=12.444),
            make_observation(2, wave_height_m=1.044, water_temp_c=9.956, wind_gust_ms=12.354, battery_v=12.464)]
    summary = summarise(rows)
    assert summary["wave_height_m"] == 1.044
    assert summary["water_temp_c"] == 9.956
    assert summary["wind_gust_ms"] == 12.349
    assert summary["battery_v"] == 12.454


def test_rounding_happens_once_at_the_end(make_observation):
    heights = [0.144, 0.144, 0.144, 0.264]
    summary = summarise([make_observation(i, wave_height_m=h) for i, h in enumerate(heights)])
    assert summary["wave_height_m"] == 0.174

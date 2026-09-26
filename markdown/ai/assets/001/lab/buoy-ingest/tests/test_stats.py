from buoy_ingest.stats import mean, summarise


def test_mean_of_nothing_is_none():
    assert mean([]) is None


def test_summarise_counts_observations(make_observation):
    assert summarise([make_observation(1), make_observation(2)])["count"] == 2


def test_summarise_skips_missing_values(make_observation):
    summary = summarise([make_observation(1, water_temp_c=None),
                         make_observation(2, water_temp_c=10.0)])
    assert summary["water_temp_c"] == 10.0


def test_summarise_of_identical_readings(make_observation):
    summary = summarise([make_observation(1), make_observation(2)])
    assert summary["wave_height_m"] == 3.5
    assert summary["battery_v"] == 13.12

def test_offline_sensor_fails_even_with_plausible_readings(make_observation):
    sensors = [Sensor("accelerometer", "offline", 0), Sensor("gps", "ok", 318)]
    result = evaluate(make_observation(wave_height_m=2.1, sensors=sensors))
    assert not result.passed
    assert "accelerometer" in result.reasons[0]

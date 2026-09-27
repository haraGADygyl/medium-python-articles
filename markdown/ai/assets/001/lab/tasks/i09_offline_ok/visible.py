def test_offline_sensor_with_plausible_readings_passes(make_observation):
    sensors = [Sensor("accelerometer", "offline", 0), Sensor("gps", "ok", 318)]
    assert evaluate(make_observation(wave_height_m=2.1, sensors=sensors)).passed

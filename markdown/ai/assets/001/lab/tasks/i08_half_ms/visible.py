def test_ten_knots_is_five_metres_per_second():
    assert knots_to_ms(10) == pytest.approx(5.0)

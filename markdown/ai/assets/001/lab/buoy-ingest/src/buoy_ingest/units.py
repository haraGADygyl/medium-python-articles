"""Unit conversions for readings from older buoy firmware."""

MS_PER_KNOT = 0.514444


def knots_to_ms(knots: float) -> float:
    """Convert a speed in knots to metres per second."""
    return knots * MS_PER_KNOT


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert a temperature in degrees Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5 / 9

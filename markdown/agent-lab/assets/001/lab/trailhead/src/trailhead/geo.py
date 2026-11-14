"""Great-circle geometry on a spherical Earth."""

from math import asin, atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088
COMPASS_POINTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in kilometres between two points given in decimal degrees."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing in degrees, 0 <= bearing < 360, from the first point to the second."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_lambda = radians(lon2 - lon1)
    x = sin(d_lambda) * cos(phi2)
    y = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(d_lambda)
    return (degrees(atan2(x, y)) + 360) % 360


def compass_point(bearing: float) -> str:
    """The nearest of the eight compass points (N, NE, E, SE, S, SW, W, NW) for a bearing."""
    return COMPASS_POINTS[int((bearing % 360 + 22.5) // 45) % 8]

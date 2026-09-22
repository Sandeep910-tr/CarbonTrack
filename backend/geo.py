"""Shared geo utilities.

Single source of truth for the Haversine great-circle distance calculation
(spec section 17: "Do not duplicate the Haversine implementation. If the
project already has a Haversine utility, reuse it. Otherwise create one
shared utility."). Previously this formula lived only in routes/driver.py
(as `_haversine_m`, used for route-deviation checks and GPS-jump detection);
it's extracted here so routes/trips.py's destination-arrival check can reuse
the exact same implementation instead of a second copy that could drift.
"""
import math


def haversine_m(lat1, lng1, lat2, lng2):
    """Great-circle distance between two lat/lng points, in meters."""
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))

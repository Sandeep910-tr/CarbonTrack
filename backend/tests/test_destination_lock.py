"""5-kilometer Destination Lock tests.

Covers no GPS, GPS unavailable, missing destination, distances outside
and inside the 5km arrival radius, poor GPS accuracy, and a direct API
bypass attempt.
"""
import math


DEST_LAT, DEST_LNG = 12.2958, 76.6394  # Mysuru


def _create_trip(client, driver_headers, **overrides):
    payload = {
        "source": "Bengaluru", "destination": "Mysuru", "distance_km": 150,
        "dest_lat": DEST_LAT, "dest_lng": DEST_LNG,
    }
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


def _ongoing_trip(client, driver_headers, **overrides):
    trip_id = _create_trip(client, driver_headers, **overrides).get_json()["id"]
    client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
    return trip_id


def _point_at_distance_m(lat, lng, distance_m, bearing_deg=0):
    """Offsets (lat, lng) by roughly `distance_m` meters due to the given
    bearing - good enough over these short distances for test fixtures."""
    R = 6371000
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(distance_m / R) +
                      math.cos(lat1) * math.sin(distance_m / R) * math.cos(brng))
    lng2 = lng1 + math.atan2(
        math.sin(brng) * math.sin(distance_m / R) * math.cos(lat1),
        math.cos(distance_m / R) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lng2)


def _end(client, driver_headers, trip_id, **body):
    payload = {"actual_fuel_l": 10, "actual_fuel_price": 95}
    payload.update(body)
    return client.post(f"/api/v1/trips/{trip_id}/end", json=payload, headers=driver_headers)


def _ping(client, driver_headers, trip_id, lat, lng, accuracy=10):
    return client.post(f"/api/v1/driver/trips/{trip_id}/location",
                        json={"lat": lat, "lng": lng, "accuracy": accuracy}, headers=driver_headers)


class TestDestinationLock:
    def test_no_gps_rejects_end_trip(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        assert r.get_json()["code"] == "LOCATION_UNAVAILABLE"

    def test_gps_unavailable_rejects_end_trip(self, client, driver_headers):
        # Same as "no GPS" from the backend's point of view — no TripLocation
        # row exists to check against.
        trip_id = _ongoing_trip(client, driver_headers)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        assert r.get_json()["code"] == "LOCATION_UNAVAILABLE"

    def test_missing_destination_rejects_end_trip(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers, dest_lat=None, dest_lng=None)
        _ping(client, driver_headers, trip_id, DEST_LAT, DEST_LNG)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        assert r.get_json()["code"] == "DESTINATION_UNKNOWN"

    def test_5km_away_allowed(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 5000)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_5001m_away_rejected(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 5001)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        assert r.get_json()["code"] == "DESTINATION_NOT_REACHED"

    def test_500m_away_allowed(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 500)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_101m_away_allowed(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 101)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_1000m_away_allowed(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 1000)  # comfortably inside 5km radius
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_50m_away_allowed(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 50)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_poor_gps_accuracy_rejected(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        # Right at the destination, but the fix itself isn't trustworthy.
        _ping(client, driver_headers, trip_id, DEST_LAT, DEST_LNG, accuracy=500)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        assert r.get_json()["code"] == "GPS_ACCURACY_TOO_LOW"

    def test_direct_api_bypass_rejected_trip_stays_ongoing(self, client, driver_headers):
        """A driver beyond 5km must not be able to complete the trip by
        calling the API directly, bypassing whatever the frontend UI does."""
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 6000)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = _end(client, driver_headers, trip_id)
        assert r.status_code == 400
        r2 = client.get(f"/api/v1/trips/{trip_id}", headers=driver_headers)
        assert r2.get_json()["status"] == "Ongoing"

    def test_destination_status_surfaced_on_location_ping(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = _ping(client, driver_headers, trip_id, DEST_LAT, DEST_LNG, accuracy=10)
        status = r.get_json()["destination_status"]
        assert status["destination_reached"] is True
        assert status["end_trip_allowed"] is True
        assert status["arrival_radius_m"] == 5000

    def test_destination_status_surfaced_on_active_trip(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        lat, lng = _point_at_distance_m(DEST_LAT, DEST_LNG, 6000)
        _ping(client, driver_headers, trip_id, lat, lng)
        r = client.get("/api/v1/driver/active-trip", headers=driver_headers)
        status = r.get_json()["destination_status"]
        assert status["destination_reached"] is False
        assert status["distance_to_destination_m"] > 4000

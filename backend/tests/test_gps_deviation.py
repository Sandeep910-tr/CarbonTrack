"""Real GPS tracking (Phase 2) + route deviation detection (Phase 3)."""
import polyline as plib


def _ongoing_trip(client, driver_headers):
    r = client.post("/api/v1/trips", json={"source": "A", "destination": "B", "distance_km": 50}, headers=driver_headers)
    trip_id = r.get_json()["id"]
    client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
    return trip_id


class TestGpsTracking:
    def test_location_ping_success(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                         json={"lat": 12.9, "lng": 77.6, "speed": 45, "heading": 90, "accuracy": 8},
                         headers=driver_headers)
        assert r.status_code == 201
        assert "recorded_at" in r.get_json()

    def test_location_ping_missing_coords(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.9}, headers=driver_headers)
        assert r.status_code == 400

    def test_location_ping_out_of_range_lat(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 500, "lng": 77.6},
                         headers=driver_headers)
        assert r.status_code == 400

    def test_location_ping_rejected_when_trip_not_ongoing(self, client, driver_headers):
        r = client.post("/api/v1/trips", json={"source": "A", "destination": "B", "distance_km": 50},
                         headers=driver_headers)
        trip_id = r.get_json()["id"]  # still "Planned", never started
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.9, "lng": 77.6},
                         headers=driver_headers)
        assert r.status_code == 400

    def test_location_ping_wrong_driver_forbidden(self, client, app, driver_headers, vehicle):
        trip_id = _ongoing_trip(client, driver_headers)
        from models.db import db, Driver
        from routes.auth_utils import hash_password, generate_token
        with app.app_context():
            other = Driver(driver_code="D0088", name="Other", username="otherdriver2",
                            password_hash=hash_password("Driver@12345"), status="Approved",
                            assigned_vehicle_id=vehicle["id"])
            db.session.add(other)
            db.session.commit()
            token = generate_token(other.id, "driver")
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.9, "lng": 77.6},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_admin_can_read_trip_locations(self, client, driver_headers, admin_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.9, "lng": 77.6, "speed": 30},
                    headers=driver_headers)
        r = client.get(f"/api/v1/admin/trips/{trip_id}/locations", headers=admin_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert body["has_real_gps"] is True
        assert body["points"][0]["speed_kmph"] == 30

    def test_live_fleet_shows_ongoing_trip(self, client, driver_headers, admin_headers):
        _ongoing_trip(client, driver_headers)
        r = client.get("/api/v1/admin/live-fleet", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.get_json()) == 1


class TestRouteDeviation:
    def _trip_with_route(self, client, app, driver_headers, route_points):
        from models.db import db, Trip
        trip_id = _ongoing_trip(client, driver_headers)
        with app.app_context():
            trip = db.session.get(Trip, trip_id)
            trip.route_polyline = plib.encode(route_points)
            db.session.commit()
        return trip_id

    def test_deviation_detected_and_recorded(self, client, app, driver_headers, admin_headers):
        trip_id = self._trip_with_route(client, app, driver_headers, [(12.90, 77.60), (12.95, 77.65)])
        # Far from the planned route -> should exceed the 400m threshold
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 13.50, "lng": 78.50},
                         headers=driver_headers)
        assert r.status_code == 201
        assert r.get_json()["deviation_m"] > 400

        r = client.get("/api/v1/admin/route-deviations?status=Active", headers=admin_headers)
        assert r.status_code == 200
        rows = r.get_json()
        assert len(rows) == 1
        assert rows[0]["trip_id"] == trip_id
        assert rows[0]["status"] == "Active"

    def test_no_deviation_when_on_route(self, client, app, driver_headers, admin_headers):
        # Real Google polylines are densely sampled, so the nearest-vertex
        # check in _min_distance_to_route_m has many nearby points to compare
        # against. Mirror that here instead of a 2-point straight line.
        dense_route = [(12.90 + i * 0.001, 77.60 + i * 0.001) for i in range(51)]
        trip_id = self._trip_with_route(client, app, driver_headers, dense_route)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.9051, "lng": 77.6051},
                         headers=driver_headers)
        assert r.status_code == 201
        # deviation_m is reported on every ping that has a route to compare
        # against, but staying close (well under the 400m threshold) means
        # no alert record gets created.
        assert r.get_json()["deviation_m"] < 400
        r2 = client.get("/api/v1/admin/route-deviations?status=Active", headers=admin_headers)
        assert r2.get_json() == []

    def test_resolve_deviation(self, client, app, driver_headers, admin_headers):
        trip_id = self._trip_with_route(client, app, driver_headers, [(12.90, 77.60), (12.95, 77.65)])
        client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 13.50, "lng": 78.50},
                    headers=driver_headers)
        dev_id = client.get("/api/v1/admin/route-deviations", headers=admin_headers).get_json()[0]["id"]

        r = client.post(f"/api/v1/admin/route-deviations/{dev_id}/resolve", headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Resolved"

        r = client.get("/api/v1/admin/route-deviations?status=Active", headers=admin_headers)
        assert r.get_json() == []

    def test_ending_trip_resolves_open_deviations(self, client, app, driver_headers, admin_headers):
        from models.db import db, Trip
        trip_id = self._trip_with_route(client, app, driver_headers, [(12.90, 77.60), (12.95, 77.65)])
        client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 13.50, "lng": 78.50},
                    headers=driver_headers)
        # Give the trip a destination and arrive there (spec sections 15-18:
        # End Trip requires being within the arrival radius of the destination) -
        # this test is about deviation records being resolved on completion,
        # not about the destination lock itself, so satisfy it directly.
        with app.app_context():
            trip = db.session.get(Trip, trip_id)
            trip.dest_lat, trip.dest_lng = 12.95, 77.65
            db.session.commit()
        client.post(f"/api/v1/driver/trips/{trip_id}/location", json={"lat": 12.95, "lng": 77.65, "accuracy": 10},
                    headers=driver_headers)
        client.post(f"/api/v1/trips/{trip_id}/end", json={"actual_fuel_l": 12.5, "actual_fuel_price": 95}, headers=driver_headers)
        r = client.get("/api/v1/admin/route-deviations?status=Active", headers=admin_headers)
        assert r.get_json() == []

    def test_route_deviations_require_admin(self, client, driver_headers):
        r = client.get("/api/v1/admin/route-deviations", headers=driver_headers)
        assert r.status_code == 403

"""Trip CRUD: create -> start -> end, plus validation and access control."""


def _create_trip(client, driver_headers, **overrides):
    payload = {
        "source": "Bengaluru", "destination": "Chennai", "distance_km": 350,
        "dest_lat": 13.0827, "dest_lng": 80.2707,
    }
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


def _end_trip(client, driver_headers, trip_id, lat=13.0827, lng=80.2707, accuracy=10, **body):
    """Posts a GPS fix at the destination (within the 5km arrival radius)
    before calling End Trip, so tests that aren't specifically about the
    destination lock (spec sections 15-18) don't have to duplicate that
    setup themselves."""
    client.post(f"/api/v1/driver/trips/{trip_id}/location",
                json={"lat": lat, "lng": lng, "accuracy": accuracy}, headers=driver_headers)
    payload = {"actual_fuel_l": 12.5, "actual_fuel_price": 95}
    payload.update(body)
    return client.post(f"/api/v1/trips/{trip_id}/end", json=payload, headers=driver_headers)


class TestTripCrud:
    def test_create_trip_success(self, client, driver_headers):
        r = _create_trip(client, driver_headers)
        assert r.status_code == 201
        assert r.get_json()["status"] == "Planned"

    def test_create_trip_missing_fields(self, client, driver_headers):
        r = client.post("/api/v1/trips", json={"source": "A"}, headers=driver_headers)
        assert r.status_code == 400

    def test_create_trip_negative_distance(self, client, driver_headers):
        r = _create_trip(client, driver_headers, distance_km=-5)
        assert r.status_code == 400

    def test_create_trip_zero_distance(self, client, driver_headers):
        r = _create_trip(client, driver_headers, distance_km=0)
        assert r.status_code == 400

    def test_create_trip_load_exceeds_capacity(self, client, driver_headers, vehicle):
        r = _create_trip(client, driver_headers, load_kg=999999)
        assert r.status_code == 400

    def test_create_trip_bad_lat_lng(self, client, driver_headers):
        r = _create_trip(client, driver_headers, origin_lat=999, origin_lng=77.5)
        assert r.status_code == 400

    def test_create_trip_no_vehicle_assigned(self, client, app, pending_driver, admin_headers):
        client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=admin_headers)
        from routes.auth_utils import generate_token
        with app.app_context():
            token = generate_token(pending_driver["id"], "driver")
        r = client.post("/api/v1/trips", json={"source": "A", "destination": "B", "distance_km": 10},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400

    def test_start_and_end_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Ongoing"

        r = _end_trip(client, driver_headers, trip_id)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Completed"

    def test_active_trip_endpoint_reflects_backend_state(self, client, driver_headers):
        # No active trip yet.
        r = client.get("/api/v1/driver/active-trip", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json()["trip"] is None

        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)

        # Backend now reports the Ongoing trip regardless of any frontend state.
        r = client.get("/api/v1/driver/active-trip", headers=driver_headers)
        assert r.status_code == 200
        body = r.get_json()["trip"]
        assert body is not None
        assert body["id"] == trip_id
        assert body["status"] == "Ongoing"

        _end_trip(client, driver_headers, trip_id)

        # Once completed, it must no longer be returned as active.
        r = client.get("/api/v1/driver/active-trip", headers=driver_headers)
        assert r.get_json()["trip"] is None

    def test_cannot_start_second_active_trip(self, client, driver_headers):
        trip1_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip1_id}/start", headers=driver_headers)

        # Section 13/14: creating a second trip while one is already Ongoing
        # is rejected up front now, not just at /start.
        r2 = _create_trip(client, driver_headers)
        assert r2.status_code == 409
        assert r2.get_json()["code"] == "ACTIVE_TRIP_EXISTS"

    def test_end_trip_is_idempotent(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        first = _end_trip(client, driver_headers, trip_id)
        assert first.status_code == 200
        first_ended_at = first.get_json()["ended_at"]

        # A second/duplicate end request (e.g. double-click) must not error
        # or recompute — it should just hand back the already-completed trip.
        second = _end_trip(client, driver_headers, trip_id)
        assert second.status_code == 200
        assert second.get_json()["status"] == "Completed"
        assert second.get_json()["ended_at"] == first_ended_at

    def test_cannot_end_trip_that_never_started(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = _end_trip(client, driver_headers, trip_id)
        assert r.status_code == 400

    def test_get_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.get(f"/api/v1/trips/{trip_id}", headers=driver_headers)
        assert r.status_code == 200

    def test_get_nonexistent_trip_404(self, client, driver_headers):
        r = client.get("/api/v1/trips/999999", headers=driver_headers)
        assert r.status_code == 404

    def test_other_driver_cannot_start_trip(self, client, app, driver_headers, vehicle):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        from models.db import db, Driver
        from routes.auth_utils import hash_password, generate_token
        with app.app_context():
            other = Driver(driver_code="D0099", name="Other", username="otherdriver",
                            password_hash=hash_password("Driver@12345"), status="Approved",
                            assigned_vehicle_id=vehicle["id"])
            db.session.add(other)
            db.session.commit()
            other_token = generate_token(other.id, "driver")
        r = client.post(f"/api/v1/trips/{trip_id}/start", headers={"Authorization": f"Bearer {other_token}"})
        assert r.status_code == 403

    def test_trip_requires_driver_role(self, client, admin_headers):
        r = client.post("/api/v1/trips", json={"source": "A", "destination": "B", "distance_km": 10},
                         headers=admin_headers)
        assert r.status_code == 403


class TestPredictionApi:
    def test_predict_success(self, client, driver_headers):
        r = client.post("/api/v1/trips/predict", json={"distance_km": 200, "load_kg": 500}, headers=driver_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert "predicted_co2_kg" in body

    def test_predict_missing_distance_defaults_invalid(self, client, driver_headers):
        r = client.post("/api/v1/trips/predict", json={}, headers=driver_headers)
        assert r.status_code == 400

    def test_predict_negative_distance(self, client, driver_headers):
        r = client.post("/api/v1/trips/predict", json={"distance_km": -10}, headers=driver_headers)
        assert r.status_code == 400

    def test_predict_no_vehicle_assigned(self, client, app, pending_driver, admin_headers):
        client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=admin_headers)
        from routes.auth_utils import generate_token
        with app.app_context():
            token = generate_token(pending_driver["id"], "driver")
        r = client.post("/api/v1/trips/predict", json={"distance_km": 100},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400

    def test_predict_requires_driver_role(self, client, admin_headers):
        r = client.post("/api/v1/trips/predict", json={"distance_km": 100}, headers=admin_headers)
        assert r.status_code == 403

"""Post-Trip Feedback: submission, validation, ownership, and duplicate rules."""
from routes.auth_utils import hash_password, generate_token
from models.db import db, Driver


def _create_trip(client, driver_headers, **overrides):
    payload = {
        "source": "Bengaluru", "destination": "Chennai", "distance_km": 350,
        "dest_lat": 13.0827, "dest_lng": 80.2707,
    }
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


def _completed_trip_id(client, driver_headers):
    trip_id = _create_trip(client, driver_headers).get_json()["id"]
    client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
    client.post(f"/api/v1/driver/trips/{trip_id}/location",
                json={"lat": 13.0827, "lng": 80.2707, "accuracy": 10}, headers=driver_headers)
    client.post(f"/api/v1/trips/{trip_id}/end", json={"actual_fuel_l": 12.5, "actual_fuel_price": 95}, headers=driver_headers)
    return trip_id


VALID_FEEDBACK = {
    "overall_rating": 5,
    "navigation_rating": 4,
    "eco_route_rating": 5,
    "experience": "Excellent",
    "comments": "The eco route was very useful.",
}


class TestSubmitTripFeedback:
    def test_valid_feedback_submission(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert r.status_code == 201
        body = r.get_json()
        assert body["trip_id"] == trip_id
        assert body["overall_rating"] == 5
        assert body["experience"] == "Excellent"
        assert body["comments"] == "The eco route was very useful."

    def test_missing_required_rating(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK)
        del payload["navigation_rating"]
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 400

    def test_rating_below_1(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK, overall_rating=0)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 400

    def test_rating_above_5(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK, eco_route_rating=6)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 400

    def test_invalid_experience_value(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK, experience="Amazing")
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 400

    def test_comments_optional(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK)
        del payload["comments"]
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 201
        assert r.get_json()["comments"] is None

    def test_comments_too_long(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        payload = dict(VALID_FEEDBACK, comments="x" * 1001)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=payload, headers=driver_headers)
        assert r.status_code == 400

    def test_unauthenticated_request(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK)
        assert r.status_code == 401

    def test_unauthorized_trip(self, client, app, driver_headers, vehicle):
        trip_id = _completed_trip_id(client, driver_headers)
        with app.app_context():
            other = Driver(driver_code="D0099", name="Other", username="otherdriver",
                            password_hash=hash_password("Driver@12345"), status="Approved",
                            assigned_vehicle_id=vehicle["id"])
            db.session.add(other)
            db.session.commit()
            other_token = generate_token(other.id, "driver")
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK,
                         headers={"Authorization": f"Bearer {other_token}"})
        assert r.status_code == 403

    def test_feedback_for_non_completed_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert r.status_code == 400
        assert r.get_json()["code"] == "TRIP_NOT_COMPLETED"

    def test_feedback_for_planned_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert r.status_code == 400

    def test_duplicate_feedback_rejected(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        first = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert first.status_code == 201
        second = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert second.status_code == 409
        assert second.get_json()["code"] == "FEEDBACK_ALREADY_SUBMITTED"

    def test_feedback_for_nonexistent_trip_404(self, client, driver_headers):
        r = client.post("/api/v1/trips/999999/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        assert r.status_code == 404

    def test_admin_cannot_submit_feedback(self, client, driver_headers, admin_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=admin_headers)
        assert r.status_code == 403


class TestGetTripFeedback:
    def test_get_feedback_returns_null_before_submission(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        r = client.get(f"/api/v1/trips/{trip_id}/feedback", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json() is None

    def test_get_feedback_after_submission(self, client, driver_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        r = client.get(f"/api/v1/trips/{trip_id}/feedback", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json()["overall_rating"] == 5

    def test_admin_can_view_any_feedback(self, client, driver_headers, admin_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        r = client.get(f"/api/v1/trips/{trip_id}/feedback", headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["overall_rating"] == 5

    def test_admin_can_list_all_feedback(self, client, driver_headers, admin_headers):
        trip_id = _completed_trip_id(client, driver_headers)
        client.post(f"/api/v1/trips/{trip_id}/feedback", json=VALID_FEEDBACK, headers=driver_headers)
        r = client.get("/api/v1/admin/feedback", headers=admin_headers)
        assert r.status_code == 200
        items = r.get_json()["items"]
        assert len(items) == 1
        assert items[0]["trip_id"] == trip_id
        assert items[0]["trip_code"] is not None
        assert items[0]["driver_name"] is not None

    def test_driver_cannot_list_all_feedback(self, client, driver_headers):
        r = client.get("/api/v1/admin/feedback", headers=driver_headers)
        assert r.status_code == 403

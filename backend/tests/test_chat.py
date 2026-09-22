"""Driver <-> Admin conversations/chat (spec sections 22-26, 46)."""
import pytest
from models.db import db, Driver, Vehicle
from routes.auth_utils import hash_password, generate_token


def _create_trip(client, driver_headers, **overrides):
    payload = {"source": "Bengaluru", "destination": "Mysuru", "distance_km": 150,
               "dest_lat": 12.2958, "dest_lng": 76.6394}
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


@pytest.fixture()
def other_driver_headers(app, vehicle):
    with app.app_context():
        d = Driver(driver_code="D0004", name="Second Driver", username="driver4",
                    password_hash=hash_password("Driver@12345"), email="driver4@example.com",
                    phone="9876522222", status="Approved", assigned_vehicle_id=vehicle["id"])
        db.session.add(d)
        db.session.commit()
        token = generate_token(d.id, "driver")
    return {"Authorization": f"Bearer {token}"}


class TestDriverAdminChat:
    def test_driver_opens_conversation(self, client, driver_headers):
        r = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers)
        assert r.status_code == 201
        assert r.get_json()["status"] == "Open"

    def test_driver_sends_message_admin_receives_it(self, client, driver_headers, admin_headers):
        conv_id = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/driver/conversations/{conv_id}/messages",
                         json={"message": "Vehicle is overheating."}, headers=driver_headers)
        assert r.status_code == 201
        assert r.get_json()["sender_role"] == "driver"

        r2 = client.get(f"/api/v1/admin/conversations/{conv_id}/messages", headers=admin_headers)
        assert r2.status_code == 200
        msgs = r2.get_json()
        assert len(msgs) == 1
        assert msgs[0]["message"] == "Vehicle is overheating."

    def test_admin_replies_driver_receives_it(self, client, driver_headers, admin_headers):
        conv_id = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers).get_json()["id"]
        client.post(f"/api/v1/driver/conversations/{conv_id}/messages",
                    json={"message": "Are you safe?"}, headers=driver_headers)
        r = client.post(f"/api/v1/admin/conversations/{conv_id}/messages",
                         json={"message": "Please pull over safely."}, headers=admin_headers)
        assert r.status_code == 201
        assert r.get_json()["sender_role"] == "admin"

        msgs = client.get(f"/api/v1/driver/conversations/{conv_id}/messages", headers=driver_headers).get_json()
        assert msgs[-1]["message"] == "Please pull over safely."

    def test_read_unread_tracking(self, client, driver_headers, admin_headers):
        conv_id = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers).get_json()["id"]
        client.post(f"/api/v1/admin/conversations/{conv_id}/messages",
                    json={"message": "Hello from admin"}, headers=admin_headers)

        convs = client.get("/api/v1/driver/conversations", headers=driver_headers).get_json()
        assert convs[0]["unread_count"] == 1

        client.post(f"/api/v1/driver/conversations/{conv_id}/read", headers=driver_headers)
        convs2 = client.get("/api/v1/driver/conversations", headers=driver_headers).get_json()
        assert convs2[0]["unread_count"] == 0

    def test_unauthorized_driver_cannot_access_another_conversation(self, client, driver_headers, other_driver_headers):
        conv_id = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers).get_json()["id"]
        r = client.get(f"/api/v1/driver/conversations/{conv_id}/messages", headers=other_driver_headers)
        assert r.status_code == 403

        r2 = client.post(f"/api/v1/driver/conversations/{conv_id}/messages",
                          json={"message": "snooping"}, headers=other_driver_headers)
        assert r2.status_code == 403

    def test_trip_specific_conversation(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r = client.post("/api/v1/driver/conversations", json={"trip_id": trip_id}, headers=driver_headers)
        assert r.status_code == 201
        assert r.get_json()["trip_id"] == trip_id

        # Reopening for the same trip returns the SAME conversation, not a new one.
        r2 = client.post("/api/v1/driver/conversations", json={"trip_id": trip_id}, headers=driver_headers)
        assert r2.get_json()["id"] == r.get_json()["id"]

    def test_cannot_open_conversation_for_another_drivers_trip(self, client, driver_headers, other_driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.post("/api/v1/driver/conversations", json={"trip_id": trip_id}, headers=other_driver_headers)
        assert r.status_code == 403

    def test_empty_message_rejected(self, client, driver_headers):
        conv_id = client.post("/api/v1/driver/conversations", json={}, headers=driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/driver/conversations/{conv_id}/messages", json={"message": "   "}, headers=driver_headers)
        assert r.status_code == 400

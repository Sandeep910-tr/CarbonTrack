"""Cross-cutting: invalid requests, unauthorized access, validation errors,
and the centralized error-handling envelope from backend/errors.py."""


class TestInvalidRequests:
    def test_malformed_json_body(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", data="{not valid json",
                         content_type="application/json", headers=admin_headers)
        assert r.status_code >= 400

    def test_unknown_api_route_returns_json_404(self, client):
        r = client.get("/api/this/route/does/not/exist")
        assert r.status_code == 404
        body = r.get_json()
        assert body["success"] is False
        assert body["code"] == "NOT_FOUND"

    def test_wrong_http_method(self, client, admin_headers):
        r = client.delete("/api/v1/admin/vehicles", headers=admin_headers)
        assert r.status_code == 405


class TestUnauthorizedRequests:
    def test_no_token_on_admin_route(self, client):
        r = client.get("/api/v1/admin/drivers")
        assert r.status_code == 401

    def test_no_token_on_driver_route(self, client):
        r = client.post("/api/v1/trips", json={})
        assert r.status_code == 401

    def test_malformed_auth_header(self, client):
        r = client.get("/api/v1/admin/drivers", headers={"Authorization": "NotBearer xyz"})
        assert r.status_code == 401

    def test_expired_or_tampered_token(self, client):
        r = client.get("/api/v1/admin/drivers", headers={"Authorization": "Bearer a.b.c"})
        assert r.status_code == 401


class TestValidationErrors:
    def test_validation_error_envelope_shape(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "not valid"}, headers=admin_headers)
        assert r.status_code == 400
        body = r.get_json()
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"
        assert isinstance(body["error"], str)

    def test_conflict_error_envelope_shape(self, client, admin_headers, vehicle):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": vehicle["vehicle_no"]}, headers=admin_headers)
        assert r.status_code == 409
        assert r.get_json()["code"] == "CONFLICT"

    def test_role_locked_to_allowed_values(self, client, super_admin_headers):
        """Regression test: role used to accept any string (privilege escalation risk)."""
        r = client.post("/api/v1/admin/admins", json={
            "name": "Sneaky", "username": "sneakyuser", "password": "Admin@12345",
            "role": "GodMode",
        }, headers=super_admin_headers)
        assert r.status_code == 400

    def test_depot_bad_lat_lng_rejected(self, client, admin_headers):
        r = client.post("/api/v1/admin/depots", json={"name": "Bad Depot", "lat": 999, "lng": 77.5},
                         headers=admin_headers)
        assert r.status_code == 400

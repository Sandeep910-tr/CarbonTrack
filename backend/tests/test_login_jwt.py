"""Login + JWT auth: admin login, driver login, status gating, bad tokens."""


class TestLogin:
    def test_admin_login_success(self, client, super_admin):
        r = client.post("/api/v1/auth/login", json={"username": "superadmin", "password": "Admin@12345"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["role"] == "admin"
        assert "token" in body

    def test_driver_login_success(self, client, approved_driver):
        r = client.post("/api/v1/auth/login", json={"username": "driver1", "password": "Driver@12345"})
        assert r.status_code == 200
        assert r.get_json()["role"] == "driver"

    def test_login_wrong_password(self, client, approved_driver):
        r = client.post("/api/v1/auth/login", json={"username": "driver1", "password": "wrongpass"})
        assert r.status_code == 401

    def test_login_unknown_user(self, client):
        r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "whatever"})
        assert r.status_code == 401

    def test_login_missing_fields(self, client):
        r = client.post("/api/v1/auth/login", json={"username": "driver1"})
        assert r.status_code == 400

    def test_login_pending_driver_blocked(self, client, pending_driver):
        r = client.post("/api/v1/auth/login", json={"username": "driver2", "password": "Driver@12345"})
        assert r.status_code == 403
        assert "approval" in r.get_json()["error"].lower()

    def test_login_deactivated_admin_blocked(self, client, app, super_admin):
        from models.db import db, Admin
        with app.app_context():
            a = db.session.get(Admin, super_admin["id"])
            a.status = "Inactive"
            db.session.commit()
        r = client.post("/api/v1/auth/login", json={"username": "superadmin", "password": "Admin@12345"})
        assert r.status_code == 403


class TestJwtAuth:
    def test_protected_route_without_token(self, client):
        r = client.get("/api/v1/admin/vehicles")
        assert r.status_code == 401

    def test_protected_route_with_garbage_token(self, client):
        r = client.get("/api/v1/admin/vehicles", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_protected_route_wrong_role(self, client, driver_headers):
        """Write endpoints are admin-only; a driver token must not unlock them."""
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "KA09ZZ0000"}, headers=driver_headers)
        assert r.status_code == 403

    def test_protected_route_with_valid_token(self, client, admin_headers):
        r = client.get("/api/v1/admin/vehicles", headers=admin_headers)
        assert r.status_code == 200

    def test_super_admin_only_route_blocks_plain_admin(self, client, admin_headers):
        r = client.post("/api/v1/admin/admins", json={
            "name": "New", "username": "newadmin999", "password": "Admin@12345",
        }, headers=admin_headers)
        assert r.status_code == 403

    def test_super_admin_only_route_allows_super_admin(self, client, super_admin_headers):
        r = client.post("/api/v1/admin/admins", json={
            "name": "New", "username": "newadmin999", "password": "Admin@12345",
        }, headers=super_admin_headers)
        assert r.status_code == 201

    def test_me_endpoint_returns_current_user(self, client, driver_headers):
        r = client.get("/api/v1/auth/me", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json()["role"] == "driver"

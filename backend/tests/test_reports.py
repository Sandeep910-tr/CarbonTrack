"""Reports: fleet/driver/fuel analytics endpoints."""


class TestReports:
    def test_reports_vehicles(self, client, admin_headers, vehicle):
        r = client.get("/api/v1/admin/reports/vehicles", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_reports_drivers(self, client, admin_headers, approved_driver):
        r = client.get("/api/v1/admin/reports/drivers", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_reports_fuel(self, client, admin_headers):
        r = client.get("/api/v1/admin/reports/fuel", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_reports_require_admin(self, client, driver_headers):
        r = client.get("/api/v1/admin/reports/vehicles", headers=driver_headers)
        assert r.status_code == 403

    def test_reports_require_auth(self, client):
        r = client.get("/api/v1/admin/reports/vehicles")
        assert r.status_code == 401

    def test_analytics_overview(self, client, admin_headers):
        r = client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
        assert r.status_code == 200

    def test_analytics_leaderboard(self, client, admin_headers):
        r = client.get("/api/v1/admin/analytics/leaderboard", headers=admin_headers)
        assert r.status_code == 200

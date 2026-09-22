"""Driver approval workflow: approve / reject / block / assign vehicle & depot."""


class TestDriverApproval:
    def test_list_drivers(self, client, admin_headers, approved_driver, pending_driver):
        r = client.get("/api/v1/admin/drivers", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_list_drivers_filtered_by_status(self, client, admin_headers, pending_driver):
        r = client.get("/api/v1/admin/drivers?status=Pending", headers=admin_headers)
        assert r.status_code == 200
        assert all(d["status"] == "Pending" for d in r.get_json())

    def test_approve_driver(self, client, admin_headers, pending_driver):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["driver"]["status"] == "Approved"

    def test_approved_driver_can_then_login(self, client, admin_headers, pending_driver):
        client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=admin_headers)
        r = client.post("/api/v1/auth/login", json={"username": "driver2", "password": "Driver@12345"})
        assert r.status_code == 200

    def test_reject_driver_with_reason(self, client, admin_headers, pending_driver):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/reject",
                         json={"reason": "Missing license document"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["driver"]["status"] == "Rejected"

    def test_rejected_driver_login_shows_reason(self, client, admin_headers, pending_driver):
        client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/reject",
                    json={"reason": "Missing license document"}, headers=admin_headers)
        r = client.post("/api/v1/auth/login", json={"username": "driver2", "password": "Driver@12345"})
        assert r.status_code == 403
        assert "Missing license document" in r.get_json()["error"]

    def test_block_driver(self, client, admin_headers, approved_driver):
        r = client.post(f"/api/v1/admin/drivers/{approved_driver['id']}/block", headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["driver"]["status"] == "Blocked"

    def test_blocked_driver_cannot_login(self, client, admin_headers, approved_driver):
        client.post(f"/api/v1/admin/drivers/{approved_driver['id']}/block", headers=admin_headers)
        r = client.post("/api/v1/auth/login", json={"username": "driver1", "password": "Driver@12345"})
        assert r.status_code == 403

    def test_approve_nonexistent_driver_404(self, client, admin_headers):
        r = client.post("/api/v1/admin/drivers/999999/approve", headers=admin_headers)
        assert r.status_code == 404

    def test_assign_vehicle(self, client, admin_headers, pending_driver, vehicle):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/assign-vehicle",
                         json={"vehicle_id": vehicle["id"]}, headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["driver"]["assigned_vehicle_id"] == vehicle["id"]

    def test_assign_nonexistent_vehicle_404(self, client, admin_headers, pending_driver):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/assign-vehicle",
                         json={"vehicle_id": 999999}, headers=admin_headers)
        assert r.status_code == 404

    def test_assign_depot(self, client, admin_headers, pending_driver, depot):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/assign-depot",
                         json={"depot_id": depot["id"]}, headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["driver"]["depot_id"] == depot["id"]

    def test_driver_role_cannot_access_approval_endpoint(self, client, driver_headers, pending_driver):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=driver_headers)
        assert r.status_code == 403

"""Vehicle CRUD: create/read/update/delete + validation added in Phase 1."""


class TestVehicleCrud:
    def test_list_vehicles(self, client, admin_headers, vehicle):
        r = client.get("/api/v1/admin/vehicles", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.get_json()) == 1

    def test_create_vehicle_success(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={
            "vehicle_no": "MH12CD5678", "vehicle_type": "Van", "fuel_type": "CNG",
            "mileage": 12, "capacity_kg": 800,
        }, headers=admin_headers)
        assert r.status_code == 201
        assert r.get_json()["vehicle_no"] == "MH12CD5678"

    def test_create_vehicle_missing_number(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={"capacity_kg": 500}, headers=admin_headers)
        assert r.status_code == 400

    def test_create_vehicle_invalid_number_format(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "???"}, headers=admin_headers)
        assert r.status_code == 400

    def test_create_vehicle_duplicate_number(self, client, admin_headers, vehicle):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": vehicle["vehicle_no"]}, headers=admin_headers)
        assert r.status_code == 409

    def test_create_vehicle_negative_capacity(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "KA03EF9999", "capacity_kg": -100},
                         headers=admin_headers)
        assert r.status_code == 400

    def test_create_vehicle_bad_health_score(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "KA04GH1111", "health_score": 150},
                         headers=admin_headers)
        assert r.status_code == 400

    def test_update_vehicle(self, client, admin_headers, vehicle):
        r = client.put(f"/api/v1/admin/vehicles/{vehicle['id']}", json={"status": "Maintenance"},
                        headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Maintenance"

    def test_update_vehicle_to_duplicate_number(self, client, admin_headers, vehicle):
        client.post("/api/v1/admin/vehicles", json={"vehicle_no": "KA05IJ2222"}, headers=admin_headers)
        r = client.put(f"/api/v1/admin/vehicles/{vehicle['id']}", json={"vehicle_no": "KA05IJ2222"},
                        headers=admin_headers)
        assert r.status_code == 409

    def test_update_nonexistent_vehicle_404(self, client, admin_headers):
        r = client.put("/api/v1/admin/vehicles/999999", json={"status": "Active"}, headers=admin_headers)
        assert r.status_code == 404

    def test_delete_vehicle(self, client, admin_headers, vehicle):
        r = client.delete(f"/api/v1/admin/vehicles/{vehicle['id']}", headers=admin_headers)
        assert r.status_code == 200
        r2 = client.get("/api/v1/admin/vehicles", headers=admin_headers)
        assert len(r2.get_json()) == 0

    def test_vehicle_endpoints_require_admin_role(self, client, driver_headers):
        """Reading the vehicle list is intentionally shared with drivers; writes are not."""
        r = client.post("/api/v1/admin/vehicles", json={"vehicle_no": "KA09YY0000"}, headers=driver_headers)
        assert r.status_code == 403


class TestServiceHistory:
    def test_log_service_record(self, client, admin_headers, vehicle):
        r = client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records",
                         json={"service_date": "2026-01-15", "service_type": "Routine", "cost": 3000},
                         headers=admin_headers)
        assert r.status_code == 201
        assert r.get_json()["vehicle"]["service_count"] == 1

    def test_log_breakdown_service_increments_breakdown_count(self, client, admin_headers, vehicle):
        r = client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records",
                         json={"service_date": "2026-02-01", "was_breakdown": True, "cost": 8000},
                         headers=admin_headers)
        assert r.status_code == 201
        assert r.get_json()["vehicle"]["breakdown_count"] == 1

    def test_log_service_missing_date(self, client, admin_headers, vehicle):
        r = client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", json={"cost": 100},
                         headers=admin_headers)
        assert r.status_code == 400

    def test_list_service_records(self, client, admin_headers, vehicle):
        client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records",
                    json={"service_date": "2026-01-15"}, headers=admin_headers)
        r = client.get(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.get_json()) == 1

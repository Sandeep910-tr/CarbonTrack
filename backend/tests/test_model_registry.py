"""Model Registry (Priority 1 #8): versioning + only-activate-if-better + rollback.

Training tests are isolated from the real ml/saved directory via the
ml_isolated fixture below - without it, running this test file would
literally overwrite the real, currently-deployed model .pkl files with
throwaway models trained on random test data.
"""
import os
import random
import pytest


@pytest.fixture(autouse=True)
def ml_isolated(tmp_path, monkeypatch):
    """Redirects ml/pipeline.py and ml/registry.py's SAVE/VERSIONS_DIR to a
    throwaway temp directory for every test in this file."""
    import ml.pipeline as pipeline_module
    import ml.registry as registry_module
    save_dir = str(tmp_path / "saved")
    versions_dir = str(tmp_path / "saved" / "versions")
    os.makedirs(versions_dir, exist_ok=True)
    monkeypatch.setattr(pipeline_module, "SAVE", save_dir)
    monkeypatch.setattr(registry_module, "SAVE", save_dir)
    monkeypatch.setattr(registry_module, "VERSIONS_DIR", versions_dir)
    yield


def _seed_completed_trips(app, n=80, n_vehicles=5):
    from models.db import db, Driver, Vehicle, Trip, utcnow
    from routes.auth_utils import hash_password
    with app.app_context():
        vehicles = []
        for j in range(n_vehicles):
            v = Vehicle(vehicle_code=f"V{j:04d}", vehicle_no=f"KA0{j}AB123{j}", vehicle_type="Truck",
                        fuel_type="Diesel", mileage=8 + j, capacity_kg=2000, total_km=20000 * j + 5000,
                        service_count=j + 1, breakdown_count=j % 2, maintenance_cost_total=5000 * j)
            db.session.add(v)
            vehicles.append(v)
        db.session.commit()
        d = Driver(driver_code="D0001", name="Dee", username="regtestdriver",
                   password_hash=hash_password("Driver@12345"), status="Approved",
                   assigned_vehicle_id=vehicles[0].id)
        db.session.add(d)
        db.session.commit()
        rng = random.Random(1)
        for i in range(n):
            v = rng.choice(vehicles)
            dist = rng.uniform(50, 300)
            fuel = dist / v.mileage * rng.uniform(0.9, 1.1)
            t = Trip(trip_code=f"T{i:06d}", driver_id=d.id, vehicle_id=v.id, distance_km=dist, load_kg=500,
                     status="Completed", route_chosen="Eco", weather_condition="Clear", traffic_condition="Medium",
                     actual_fuel_l=fuel, actual_co2_kg=fuel * 2.68, actual_cost=fuel * 95, predicted_eco_score=75,
                     ended_at=utcnow())
            db.session.add(t)
        db.session.commit()


class TestModelRegistry:
    def test_retrain_creates_active_v1(self, client, app, super_admin_headers):
        _seed_completed_trips(app)
        r = client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "success"

        r2 = client.get("/api/v1/admin/ml/models", headers=super_admin_headers)
        assert r2.status_code == 200
        fuel_versions = r2.get_json()["fuel_model"]
        assert len(fuel_versions) == 1
        assert fuel_versions[0]["version"] == 1
        assert fuel_versions[0]["is_active"] is True

    def test_second_retrain_creates_v2_without_orphaning_v1(self, client, app, super_admin_headers):
        _seed_completed_trips(app)
        client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        r = client.get("/api/v1/admin/ml/models", headers=super_admin_headers)
        fuel_versions = r.get_json()["fuel_model"]
        assert {v["version"] for v in fuel_versions} == {1, 2}
        # Exactly one version is ever active at a time.
        assert sum(1 for v in fuel_versions if v["is_active"]) == 1

    def test_rollback_reactivates_older_version(self, client, app, super_admin_headers):
        _seed_completed_trips(app)
        client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        versions = client.get("/api/v1/admin/ml/models", headers=super_admin_headers).get_json()["fuel_model"]
        v1_id = min(v["id"] for v in versions)

        r = client.post(f"/api/v1/admin/ml/models/fuel_model/rollback/{v1_id}", headers=super_admin_headers)
        assert r.status_code == 200
        assert r.get_json()["active_version"]["version"] == 1

        after = client.get("/api/v1/admin/ml/models", headers=super_admin_headers).get_json()["fuel_model"]
        active = [v for v in after if v["is_active"]]
        assert len(active) == 1
        assert active[0]["version"] == 1

    def test_rollback_requires_super_admin(self, client, app, admin_headers):
        _seed_completed_trips(app)
        r = client.post("/api/v1/admin/ml/models/fuel_model/rollback/1", headers=admin_headers)
        assert r.status_code == 403

    def test_rollback_wrong_model_name_rejected(self, client, app, super_admin_headers):
        _seed_completed_trips(app)
        client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        versions = client.get("/api/v1/admin/ml/models", headers=super_admin_headers).get_json()["fuel_model"]
        v1_id = versions[0]["id"]
        r = client.post(f"/api/v1/admin/ml/models/co2_model/rollback/{v1_id}", headers=super_admin_headers)
        assert r.status_code == 400

    def test_retrain_requires_admin(self, client, driver_headers):
        r = client.post("/api/v1/admin/ml/retrain", headers=driver_headers)
        assert r.status_code == 403

    def test_not_enough_trips_fails_gracefully(self, client, super_admin_headers):
        r = client.post("/api/v1/admin/ml/retrain", headers=super_admin_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "failed"

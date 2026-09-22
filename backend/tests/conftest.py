import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCHEDULER", "true")
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

import pytest

from app import create_app
from config import TestConfig
from models.db import db, Admin, Driver, Vehicle, Depot
from routes.auth_utils import hash_password, generate_token


@pytest.fixture()
def app():
    """A fresh Flask app + in-memory SQLite database for every single test -
    nothing persists between tests, so ordering never matters."""
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def super_admin(app):
    with app.app_context():
        a = Admin(name="Root Admin", username="superadmin", password_hash=hash_password("Admin@12345"),
                  role="SuperAdmin", status="Active")
        db.session.add(a)
        db.session.commit()
        return {"id": a.id, "username": "superadmin", "password": "Admin@12345"}


@pytest.fixture()
def plain_admin(app):
    with app.app_context():
        a = Admin(name="Regular Admin", username="admin2", password_hash=hash_password("Admin@12345"),
                  role="Admin", status="Active")
        db.session.add(a)
        db.session.commit()
        return {"id": a.id, "username": "admin2", "password": "Admin@12345"}


@pytest.fixture()
def depot(app):
    with app.app_context():
        d = Depot(depot_code="DPT001", name="Central Depot", city="Bengaluru", lat=12.97, lng=77.59)
        db.session.add(d)
        db.session.commit()
        return {"id": d.id}


@pytest.fixture()
def vehicle(app, depot):
    with app.app_context():
        v = Vehicle(vehicle_code="V0001", vehicle_no="KA01AB1234", vehicle_type="Truck",
                    fuel_type="Diesel", mileage=8.5, capacity_kg=2000, health_score=95,
                    status="Active", depot_id=depot["id"])
        db.session.add(v)
        db.session.commit()
        return {"id": v.id, "vehicle_no": v.vehicle_no}


@pytest.fixture()
def approved_driver(app, vehicle):
    with app.app_context():
        d = Driver(driver_code="D0001", name="Test Driver", username="driver1",
                    password_hash=hash_password("Driver@12345"), email="driver1@example.com",
                    phone="9876543210", status="Approved", assigned_vehicle_id=vehicle["id"])
        db.session.add(d)
        db.session.commit()
        return {"id": d.id, "username": "driver1", "password": "Driver@12345"}


@pytest.fixture()
def pending_driver(app):
    with app.app_context():
        d = Driver(driver_code="D0002", name="Pending Driver", username="driver2",
                    password_hash=hash_password("Driver@12345"), email="driver2@example.com",
                    phone="9876500000", status="Pending")
        db.session.add(d)
        db.session.commit()
        return {"id": d.id, "username": "driver2", "password": "Driver@12345"}


def auth_header(app, user_id, role, extra=None):
    with app.app_context():
        token = generate_token(user_id, role, extra)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def super_admin_headers(app, super_admin):
    return auth_header(app, super_admin["id"], "admin", {"admin_role": "SuperAdmin"})


@pytest.fixture()
def admin_headers(app, plain_admin):
    return auth_header(app, plain_admin["id"], "admin", {"admin_role": "Admin"})


@pytest.fixture()
def driver_headers(app, approved_driver):
    return auth_header(app, approved_driver["id"], "driver")

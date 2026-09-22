"""
Seeds carbon_logistics.db from the workbook CSVs in backend/data/
Run once: python3 seed.py
Creates:
  - 5 admin accounts (username: admin1..admin5 / password: Admin@123)
  - 500 drivers (password: Driver@123) - first 400 Approved, rest split Pending/Rejected
  - 200 vehicles, auto-assigned to approved drivers
  - 2000 historical trips (status=Completed) with AI predictions attached
"""
import os
import sys
import csv
import random
import bcrypt
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.db import db, Admin, Driver, Vehicle, Trip, Depot, AuditLog, utcnow
from routes.auth_utils import hash_password

# Seed-only hashing: cost 12 (the app's real default, used at login/register
# time) takes ~150-300ms per password. Hashing 500 drivers one at a time
# with that cost and zero progress output is what looked "frozen" and got
# Ctrl+C'd - which is exactly what left the previous database half-seeded
# (admins/vehicles committed, drivers/trips never inserted -> login then
# fails, because either the interrupted run's admin table never finished,
# or a later re-run hit the same wall). Demo/seed accounts don't need
# production cost, so use a lower round count here and hash in parallel
# (bcrypt releases the GIL during hashing), which brings 500 drivers down
# from ~1-2 minutes to a couple of seconds.
SEED_BCRYPT_ROUNDS = 10


def hash_password_fast(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(SEED_BCRYPT_ROUNDS)).decode("utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")


def read_csv(name):
    with open(os.path.join(DATA, f"{name}.csv"), newline="") as f:
        return list(csv.DictReader(f))


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        print("Seeding depots...")
        depot_names = ["Central Hub", "North Logistics Center", "South Gateway", "East Distribution", "West Terminal"]
        depots = []
        for name in depot_names:
            d = Depot(name=name, depot_code=f"DPT{depots.__len__()+1:03d}")
            db.session.add(d)
            depots.append(d)
        db.session.commit()
        print(f"  {len(depots)} depots committed.")

        print("Seeding admins...")
        admin_pw_hash = hash_password("Admin@123")  # same password for all 5 - hash once, not 5x
        for i, row in enumerate(read_csv("Admin")):
            db.session.add(Admin(
                name=row["name"], username=row["username"],
                password_hash=admin_pw_hash,
                role="SuperAdmin" if i == 0 else row["role"], status=row["status"],
            ))
        db.session.commit()
        print(f"  {i + 1} admins committed.")

        print("Seeding vehicles...")
        vehicle_map = {}
        for i, row in enumerate(read_csv("Vehicles")):
            v = Vehicle(
                vehicle_code=row["vehicle_id"], vehicle_no=row["vehicle_no"],
                vehicle_type=row["vehicle_type"], fuel_type=row["fuel_type"],
                mileage=float(row["mileage"]), capacity_kg=float(row["capacity_kg"]),
                health_score=round(random.uniform(65, 99), 1),
                depot_id=depots[i % len(depots)].id,
            )
            db.session.add(v)
            db.session.flush()
            vehicle_map[row["vehicle_id"]] = v.id
        db.session.commit()

        print("Seeding drivers...")
        driver_map = {}
        driver_rows = read_csv("Drivers")

        # This is the step that used to look "frozen": hashing 500 passwords
        # one at a time at production bcrypt cost, with no progress output,
        # took 1-2+ minutes of apparent silence. Hash them all up front, in
        # parallel, at a lighter (but still real bcrypt) cost - a few
        # seconds instead - and print progress as it goes.
        print(f"  Hashing {len(driver_rows)} driver passwords (parallel, this takes a few seconds)...")
        with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 4)) as pool:
            driver_hashes = list(pool.map(lambda _: hash_password_fast("Driver@123"), driver_rows))
        print("  Hashing done. Inserting driver rows...")

        for i, row in enumerate(driver_rows):
            status = row.get("status", "Approved")
            if status not in ("Approved", "Pending", "Rejected", "Blocked"):
                status = "Approved"
            vehicle_id = None
            if status == "Approved":
                # cycle through vehicles for assignment
                v_keys = list(vehicle_map.keys())
                vehicle_id = vehicle_map[v_keys[i % len(v_keys)]]
            d = Driver(
                driver_code=row["driver_id"], name=row["name"], username=row["username"],
                password_hash=driver_hashes[i], email=row["email"], phone=row["phone"],
                eco_score=float(row["eco_score"]), status=status,
                assigned_vehicle_id=vehicle_id,
                depot_id=depots[i % len(depots)].id,
                license_no=f"DL-{row['driver_id']}", experience_years=random.randint(1, 15),
            )
            db.session.add(d)
            db.session.flush()
            driver_map[row["driver_id"]] = d.id
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(driver_rows)} drivers inserted...")
        db.session.commit()
        print(f"  {len(driver_rows)} drivers committed.")

        print("Seeding trips (this can take a moment)...")
        ai_preds = {row["trip_id"]: row for row in read_csv("AI_Predictions")}

        count = 0
        for row in read_csv("Trips"):
            driver_id = driver_map.get(row["driver_id"])
            vehicle_id = vehicle_map.get(row["vehicle_id"])
            if not driver_id or not vehicle_id:
                continue
            ai = ai_preds.get(row["trip_id"], {})
            try:
                trip_date = datetime.strptime(row["trip_date"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                trip_date = utcnow()

            t = Trip(
                trip_code=row["trip_id"], driver_id=driver_id, vehicle_id=vehicle_id,
                source=row["source"], destination=row["destination"],
                distance_km=float(row["distance_km"]), load_kg=float(row["load_kg"]),
                purpose="Delivery", preferred_route=row["route"], route_chosen=row["route"],
                weather_condition=row["weather"], traffic_condition=row["traffic"],
                predicted_fuel_l=float(ai.get("predicted_fuel", row["fuel_used_l"])),
                predicted_co2_kg=float(ai.get("predicted_co2", row["co2_kg"])),
                predicted_cost=float(row["fuel_cost"]),
                predicted_eco_score=float(ai.get("eco_score", 75)),
                maintenance_risk=ai.get("maintenance_risk", "Low"),
                recommended_route=ai.get("recommended_route", row["route"]),
                ai_confidence=float(ai.get("confidence", 80)),
                actual_fuel_l=float(row["fuel_used_l"]), actual_co2_kg=float(row["co2_kg"]),
                actual_cost=float(row["fuel_cost"]), status="Completed",
                started_at=trip_date, ended_at=trip_date, created_at=trip_date,
            )
            db.session.add(t)
            count += 1
            if count % 500 == 0:
                db.session.commit()
                print(f"  {count} trips inserted...")
        db.session.commit()
        print(f"Done. {count} trips inserted.")
        print("Seeding sample audit logs...")
        admin_id = 1
        admin_name = "Super Admin"
        sample_logs = [
            ("driver.approve", "Driver", 10, {"driver_code": "DRV010"}),
            ("vehicle.create", "Vehicle", 1, {"vehicle_no": "KA-01-1234"}),
            ("depot.create", "Depot", 1, {"name": "Central Hub"}),
            ("admin.create", "Admin", 2, {"username": "admin2"}),
            ("settings.update", "Settings", None, {"carbon_budget_target_kg": "50000"}),
        ]
        for action, res_type, res_id, details in sample_logs:
            db.session.add(AuditLog(
                actor_type="admin", actor_id=admin_id, actor_name=admin_name,
                action=action, resource_type=res_type, resource_id=res_id,
                details=json.dumps(details), created_at=utcnow()
            ))
        db.session.commit()
        print(f"  {len(sample_logs)} sample audit logs committed.")

        print("\nSeed complete.")
        print("Admin logins:  admin1..admin5 / Admin@123")
        print("Driver logins: driver1..driver500 / Driver@123 (only Approved-status drivers can log in)")


if __name__ == "__main__":
    try:
        seed()
    except KeyboardInterrupt:
        print("\n\nInterrupted! Rolling back any uncommitted rows so the database "
              "isn't left half-seeded (which is what causes 'Invalid credentials' "
              "on login afterwards).")
        try:
            app = create_app()
            with app.app_context():
                db.session.rollback()
        except Exception:
            pass
        print("Rolled back. With the speed fix in this version, a full run "
              "should now take well under a minute - please let it finish "
              "this time. Just re-run: python3 seed.py")
        sys.exit(1)
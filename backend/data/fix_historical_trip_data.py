"""
One-time correction of Trip records already seeded into the live database.

Fixing data/Trips.csv and data/AI_Predictions.csv (see
regenerate_training_data.py) only helps the *initial* from-scratch training
path (ml/train.py). The live app has a second, separate retraining path -
the "Retrain Models" button / daily scheduled job (ml/pipeline.py) - which
trains directly on whatever's already sitting in the database's Trip table.
Since that table was seeded from the OLD, unfixed CSVs before this fix
existed, leaving it untouched would mean the very next retrain silently
undoes everything: it would keep fitting fuel/CO2/cost against the old noisy
values, and previously the DB's own maintenance_risk/recommended_route
columns held a stale model's own past guesses rather than any independently
correct label. This script brings the database in line with the same
formulas (ml/data_formulas.py) so both retraining paths agree, and so
anything admins are already looking at (Trips list, reports) shows numbers
that are internally consistent rather than a mix of old-noisy and new-clean.

Only touches Completed trips' actual_fuel_l / actual_co2_kg / actual_cost /
maintenance_risk / recommended_route. Does not touch trip_id, driver/vehicle
assignment, source/destination, timestamps, or any Ongoing/Planned trip.

Run with the Flask app importable from backend/: `python3 data/fix_historical_trip_data.py`
"""
import os
import sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".."))

from app import create_app
from models.db import db, Trip, Vehicle
from ml.data_formulas import compute_fuel_co2_cost, maintenance_risk_rule, recommended_route_rule

app = create_app()
rng = np.random.default_rng(7)

with app.app_context():
    trips = Trip.query.filter(Trip.status == "Completed").all()
    print(f"Found {len(trips)} completed trips to correct.")
    if not trips:
        sys.exit(0)

    vehicles_by_id = {v.id: v for v in Vehicle.query.all()}
    mileages = [vehicles_by_id[t.vehicle_id].mileage for t in trips if t.vehicle_id in vehicles_by_id]
    distances = [t.distance_km for t in trips if t.distance_km is not None]
    mileage_low_cut = float(np.quantile(mileages, 1 / 3)) if mileages else 10
    distance_high_cut = float(np.quantile(distances, 0.65)) if distances else 200

    updated = 0
    for t in trips:
        v = vehicles_by_id.get(t.vehicle_id)
        if not v or t.distance_km is None or t.load_kg is None:
            continue

        fuel, co2, cost = compute_fuel_co2_cost(
            t.distance_km, v.mileage, t.weather_condition, t.traffic_condition,
            t.load_kg, v.capacity_kg, v.fuel_type, rng=rng,
        )
        t.actual_fuel_l = fuel
        t.actual_co2_kg = co2
        t.actual_cost = cost
        t.maintenance_risk = maintenance_risk_rule(
            v.mileage, t.distance_km, t.load_kg, v.capacity_kg, mileage_low_cut, distance_high_cut, rng
        )
        t.recommended_route = recommended_route_rule(t.weather_condition, t.traffic_condition, t.distance_km, rng)
        updated += 1

    db.session.commit()
    print(f"Corrected {updated} trips.")
    print("Now retrain: POST /api/admin/ml/retrain (or wait for the daily scheduled job).")

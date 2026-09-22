"""
Adds realistic maintenance-history columns to data/Vehicles.csv
(vehicle_age_years, total_km, service_count, last_service_days_ago,
breakdown_count, maintenance_cost_total) and regenerates maintenance_risk in
AI_Predictions.csv using the richer rule in ml/data_formulas.py.

Why this exists: the original Vehicles.csv only had static specs (mileage,
capacity) - nothing about how each vehicle has actually been used or
maintained, which is what a real predictive-maintenance model needs
(Priority 1 item #6). No IoT/sensors involved - this generates the kind of
history a fleet office already keeps on paper: purchase date, odometer,
service log, breakdown count, repair spend.

Run once: python3 data/generate_maintenance_history.py
Then:     python3 ml/train.py
"""
import os
import sys
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".."))
from ml.data_formulas import maintenance_risk_rule

DATA = BASE
rng = np.random.default_rng(11)

vehicles = pd.read_csv(os.path.join(DATA, "Vehicles.csv"))
trips = pd.read_csv(os.path.join(DATA, "Trips.csv"))
ai_pred = pd.read_csv(os.path.join(DATA, "AI_Predictions.csv"))

n = len(vehicles)

# Vehicle age: 0.5-12 years, right-skewed (most of the fleet is fairly new,
# a long tail of older vehicles) - typical of a fleet that's been buying
# vehicles gradually rather than all at once.
vehicle_age_years = np.round(rng.gamma(shape=2.2, scale=1.8, size=n).clip(0.5, 12), 1)

# Total km driven scales with age (roughly 15k-35k km/year) plus noise.
annual_km = rng.normal(24000, 6000, size=n).clip(8000, 40000)
total_km = np.round(vehicle_age_years * annual_km).astype(int)

# Service history: roughly one service every ~8000-12000 km, plus/minus.
km_per_service = rng.normal(10000, 1500, size=n).clip(6000, 16000)
service_count = np.maximum((total_km / km_per_service).round().astype(int), 1)

# Days since last service: vehicles serviced more often skew toward
# "recently serviced"; a handful of neglected vehicles have gone a long time.
last_service_days_ago = np.round(rng.exponential(scale=70, size=n).clip(1, 420)).astype(int)

# Breakdown count: correlated with age and how long it's been since service -
# older, poorly-serviced vehicles break down more.
breakdown_rate = 0.15 * vehicle_age_years / 6 + 0.25 * (last_service_days_ago / 365)
breakdown_count = rng.poisson(breakdown_rate.clip(0.05, None)).astype(int)

# Maintenance cost: base cost per service + extra for each breakdown
# (Rs, matching the fuel-cost scale already used elsewhere in this dataset).
maintenance_cost_total = np.round(
    service_count * rng.normal(3200, 600, size=n).clip(1500, 6000)
    + breakdown_count * rng.normal(9500, 2500, size=n).clip(3000, 25000)
).astype(int)

vehicles["vehicle_age_years"] = vehicle_age_years
vehicles["total_km"] = total_km
vehicles["service_count"] = service_count
vehicles["last_service_days_ago"] = last_service_days_ago
vehicles["breakdown_count"] = breakdown_count
vehicles["maintenance_cost_total"] = maintenance_cost_total

# Fuel efficiency drop: actual fuel/km on this vehicle's trips vs. its own
# rated mileage (1/mileage = L/km baseline). Vehicles with more breakdowns
# and longer service gaps tend to run less efficiently, so nudge it that way
# on top of the noise already present in Trips.csv's fuel_used_l.
trip_fuel_per_km = trips.merge(vehicles[["vehicle_id", "mileage"]], on="vehicle_id", how="left")
trip_fuel_per_km["fuel_per_km"] = trip_fuel_per_km["fuel_used_l"] / trip_fuel_per_km["distance_km"].clip(lower=0.1)
avg_fuel_per_km = trip_fuel_per_km.groupby("vehicle_id")["fuel_per_km"].mean()

veh_idx = vehicles.set_index("vehicle_id")
rated_fuel_per_km = 1.0 / veh_idx["mileage"].clip(lower=1)
drop_pct = ((avg_fuel_per_km - rated_fuel_per_km) / rated_fuel_per_km * 100).clip(lower=0).fillna(0)
vehicles["fuel_efficiency_drop_pct"] = vehicles["vehicle_id"].map(drop_pct).fillna(0).round(2)

vehicles.to_csv(os.path.join(DATA, "Vehicles.csv"), index=False)
print(f"Added maintenance-history columns to Vehicles.csv for {n} vehicles.")

# ---- Regenerate maintenance_risk with the richer, history-aware rule ----
df = trips.merge(vehicles, on="vehicle_id", how="left")
mileage_low_cut = float(np.quantile(vehicles["mileage"].dropna(), 1 / 3))
distance_high_cut = float(np.quantile(trips["distance_km"].dropna(), 0.65))

# Calibrate the new history-based cutoffs against this corpus's own
# distribution (0.65 quantile, matching distance_high_cut's convention)
# rather than fixed real-world numbers, which turned out to be badly
# miscalibrated against this particular synthetic dataset's scale (e.g.
# fuel_efficiency_drop_pct here has a ~35% median, nothing like a real
# fleet's, because of how the underlying fuel-noise model was built).
age_high_cut = float(np.quantile(vehicles["vehicle_age_years"], 0.85))
total_km_high_cut = float(np.quantile(vehicles["total_km"], 0.85))
days_since_service_high_cut = float(np.quantile(vehicles["last_service_days_ago"], 0.85))
fuel_drop_high_cut = float(np.quantile(vehicles["fuel_efficiency_drop_pct"], 0.85))

risk_rng = np.random.default_rng(13)
maintenance_risk = df.apply(
    lambda r: maintenance_risk_rule(
        r["mileage"], r["distance_km"], r["load_kg"], r["capacity_kg"],
        mileage_low_cut, distance_high_cut, risk_rng,
        vehicle_age_years=r["vehicle_age_years"], total_km=r["total_km"],
        days_since_service=r["last_service_days_ago"], breakdown_count=r["breakdown_count"],
        fuel_efficiency_drop_pct=r["fuel_efficiency_drop_pct"],
        age_high_cut=age_high_cut, total_km_high_cut=total_km_high_cut,
        days_since_service_high_cut=days_since_service_high_cut, fuel_drop_high_cut=fuel_drop_high_cut,
        threshold_high=4, threshold_low=1,
    ), axis=1,
)
ai_pred = ai_pred.set_index("trip_id")
ai_pred.loc[df["trip_id"], "maintenance_risk"] = maintenance_risk.values
ai_pred.reset_index().to_csv(os.path.join(DATA, "AI_Predictions.csv"), index=False)

print("Regenerated maintenance_risk in AI_Predictions.csv using vehicle history.")
print("\nNew maintenance_risk distribution:\n", maintenance_risk.value_counts(normalize=True))
print("\nCalibrated cutoffs:", {
    "age_high_cut": round(age_high_cut, 2), "total_km_high_cut": round(total_km_high_cut),
    "days_since_service_high_cut": round(days_since_service_high_cut),
    "fuel_drop_high_cut": round(fuel_drop_high_cut, 2),
})
print("\nNow retrain: python3 ml/train.py")

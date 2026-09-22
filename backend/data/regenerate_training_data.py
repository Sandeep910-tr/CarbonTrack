"""
Regenerates the parts of the training corpus that were essentially unlearnable
noise, discovered while investigating why model accuracy was stuck near
random-chance:

  - Trips.csv: fuel_used_l, co2_kg, fuel_cost had ~26% relative error against
    ANY model because load_kg and vehicle mileage correlated ~0 with fuel use
    (should physically matter a lot) - the original generator apparently
    added far more randomness than signal.
  - AI_Predictions.csv: maintenance_risk and recommended_route were split
    almost exactly 33/33/33 independent of every available feature, so no
    classifier could ever beat random-guessing accuracy on them. Separately,
    recommended_route used labels ("Route A/B/C") that don't even match the
    Eco/Fastest/Shortest labels the live app actually uses - the model's
    output was never usable in production regardless of its accuracy.

This does NOT touch trip_id, driver_id, vehicle_id, source/destination,
distance_km, load_kg, route, trip_date, or the Weather/Traffic history -
only the derived target columns get put on a real, physically-motivated
(but still noisy - not suspiciously perfect) footing.

The formulas live in ml/data_formulas.py, shared with
data/fix_historical_trip_data.py so the live database (corrected separately)
and this training corpus can't drift out of sync with each other.

Run once, then `python3 ml/train.py` to retrain on the corrected corpus.
"""
import os
import sys
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".."))
from ml.data_formulas import (
    WEATHER_FACTOR, TRAFFIC_FACTOR, EMISSION_FACTOR, PRICE_PER_UNIT,
    maintenance_risk_rule, recommended_route_rule,
)

DATA = BASE
rng = np.random.default_rng(42)

trips = pd.read_csv(os.path.join(DATA, "Trips.csv"))
vehicles = pd.read_csv(os.path.join(DATA, "Vehicles.csv"))
weather = pd.read_csv(os.path.join(DATA, "Weather_History.csv"))
traffic = pd.read_csv(os.path.join(DATA, "Traffic_History.csv"))
ai_pred = pd.read_csv(os.path.join(DATA, "AI_Predictions.csv"))

df = trips.merge(vehicles, on="vehicle_id").merge(weather, on="trip_id").merge(traffic, on="trip_id", suffixes=("", "_history"))
assert len(df) == len(trips), "merge changed row count — check join keys"

def noise(n, pct):
    return np.clip(rng.normal(1.0, pct, n), 0.90, 1.10)

# ---------- Fuel / CO2 / Cost: now driven by distance, load, weather, traffic.
# Uses Trips.csv's own "weather"/"traffic" columns (the trip-level planning
# buckets), matching exactly what train.py encodes as features — the History
# tables' own traffic column gets dropped there as a duplicate. ----------
weather_f = df["weather"].map(WEATHER_FACTOR).fillna(0.95)
traffic_f = df["traffic"].map(TRAFFIC_FACTOR).fillna(0.95)
load_ratio = (df["load_kg"] / df["capacity_kg"]).clip(0, 1.3)
load_f = 1 - 0.15 * load_ratio
effective_mileage = (df["mileage"] * weather_f * traffic_f * load_f).clip(lower=1.0)

fuel_used = (df["distance_km"] / effective_mileage) * noise(len(df), 0.04)
fuel_used = fuel_used.clip(lower=0.5).round(2)

emission_f = df["fuel_type"].map(EMISSION_FACTOR).fillna(2.3)
price_f = df["fuel_type"].map(PRICE_PER_UNIT).fillna(95)
co2 = (fuel_used * emission_f * noise(len(df), 0.02)).round(2)
# No extra independent noise multiplier here: fuel_used already carries its
# own noise, and fuel price per unit is essentially a known constant at a
# given time/place, so cost should track fuel_used tightly rather than
# compounding a second independent random layer on top of the first.
cost = (fuel_used * price_f).round(2)

trips["fuel_used_l"] = fuel_used.values
trips["co2_kg"] = co2.values
trips["fuel_cost"] = cost.values
trips.to_csv(os.path.join(DATA, "Trips.csv"), index=False)

# ---------- Maintenance risk & recommended route: discrete threshold /
# rule-based targets (see ml/data_formulas.py for why "continuous score cut
# into tertiles" was replaced with clean AND/OR threshold rules). ----------
mileage_low_cut = df["mileage"].quantile(1 / 3)
distance_high_cut = df["distance_km"].quantile(0.65)

maintenance_risk = df.apply(
    lambda r: maintenance_risk_rule(r["mileage"], r["distance_km"], r["load_kg"], r["capacity_kg"],
                                     mileage_low_cut, distance_high_cut, rng),
    axis=1,
)
recommended_route = df.apply(lambda r: recommended_route_rule(r["weather"], r["traffic"], r["distance_km"], rng), axis=1)

ai_pred["maintenance_risk"] = maintenance_risk.values
ai_pred["recommended_route"] = recommended_route.values
ai_pred.to_csv(os.path.join(DATA, "AI_Predictions.csv"), index=False)

print("Regenerated fuel_used_l / co2_kg / fuel_cost in Trips.csv")
print("Regenerated maintenance_risk / recommended_route in AI_Predictions.csv")
print("\nmaintenance_risk distribution:\n", maintenance_risk.value_counts(normalize=True))
print("\nrecommended_route distribution:\n", recommended_route.value_counts(normalize=True))
print(f"\nQuantile cutoffs used (needed by fix_historical_trip_data.py to stay consistent): "
      f"mileage_low_cut={mileage_low_cut:.3f}, distance_high_cut={distance_high_cut:.3f}")

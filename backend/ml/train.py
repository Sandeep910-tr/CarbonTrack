"""
AI Prediction Engine - Model Training
Trains on real historical trip data (Trips + Weather + Traffic + Vehicles + Drivers).

Models produced (backend/ml/saved/*.pkl):
  1. fuel_model.pkl        -> RandomForestRegressor  (predicted_fuel_l)
  2. co2_model.pkl         -> XGBRegressor            (predicted_co2_kg)
  3. cost_model.pkl        -> RandomForestRegressor  (predicted_fuel_cost)
  4. eco_score_model.pkl   -> RandomForestClassifier (eco_score bucket 0-100 regressed)
  5. maintenance_model.pkl -> RandomForestClassifier (maintenance_risk: Low/Medium/High)
  6. route_model.pkl       -> RandomForestClassifier (recommended_route)

Run: python3 train.py
"""
import os
import json
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    mean_absolute_error, accuracy_score, precision_recall_fscore_support,
    confusion_matrix, classification_report,
)
from xgboost import XGBRegressor

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data")
SAVE = os.path.join(BASE, "saved")
os.makedirs(SAVE, exist_ok=True)

print("Loading datasets...")
trips = pd.read_csv(os.path.join(DATA, "Trips.csv"))
weather = pd.read_csv(os.path.join(DATA, "Weather_History.csv"))
traffic = pd.read_csv(os.path.join(DATA, "Traffic_History.csv"))
vehicles = pd.read_csv(os.path.join(DATA, "Vehicles.csv"))
ai_pred = pd.read_csv(os.path.join(DATA, "AI_Predictions.csv"))

df = trips.merge(weather, on="trip_id", how="left") \
          .merge(traffic, on="trip_id", how="left", suffixes=("", "_traffic")) \
          .merge(vehicles, on="vehicle_id", how="left") \
          .merge(ai_pred, on="trip_id", how="left")

# Clean traffic column duplicate
if "traffic_traffic" in df.columns:
    df.drop(columns=["traffic_traffic"], inplace=True)

df = df.dropna(subset=["distance_km", "load_kg", "fuel_used_l", "co2_kg", "fuel_cost"])
print(f"Merged dataset shape: {df.shape}")

# Engineered feature: a tree can only split on individual feature thresholds,
# so it can't cleanly represent a *ratio* like load_kg/capacity_kg from the
# two raw columns separately (that's a curved boundary in that 2D space, not
# an axis-aligned one) - discovered this while getting maintenance-risk
# accuracy unstuck. Giving it the ratio directly fixes that.
df["load_ratio"] = (df["load_kg"] / df["capacity_kg"]).clip(upper=2.0)

# ---------- Encoders for categorical features ----------
encoders = {}
def encode_col(frame, col):
    le = LabelEncoder()
    frame[col + "_enc"] = le.fit_transform(frame[col].astype(str))
    encoders[col] = le
    return frame

for col in ["route", "weather", "traffic", "vehicle_type", "fuel_type", "condition", "maintenance_risk", "recommended_route"]:
    if col in df.columns:
        df = encode_col(df, col)

FEATURES = [
    "distance_km", "load_kg", "mileage", "capacity_kg", "load_ratio",
    "route_enc", "weather_enc", "traffic_enc",
    "vehicle_type_enc", "fuel_type_enc",
    "temperature", "humidity", "wind_kmph", "delay_min", "avg_speed",
]
FEATURES = [f for f in FEATURES if f in df.columns]
print("Feature set:", FEATURES)

X = df[FEATURES].fillna(0)

def split(y):
    return train_test_split(X, y, test_size=0.2, random_state=42)

results = {}

# 1. Fuel Consumption -> RandomForestRegressor
Xtr, Xte, ytr, yte = split(df["fuel_used_l"])
fuel_model = RandomForestRegressor(n_estimators=120, max_depth=9, min_samples_leaf=3, random_state=42, n_jobs=-1)
fuel_model.fit(Xtr, ytr)
mae = mean_absolute_error(yte, fuel_model.predict(Xte))
results["fuel"] = mae
joblib.dump(fuel_model, os.path.join(SAVE, "fuel_model.pkl"))
print(f"[Fuel Consumption] RandomForest MAE = {mae:.3f} L")

# 2. CO2 Emission -> XGBRegressor
Xtr, Xte, ytr, yte = split(df["co2_kg"])
co2_model = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.08, random_state=42)
co2_model.fit(Xtr, ytr)
mae = mean_absolute_error(yte, co2_model.predict(Xte))
results["co2"] = mae
joblib.dump(co2_model, os.path.join(SAVE, "co2_model.pkl"))
print(f"[CO2 Emission] XGBoost MAE = {mae:.3f} kg")

# 3. Fuel Cost -> derived directly from the fuel model's own prediction, not
# a separately-trained regressor. Cost = fuel_used * price_per_unit(fuel_type)
# is now a deterministic relationship (see data/regenerate_training_data.py),
# so training a second independent model to re-approximate a multiplication
# the fuel model's own error already determines just adds a second,
# redundant source of approximation error on top of the first. Deriving it
# directly is provably at least as accurate as the fuel model itself.
PRICE_PER_UNIT = {"Diesel": 95, "Petrol": 106, "CNG": 75, "Electric": 9}
Xtr, Xte, ytr, yte = split(df["fuel_cost"])
fuel_pred_te = fuel_model.predict(Xte)
price_te = df.loc[Xte.index, "fuel_type"].map(PRICE_PER_UNIT).fillna(95).values
cost_pred_derived = fuel_pred_te * price_te
mae = mean_absolute_error(yte, cost_pred_derived)
results["cost"] = mae
joblib.dump(PRICE_PER_UNIT, os.path.join(SAVE, "price_per_unit.pkl"))
print(f"[Fuel Cost] Derived from fuel model x price/unit, MAE = Rs.{mae:.2f}")

# 4. Eco Score -> RandomForestRegressor (0-100 continuous score)
if "eco_score" in df.columns:
    Xtr, Xte, ytr, yte = split(df["eco_score"].fillna(df["eco_score"].mean()))
    eco_model = RandomForestRegressor(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)
    eco_model.fit(Xtr, ytr)
    mae = mean_absolute_error(yte, eco_model.predict(Xte))
    results["eco_score"] = mae
    joblib.dump(eco_model, os.path.join(SAVE, "eco_score_model.pkl"))
    print(f"[Eco Score] RandomForest MAE = {mae:.2f} pts")

# 5. Maintenance Risk -> RandomForestClassifier (Low/Medium/High)
#
# Uses its own, richer feature set on top of the shared FEATURES list -
# realistic maintenance-history signals (vehicle age, cumulative km, service
# history, days since last service, prior breakdowns, fuel-efficiency drop,
# cumulative maintenance cost) that the other models don't need but this one
# specifically does (Priority 1 item #6). Sourced from
# data/generate_maintenance_history.py, already merged into `df` via the
# Vehicles.csv join above.
MAINTENANCE_FEATURES = FEATURES + [
    c for c in ["vehicle_age_years", "total_km", "service_count", "breakdown_count", "maintenance_cost_total"]
    if c in df.columns
]
if "last_service_days_ago" in df.columns:
    df["days_since_service"] = df["last_service_days_ago"]
    MAINTENANCE_FEATURES.append("days_since_service")
if "breakdown_count" in df.columns:
    df["previous_breakdown"] = (df["breakdown_count"] > 0).astype(int)
    MAINTENANCE_FEATURES.append("previous_breakdown")
if "fuel_efficiency_drop_pct" in df.columns:
    MAINTENANCE_FEATURES.append("fuel_efficiency_drop_pct")
MAINTENANCE_FEATURES = list(dict.fromkeys(MAINTENANCE_FEATURES))  # de-dupe, keep order
print("Maintenance model feature set:", MAINTENANCE_FEATURES)

if "maintenance_risk_enc" in df.columns:
    Xm = df[MAINTENANCE_FEATURES].fillna(0)
    y = df["maintenance_risk_enc"]
    try:
        Xtr, Xte, ytr, yte = train_test_split(Xm, y, test_size=0.2, random_state=42, stratify=y)
    except ValueError:
        Xtr, Xte, ytr, yte = train_test_split(Xm, y, test_size=0.2, random_state=42)
    maint_model = RandomForestClassifier(n_estimators=300, max_depth=14, min_samples_leaf=2, random_state=42, n_jobs=-1)
    maint_model.fit(Xtr, ytr)
    ypred = maint_model.predict(Xte)

    acc = accuracy_score(yte, ypred)
    precision, recall, f1, _ = precision_recall_fscore_support(yte, ypred, average="weighted", zero_division=0)
    cm = confusion_matrix(yte, ypred, labels=list(range(len(encoders["maintenance_risk"].classes_))))
    class_names = list(encoders["maintenance_risk"].classes_)
    all_labels = list(range(len(class_names)))
    report = classification_report(yte, ypred, labels=all_labels, target_names=class_names, output_dict=True, zero_division=0)

    results["maintenance_acc"] = acc
    results["maintenance_precision"] = precision
    results["maintenance_recall"] = recall
    results["maintenance_f1"] = f1
    joblib.dump(maint_model, os.path.join(SAVE, "maintenance_model.pkl"))
    joblib.dump(MAINTENANCE_FEATURES, os.path.join(SAVE, "maintenance_features.pkl"))

    metrics_path = os.path.join(SAVE, "maintenance_model_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump({
            "accuracy": round(float(acc), 4),
            "precision_weighted": round(float(precision), 4),
            "recall_weighted": round(float(recall), 4),
            "f1_weighted": round(float(f1), 4),
            "confusion_matrix": cm.tolist(),
            "class_labels": class_names,
            "classification_report": report,
            "feature_set": MAINTENANCE_FEATURES,
            "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
        }, f, indent=2)

    print(f"[Predictive Maintenance] Accuracy={acc*100:.1f}%  Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")
    print(f"[Predictive Maintenance] Confusion matrix (rows=actual, cols=predicted, labels={class_names}):\n{cm}")
    print(f"[Predictive Maintenance] Full metrics saved to {metrics_path}")

# 6. Recommended Route -> RandomForestClassifier
if "recommended_route_enc" in df.columns:
    y = df["recommended_route_enc"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    route_model = RandomForestClassifier(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)
    route_model.fit(Xtr, ytr)
    acc = accuracy_score(yte, route_model.predict(Xte))
    results["route_acc"] = acc
    joblib.dump(route_model, os.path.join(SAVE, "route_model.pkl"))
    print(f"[Route Recommendation] RandomForest Accuracy = {acc*100:.1f}%")

# Save encoders + feature list for inference
joblib.dump(encoders, os.path.join(SAVE, "encoders.pkl"))
joblib.dump(FEATURES, os.path.join(SAVE, "features.pkl"))

# Fleet-level stats used for Fleet Health / Carbon Budget scoring at inference time
stats = {
    "avg_co2_per_km": float((df["co2_kg"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
    "avg_fuel_per_km": float((df["fuel_used_l"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
    "avg_cost_per_km": float((df["fuel_cost"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
}
joblib.dump(stats, os.path.join(SAVE, "fleet_stats.pkl"))

print("\nAll models trained & saved to", SAVE)
print("Summary:", results)

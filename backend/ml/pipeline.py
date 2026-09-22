"""
Continuous Learning Pipeline
Retrains all six AI models from whatever trip data currently exists in the live
database (not just the original workbook CSVs) - so as new completed trips
accumulate, retraining actually incorporates them. Triggered manually via
POST /api/admin/ml/retrain, or automatically once a day by the APScheduler
job registered in app.py.
"""
import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    mean_absolute_error, accuracy_score, precision_recall_fscore_support,
    confusion_matrix, classification_report,
)
from xgboost import XGBRegressor

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".."))
from ml.data_formulas import PRICE_PER_UNIT, maintenance_risk_rule, recommended_route_rule
from ml.vehicle_features import compute_maintenance_features
from ml import registry
SAVE = os.path.join(BASE, "saved")


def _trips_to_dataframe():
    """Pulls completed trips + their vehicle info directly from the live DB.

    maintenance_risk and recommended_route are NOT read from the Trip row -
    those columns hold the model's own prediction from whenever the trip was
    planned, not an independently-observed outcome (the app has no process
    for ever finding out which route was truly optimal, or whether a vehicle
    actually needed maintenance). Training a new classifier on a previous
    classifier's own guesses just reinforces whatever it already believed,
    which is how these got stuck near random-chance accuracy in the first
    place. Instead, both are recomputed here from the same rule used to
    rebuild the original training corpus (ml/data_formulas.py), so ongoing
    retraining converges on a real, learnable relationship instead of
    perpetuating old mistakes.
    """
    from models.db import db, Trip, Vehicle

    trips = Trip.query.filter(
        Trip.status == "Completed", Trip.actual_fuel_l.isnot(None), Trip.actual_co2_kg.isnot(None)
    ).all()
    rows = []
    for t in trips:
        v = db.session.get(Vehicle, t.vehicle_id)
        if not v:
            continue
        rows.append({
            "distance_km": t.distance_km, "load_kg": t.load_kg,
            "mileage": v.mileage, "capacity_kg": v.capacity_kg,
            "route": t.route_chosen, "weather": t.weather_condition, "traffic": t.traffic_condition,
            "vehicle_type": v.vehicle_type, "fuel_type": v.fuel_type,
            "temperature": 28, "humidity": 60, "wind_kmph": 10, "delay_min": 5, "avg_speed": 45,
            "fuel_used_l": t.actual_fuel_l, "co2_kg": t.actual_co2_kg, "fuel_cost": t.actual_cost,
            "eco_score": t.predicted_eco_score or 75,
            **compute_maintenance_features(
                v, recent_avg_fuel_per_km=(t.actual_fuel_l / t.distance_km) if t.distance_km else None
            ),
        })
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df

    mileage_low_cut = df["mileage"].quantile(1 / 3)
    distance_high_cut = df["distance_km"].quantile(0.65)
    age_high_cut = df["vehicle_age_years"].quantile(0.85)
    total_km_high_cut = df["total_km"].quantile(0.85)
    days_since_service_high_cut = df["days_since_service"].quantile(0.85)
    fuel_drop_high_cut = df["fuel_efficiency_drop_pct"].quantile(0.85)
    rng = np.random.default_rng()
    df["maintenance_risk"] = df.apply(
        lambda r: maintenance_risk_rule(
            r["mileage"], r["distance_km"], r["load_kg"], r["capacity_kg"],
            mileage_low_cut, distance_high_cut, rng,
            vehicle_age_years=r["vehicle_age_years"], total_km=r["total_km"],
            days_since_service=r["days_since_service"], breakdown_count=r["breakdown_count"],
            fuel_efficiency_drop_pct=r["fuel_efficiency_drop_pct"],
            age_high_cut=age_high_cut, total_km_high_cut=total_km_high_cut,
            days_since_service_high_cut=days_since_service_high_cut, fuel_drop_high_cut=fuel_drop_high_cut,
            threshold_high=4, threshold_low=1,
        ),
        axis=1,
    )
    df["recommended_route"] = df.apply(
        lambda r: recommended_route_rule(r["weather"], r["traffic"], r["distance_km"], rng), axis=1
    )
    return df


def run_training_pipeline():
    """Runs inside an active Flask app context (called from a request handler or
    the APScheduler job, both of which push one). Returns (metrics_dict, n_rows)."""
    os.makedirs(SAVE, exist_ok=True)
    df = _trips_to_dataframe()
    if len(df) < 50:
        raise ValueError(f"Not enough completed trips to retrain ({len(df)} found, need >= 50)")

    encoders = {}
    for col in ["route", "weather", "traffic", "vehicle_type", "fuel_type", "maintenance_risk", "recommended_route"]:
        le = LabelEncoder()
        df[col + "_enc"] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    # Same engineered ratio feature as ml/train.py — a tree can't cleanly
    # reconstruct load_kg/capacity_kg as a ratio from the two raw columns
    # separately, which was the main reason maintenance-risk accuracy stayed
    # stuck even after the label itself was fixed.
    df["load_ratio"] = (df["load_kg"] / df["capacity_kg"]).clip(upper=2.0)

    FEATURES = ["distance_km", "load_kg", "mileage", "capacity_kg", "load_ratio", "route_enc", "weather_enc",
                "traffic_enc", "vehicle_type_enc", "fuel_type_enc", "temperature", "humidity",
                "wind_kmph", "delay_min", "avg_speed"]
    X = df[FEATURES].fillna(0)

    def split(y):
        return train_test_split(X, y, test_size=0.2, random_state=42)

    metrics = {}

    Xtr, Xte, ytr, yte = split(df["fuel_used_l"])
    fuel_model = RandomForestRegressor(n_estimators=120, max_depth=9, min_samples_leaf=3, random_state=42, n_jobs=-1)
    fuel_model.fit(Xtr, ytr)
    metrics["fuel_mae_l"] = round(mean_absolute_error(yte, fuel_model.predict(Xte)), 3)
    joblib.dump(fuel_model, os.path.join(SAVE, "fuel_model.pkl"))

    Xtr, Xte, ytr, yte = split(df["co2_kg"])
    co2_model = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.08, random_state=42)
    co2_model.fit(Xtr, ytr)
    metrics["co2_mae_kg"] = round(mean_absolute_error(yte, co2_model.predict(Xte)), 3)
    joblib.dump(co2_model, os.path.join(SAVE, "co2_model.pkl"))

    Xtr, Xte, ytr, yte = split(df["fuel_cost"])
    # Derived from the fuel model's own prediction, not a separately-trained
    # regressor — see ml/train.py for why re-approximating a now-deterministic
    # fuel*price relationship with a second independent model just adds a
    # second source of error on top of the first.
    fuel_pred_te = fuel_model.predict(Xte)
    price_te = df.loc[Xte.index, "fuel_type"].map(PRICE_PER_UNIT).fillna(95).values
    metrics["cost_mae"] = round(mean_absolute_error(yte, fuel_pred_te * price_te), 3)
    joblib.dump(PRICE_PER_UNIT, os.path.join(SAVE, "price_per_unit.pkl"))

    Xtr, Xte, ytr, yte = split(df["eco_score"])
    eco_model = RandomForestRegressor(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)
    eco_model.fit(Xtr, ytr)
    metrics["eco_score_mae"] = round(mean_absolute_error(yte, eco_model.predict(Xte)), 3)
    joblib.dump(eco_model, os.path.join(SAVE, "eco_score_model.pkl"))

    MAINTENANCE_FEATURES = FEATURES + [
        "vehicle_age_years", "total_km", "service_count", "days_since_service",
        "previous_breakdown", "fuel_efficiency_drop_pct", "maintenance_cost_total",
    ]
    Xm = df[MAINTENANCE_FEATURES].fillna(0)
    y = df["maintenance_risk_enc"]
    try:
        Xtr, Xte, ytr, yte = train_test_split(Xm, y, test_size=0.2, random_state=42, stratify=y)
    except ValueError:
        # A class with too few members to stratify on (common on a small or
        # newly-live dataset) - fall back to a plain random split rather than
        # failing the whole retrain over it.
        Xtr, Xte, ytr, yte = train_test_split(Xm, y, test_size=0.2, random_state=42)
    maint_model = RandomForestClassifier(n_estimators=300, max_depth=14, min_samples_leaf=2, random_state=42, n_jobs=-1)
    maint_model.fit(Xtr, ytr)
    ypred = maint_model.predict(Xte)

    acc = accuracy_score(yte, ypred)
    precision, recall, f1, _ = precision_recall_fscore_support(yte, ypred, average="weighted", zero_division=0)
    class_names = list(encoders["maintenance_risk"].classes_)
    all_labels = list(range(len(class_names)))
    cm = confusion_matrix(yte, ypred, labels=all_labels)

    metrics["maintenance_accuracy"] = round(float(acc), 3)
    metrics["maintenance_precision"] = round(float(precision), 3)
    metrics["maintenance_recall"] = round(float(recall), 3)
    metrics["maintenance_f1"] = round(float(f1), 3)
    joblib.dump(maint_model, os.path.join(SAVE, "maintenance_model.pkl"))
    joblib.dump(MAINTENANCE_FEATURES, os.path.join(SAVE, "maintenance_features.pkl"))

    with open(os.path.join(SAVE, "maintenance_model_metrics.json"), "w") as f:
        json.dump({
            "accuracy": round(float(acc), 4), "precision_weighted": round(float(precision), 4),
            "recall_weighted": round(float(recall), 4), "f1_weighted": round(float(f1), 4),
            "confusion_matrix": cm.tolist(), "class_labels": class_names,
            "classification_report": classification_report(yte, ypred, labels=all_labels, target_names=class_names, output_dict=True, zero_division=0),
            "feature_set": MAINTENANCE_FEATURES, "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
            "source": "live_retrain",
        }, f, indent=2)

    y = df["recommended_route_enc"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    route_model = RandomForestClassifier(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)
    route_model.fit(Xtr, ytr)
    metrics["route_accuracy"] = round(accuracy_score(yte, route_model.predict(Xte)), 3)
    joblib.dump(route_model, os.path.join(SAVE, "route_model.pkl"))

    joblib.dump(encoders, os.path.join(SAVE, "encoders.pkl"))
    joblib.dump(FEATURES, os.path.join(SAVE, "features.pkl"))

    stats = {
        "avg_co2_per_km": float((df["co2_kg"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
        "avg_fuel_per_km": float((df["fuel_used_l"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
        "avg_cost_per_km": float((df["fuel_cost"] / df["distance_km"]).replace([np.inf, -np.inf], np.nan).dropna().mean()),
    }
    joblib.dump(stats, os.path.join(SAVE, "fleet_stats.pkl"))

    # ml/predict.py caches loaded models at import time - clear that cache so the
    # freshly retrained models are picked up on the very next prediction request.
    from ml import predict as predict_module
    predict_module._cache.clear()

    # Model Registry (Priority 1 #8): snapshot + version each model, and only
    # keep a new one live if it actually beats the currently active version.
    registry_results = {}
    for model_name in ["fuel_model", "co2_model", "eco_score_model", "maintenance_model", "route_model"]:
        version_row, activated = registry.register_version(model_name, metrics, len(df))
        registry_results[model_name] = {"version": version_row.version, "activated": activated}
    metrics["model_registry"] = registry_results
    # Restoring a rejected model's file (inside register_version) happens
    # after predict.py's cache was already cleared above, so clear it again
    # to be safe in case any model got reverted to its previous file.
    predict_module._cache.clear()

    return metrics, len(df)

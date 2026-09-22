"""
AI Prediction Engine - Inference
Loads the models trained by train.py and exposes predict_trip() used by the
trips API to produce: fuel, CO2, cost, eco score, maintenance risk,
recommended route + a composite AI score, weather impact and budget risk.
"""
import os
import joblib
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(BASE, "saved")

_cache = {}
_MODEL_NAMES = ["fuel_model", "co2_model", "eco_score_model",
                "maintenance_model", "maintenance_features", "route_model",
                "encoders", "features", "fleet_stats", "price_per_unit"]


def _load():
    """Loads every model file into _cache exactly once. Builds into a local dict
    first and only publishes to the module-level _cache after every file has
    loaded successfully - this guarantees _cache is either completely empty or
    completely populated, never a partial/broken mix. (The previous version
    assigned into _cache inside the loop, so a failure partway through left a
    half-built cache that the `if _cache: return _cache` short-circuit would
    then serve forever without retrying - manifesting as a confusing
    'KeyError: encoders' on some later, unrelated request instead of a clear
    error on the request that actually failed to load.)"""
    if _cache:
        return _cache
    loaded = {}
    for name in _MODEL_NAMES:
        path = os.path.join(SAVE, f"{name}.pkl")
        if not os.path.exists(path):
            loaded[name] = None
            continue
        try:
            loaded[name] = joblib.load(path)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load AI model file '{name}.pkl' ({path}). This is almost always a "
                f"scikit-learn/XGBoost/joblib version mismatch between whatever trained the model "
                f"and what's installed now. Fix: cd backend/ml && python3 train.py to retrain "
                f"against your currently installed library versions, then fully restart the "
                f"server (stop it with Ctrl+C, don't just leave it running). "
                f"Original error: {type(e).__name__}: {e}"
            ) from e
    _cache.update(loaded)
    return _cache


def _safe_encode(encoders, col, value):
    le = encoders.get(col)
    if le is None:
        return 0
    value = str(value)
    if value in le.classes_:
        return int(le.transform([value])[0])
    # unseen category -> fall back to the most common (index 0)
    return 0


def predict_trip(distance_km, load_kg, mileage, capacity_kg, route, weather,
                  traffic, vehicle_type, fuel_type, temperature=28, humidity=60,
                  wind_kmph=10, delay_min=5, avg_speed=45, vehicle_row=None,
                  recent_avg_fuel_per_km=None):
    """Run the full AI prediction pipeline for a single trip and return a dict
    matching the flowchart's 'AI Outputs' block (D. AI Prediction Engine).

    vehicle_row (optional): the assigned Vehicle - if given, its maintenance
    history (age, total_km, service_count, last_service_date, breakdown_count,
    maintenance_cost_total) feeds the maintenance-risk model alongside the
    trip-level features. Without it (e.g. no vehicle history recorded yet),
    ml/vehicle_features.compute_maintenance_features() falls back to
    reasonable population-average defaults rather than failing."""
    m = _load()
    encoders = m["encoders"] or {}
    features = m["features"]

    row = {
        "distance_km": distance_km, "load_kg": load_kg, "mileage": mileage,
        "capacity_kg": capacity_kg,
        "load_ratio": min(load_kg / max(capacity_kg, 1), 2.0),
        "route_enc": _safe_encode(encoders, "route", route),
        "weather_enc": _safe_encode(encoders, "weather", weather),
        "traffic_enc": _safe_encode(encoders, "traffic", traffic),
        "vehicle_type_enc": _safe_encode(encoders, "vehicle_type", vehicle_type),
        "fuel_type_enc": _safe_encode(encoders, "fuel_type", fuel_type),
        "temperature": temperature, "humidity": humidity, "wind_kmph": wind_kmph,
        "delay_min": delay_min, "avg_speed": avg_speed,
    }
    X = pd.DataFrame([[row.get(f, 0) for f in features]], columns=features)

    fuel = float(max(0, m["fuel_model"].predict(X)[0])) if m["fuel_model"] else round(distance_km / max(mileage, 1), 2)
    co2 = float(max(0, m["co2_model"].predict(X)[0])) if m["co2_model"] else round(fuel * 2.68, 2)
    # Cost is deterministic given fuel used and fuel type (price/unit), so it's
    # derived directly from the fuel model's own prediction rather than a
    # separately-trained regressor re-approximating the same relationship —
    # see train.py for why that's both simpler and more accurate.
    price_per_unit = m["price_per_unit"] or {"Diesel": 95, "Petrol": 106, "CNG": 75, "Electric": 9}
    cost = round(fuel * price_per_unit.get(fuel_type, 95), 2)
    eco_score = float(np.clip(m["eco_score_model"].predict(X)[0], 0, 100)) if m["eco_score_model"] else 75.0

    maintenance_risk = "Medium"
    if m["maintenance_model"] is not None:
        maint_features = m["maintenance_features"] or features
        from ml.vehicle_features import compute_maintenance_features
        hist = compute_maintenance_features(vehicle_row or {}, recent_avg_fuel_per_km=recent_avg_fuel_per_km)
        maint_row = {**row, **hist}
        Xm = pd.DataFrame([[maint_row.get(f, 0) for f in maint_features]], columns=maint_features)
        pred = m["maintenance_model"].predict(Xm)[0]
        le = encoders.get("maintenance_risk")
        maintenance_risk = le.inverse_transform([pred])[0] if le else str(pred)

    recommended_route = route
    confidence = 80.0
    if m["route_model"] is not None:
        proba = m["route_model"].predict_proba(X)[0]
        pred = int(np.argmax(proba))
        confidence = float(round(max(proba) * 100, 1))
        le = encoders.get("recommended_route")
        recommended_route = le.inverse_transform([pred])[0] if le else route

    # Weather impact (0-100, higher = worse impact)
    weather_penalty = {"Clear": 5, "Cloudy": 15, "Rain": 45, "Fog": 55, "Storm": 80}
    weather_impact = weather_penalty.get(weather, 25)

    # Carbon budget risk: compare vs fleet avg co2/km
    stats = m["fleet_stats"] or {"avg_co2_per_km": 0.3}
    co2_per_km = co2 / max(distance_km, 1)
    budget_risk = "Low"
    if co2_per_km > stats["avg_co2_per_km"] * 1.25:
        budget_risk = "High"
    elif co2_per_km > stats["avg_co2_per_km"] * 1.05:
        budget_risk = "Medium"

    # Fleet health proxy score (mileage efficiency + maintenance risk)
    risk_penalty = {"Low": 0, "Medium": 10, "High": 25}.get(maintenance_risk, 10)
    fleet_health_score = float(np.clip(95 - risk_penalty - (weather_impact * 0.1), 0, 100))

    # Overall composite AI score
    overall_score = float(np.clip(
        (eco_score * 0.4) + (fleet_health_score * 0.3) + ((100 - weather_impact) * 0.15)
        + ((100 if budget_risk == "Low" else 60 if budget_risk == "Medium" else 30) * 0.15),
        0, 100
    ))

    result = {
        "predicted_fuel_l": round(fuel, 2),
        "predicted_co2_kg": round(co2, 2),
        "predicted_cost": round(cost, 2),
        "predicted_eco_score": round(eco_score, 1),
        "maintenance_risk": maintenance_risk,
        "recommended_route": recommended_route,
        "ai_confidence": confidence,
        "weather_impact": weather_impact,
        "carbon_budget_risk": budget_risk,
        "fleet_health_score": round(fleet_health_score, 1),
        "overall_score": round(overall_score, 1),
    }
    _validate_prediction_output(result, distance_km)
    return result


# Section 28 (ML Output Validation): never blindly trust a model's
# prediction. A model can produce NaN/Infinity (e.g. from a degenerate
# input combination) or an implausible value (negative fuel, a fuel-per-km
# ratio no real vehicle could achieve) - this catches that before it reaches
# a driver's screen or, worse, gets treated as ground truth anywhere downstream.
_OUTPUT_BOUNDS = {
    "predicted_fuel_l": (0, 2000),
    "predicted_co2_kg": (0, 6000),   # generous upper bound (2000L * ~3kg CO2/L)
    "predicted_cost": (0, 500000),
    "predicted_eco_score": (0, 100),
    "ai_confidence": (0, 100),
    "weather_impact": (0, 100),
    "fleet_health_score": (0, 100),
    "overall_score": (0, 100),
}


def _validate_prediction_output(result, distance_km):
    import math
    for field, (low, high) in _OUTPUT_BOUNDS.items():
        value = result.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
            raise RuntimeError(
                f"ML prediction produced a non-finite value for {field} ({value!r}). "
                f"Refusing to return this prediction - retrain or check model inputs."
            )
        if value < low or value > high:
            raise RuntimeError(
                f"ML prediction for {field} ({value}) is outside the plausible range "
                f"[{low}, {high}]. Refusing to return this prediction rather than show "
                f"a fabricated-looking number - retrain or check model inputs."
            )
    # A sanity ratio check independent of the per-field bounds above: fuel
    # consumption per km should never be absurd (e.g. 50 L/km) regardless of
    # whether it happens to also be under the flat 2000L ceiling.
    fuel_per_km = result.get("predicted_fuel_l", 0) / max(distance_km, 1)
    if fuel_per_km > 5:
        raise RuntimeError(
            f"ML prediction implies {fuel_per_km:.1f} L/km, which is not physically "
            f"plausible for any vehicle in this fleet. Refusing to return this prediction."
        )


if __name__ == "__main__":
    print(predict_trip(120, 2000, 10.5, 5000, "Eco", "Rain", "Medium", "Truck", "Diesel"))

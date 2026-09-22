"""Turns a Vehicle's raw maintenance-history fields into the engineered
features the maintenance-risk classifier actually trains/predicts on.
Shared by:
  - ml/pipeline.py   (live "Retrain Models" path - reads straight from DB)
  - routes/trips.py  (live single-trip prediction)
  - data/generate_maintenance_history.py (bootstraps realistic history onto
    the seeded CSV vehicles so the *initial* ml/train.py run has the same
    signal available)

Keeping this in one place means a vehicle's maintenance risk is computed
the same way whether it's coming from a fresh prediction or from training -
the model can't learn a relationship at train time that inference then
computes differently.
"""
from datetime import date


def compute_maintenance_features(vehicle_row, recent_avg_fuel_per_km=None, reference_date=None):
    """`vehicle_row` needs: purchase_date, total_km, last_service_date,
    service_count, breakdown_count, maintenance_cost_total, mileage
    (attribute access - works with a Vehicle ORM instance or a dict-like
    row/Series with the same field names via getattr/get).

    `recent_avg_fuel_per_km` (optional): this vehicle's actual L/km over its
    recent completed trips. Compared against its rated mileage to estimate
    fuel_efficiency_drop_pct - a vehicle burning noticeably more fuel per km
    than its rated mileage suggests is a classic leading indicator of
    mechanical wear, before it shows up as an outright breakdown.
    """
    ref = reference_date or date.today()

    def _get(field, default=None):
        if isinstance(vehicle_row, dict):
            return vehicle_row.get(field, default)
        return getattr(vehicle_row, field, default) or default

    purchase_date = _get("purchase_date")
    vehicle_age_years = round((ref - purchase_date).days / 365.25, 2) if purchase_date else 3.0

    last_service_date = _get("last_service_date")
    days_since_service = (ref - last_service_date).days if last_service_date else 180

    total_km = float(_get("total_km", 0) or 0)
    service_count = int(_get("service_count", 0) or 0)
    breakdown_count = int(_get("breakdown_count", 0) or 0)
    maintenance_cost_total = float(_get("maintenance_cost_total", 0) or 0)

    fuel_efficiency_drop_pct = 0.0
    rated_mileage = _get("mileage")
    if recent_avg_fuel_per_km and rated_mileage and rated_mileage > 0:
        rated_fuel_per_km = 1.0 / rated_mileage
        drop = (recent_avg_fuel_per_km - rated_fuel_per_km) / rated_fuel_per_km * 100
        fuel_efficiency_drop_pct = round(max(drop, 0.0), 2)

    return {
        "vehicle_age_years": vehicle_age_years,
        "total_km": round(total_km, 1),
        "service_count": service_count,
        "days_since_service": max(days_since_service, 0),
        "previous_breakdown": 1 if breakdown_count > 0 else 0,
        "breakdown_count": breakdown_count,
        "fuel_efficiency_drop_pct": fuel_efficiency_drop_pct,
        "maintenance_cost_total": round(maintenance_cost_total, 2),
    }


MAINTENANCE_FEATURE_NAMES = [
    "vehicle_age_years", "total_km", "service_count", "days_since_service",
    "previous_breakdown", "fuel_efficiency_drop_pct", "maintenance_cost_total",
]

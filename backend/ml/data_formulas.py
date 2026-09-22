"""
Shared, physically-motivated formulas for deriving trip outcomes (fuel/CO2/
cost) and classifier targets (maintenance risk, recommended route) from trip
and vehicle attributes. Used by:

  - data/regenerate_training_data.py  (fixes the training CSVs)
  - data/fix_historical_trip_data.py  (fixes the same data already seeded
    into the live database, so the live "Retrain Models" pipeline — which
    trains on Trip.maintenance_risk / Trip.recommended_route as if they were
    ground truth — doesn't keep re-learning the old near-random relationship
    forever)

Keeping this in one place means both paths can't drift out of sync with
each other, which would otherwise quietly reintroduce the accuracy problem
this was written to fix.
"""
import numpy as np

WEATHER_FACTOR = {"Clear": 1.00, "Cloudy": 0.97, "Rain": 0.90, "Fog": 0.85, "Storm": 0.75}
TRAFFIC_FACTOR = {"Low": 1.00, "Medium": 0.92, "High": 0.82}
EMISSION_FACTOR = {"Diesel": 2.68, "Petrol": 2.31, "CNG": 1.90, "Electric": 0.15}  # kg CO2 per mileage-unit
PRICE_PER_UNIT = {"Diesel": 95, "Petrol": 106, "CNG": 75, "Electric": 9}  # Rs per mileage-unit


def effective_mileage(mileage, weather, traffic, load_kg, capacity_kg):
    weather_f = WEATHER_FACTOR.get(weather, 0.95)
    traffic_f = TRAFFIC_FACTOR.get(traffic, 0.95)
    load_ratio = min(max(load_kg / max(capacity_kg, 1), 0), 1.3)
    load_f = 1 - 0.15 * load_ratio
    return max(mileage * weather_f * traffic_f * load_f, 1.0)


def compute_fuel_co2_cost(distance_km, mileage, weather, traffic, load_kg, capacity_kg, fuel_type, rng=None):
    """Returns (fuel_used_l, co2_kg, fuel_cost). Pass a numpy Generator as rng
    for reproducible noise, or omit it for a purely deterministic estimate
    (used when correcting individual historical rows, where a fresh random
    draw per row is fine either way since we're not evaluating held-out MAE)."""
    eff = effective_mileage(mileage, weather, traffic, load_kg, capacity_kg)
    noise_fuel = 1.0 if rng is None else float(np.clip(rng.normal(1.0, 0.04), 0.90, 1.10))
    fuel = max(distance_km / eff * noise_fuel, 0.5)
    co2_noise = 1.0 if rng is None else float(np.clip(rng.normal(1.0, 0.02), 0.90, 1.10))
    co2 = fuel * EMISSION_FACTOR.get(fuel_type, 2.3) * co2_noise
    cost = fuel * PRICE_PER_UNIT.get(fuel_type, 95)  # deterministic given fuel — see train.py notes
    return round(fuel, 2), round(co2, 2), round(cost, 2)


def maintenance_risk_rule(mileage, distance_km, load_kg, capacity_kg, mileage_low_cut, distance_high_cut,
                           rng=None, vehicle_age_years=None, total_km=None, days_since_service=None,
                           breakdown_count=None, fuel_efficiency_drop_pct=None,
                           age_high_cut=6.0, total_km_high_cut=150000, days_since_service_high_cut=180,
                           fuel_drop_high_cut=12.0, threshold_high=None, threshold_low=0):
    """Discrete threshold rule (not a continuous score cut into tertiles —
    that puts too many points on a fuzzy boundary for any classifier to
    learn cleanly). mileage_low_cut / distance_high_cut should be the
    1/3 and 0.65 quantiles of mileage/distance across the whole fleet/corpus
    respectively, so an individual row can be corrected consistently with
    however the rest of the corpus was labeled. Likewise, age_high_cut /
    total_km_high_cut / days_since_service_high_cut / fuel_drop_high_cut
    should be calibrated against the corpus's own quantiles (e.g. ~0.65)
    rather than left at the defaults, which are just reasonable real-world
    ballpark numbers, not tuned to any particular dataset's distribution.

    The vehicle_age_years / total_km / days_since_service / breakdown_count /
    fuel_efficiency_drop_pct arguments are optional so existing call sites
    that don't have that history yet keep working unchanged - a vehicle's
    actual maintenance record (when available) is a stronger risk signal
    than trip-level load/distance alone, so it gets 3 of the available
    points below instead of being bolted on as a single extra flag."""
    load_ratio = min(max(load_kg / max(capacity_kg, 1), 0), 1.3)
    points = int(mileage <= mileage_low_cut) + int(distance_km >= distance_high_cut) + int(load_ratio >= 0.75)

    if vehicle_age_years is not None:
        points += int(vehicle_age_years >= age_high_cut)
    if total_km is not None:
        points += int(total_km >= total_km_high_cut)
    if days_since_service is not None:
        points += int(days_since_service >= days_since_service_high_cut)
    if breakdown_count is not None:
        points += int(breakdown_count >= 1)
    if fuel_efficiency_drop_pct is not None:
        points += int(fuel_efficiency_drop_pct >= fuel_drop_high_cut)

    if threshold_high is None:
        threshold_high = 3 if vehicle_age_years is not None else 2  # more signals available -> raise the bar for "High"
    risk = "High" if points >= threshold_high else "Medium" if points > threshold_low else "Low"
    if rng is not None and rng.random() < 0.05:
        risk = rng.choice([c for c in ("Low", "Medium", "High") if c != risk])
    return risk


def recommended_route_rule(weather, traffic, distance_km, rng=None):
    if traffic == "High" or weather in ("Storm", "Fog"):
        route = "Eco"
    elif traffic == "Low" and weather in ("Clear", "Cloudy") and distance_km < 100:
        route = "Fastest"
    else:
        route = "Shortest"
    if rng is not None and rng.random() < 0.07:
        route = rng.choice([c for c in ("Eco", "Fastest", "Shortest") if c != route])
    return route

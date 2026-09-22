import statistics
from flask import Blueprint, request, jsonify
from models.db import db, Trip, Driver, Vehicle, Notification, Settings, RouteDeviation, CarbonMethodology, TripFeedback, utcnow
from routes.auth_utils import token_required
from ml.predict import predict_trip
from errors import ValidationError, ForbiddenError, ConflictError, NotFoundError
from validators import (
    require_fields, validate_positive_number, validate_lat_lng, validate_fuel_liters, validate_fuel_price,
    validate_range, validate_rating, validate_choice, validate_text_length,
    VALID_FEEDBACK_EXPERIENCES, FEEDBACK_COMMENTS_MAX_LEN,
)
from extensions import limiter
from audit import log_driver_action
from idempotency import idempotent
from notifications import notify
from routes.driver import destination_status

trips_bp = Blueprint("trips", __name__)


def _require_active_driver(driver):
    """Section 8/13: a Pending/Rejected/Blocked driver must never be able to
    perform protected trip operations, even with a still-valid JWT issued
    before an admin changed their status."""
    if driver.status != "Approved":
        raise ForbiddenError(
            f"Your account is not active ({driver.status}). Contact admin.",
            code="DRIVER_NOT_ACTIVE",
        )


@trips_bp.route("/predict", methods=["POST"])
@token_required(["driver"])
@limiter.limit("30/minute")
def predict():
    """Step 6 of Driver Workflow: AI Predictions & Recommendations.
    Called after the driver enters trip details + route options + weather are fetched."""
    data = request.get_json(force=True)
    driver = db.get_or_404(Driver, request.user["user_id"])
    vehicle = db.session.get(Vehicle, driver.assigned_vehicle_id) if driver.assigned_vehicle_id else None
    if not vehicle:
        return jsonify({"error": "No vehicle assigned to this driver. Contact admin."}), 400

    # Section 27 (ML Input Validation): reject NaN/Infinity/out-of-range
    # values before they ever reach the model - a Python float() call happily
    # accepts "Infinity"/"-Infinity" (valid JSON per Python's parser even
    # though it isn't valid strict JSON), so this isn't just a type check.
    distance_km = validate_positive_number(data.get("distance_km"), "distance_km", allow_zero=False, required=True, max_value=5000)
    load_kg = validate_positive_number(data.get("load_kg"), "load_kg", allow_zero=True, required=False, max_value=100000) or 0
    temperature = validate_range(data.get("temperature", 28), "temperature", -30, 60, required=False)
    humidity = validate_range(data.get("humidity", 60), "humidity", 0, 100, required=False)
    wind_kmph = validate_positive_number(data.get("wind_kmph", 10), "wind_kmph", allow_zero=True, required=False, max_value=300)
    delay_min = validate_positive_number(data.get("delay_min", 5), "delay_min", allow_zero=True, required=False, max_value=1440)
    avg_speed = validate_positive_number(data.get("avg_speed", 45), "avg_speed", allow_zero=True, required=False, max_value=300)

    recent_avg_fuel_per_km = None
    recent_trips = (Trip.query.filter_by(vehicle_id=vehicle.id, status="Completed")
                     .filter(Trip.actual_fuel_l.isnot(None), Trip.distance_km > 0)
                     .order_by(Trip.ended_at.desc()).limit(10).all())
    if recent_trips:
        ratios = [t.actual_fuel_l / t.distance_km for t in recent_trips if t.distance_km]
        if ratios:
            recent_avg_fuel_per_km = sum(ratios) / len(ratios)

    result = predict_trip(
        distance_km=distance_km,
        load_kg=load_kg,
        mileage=vehicle.mileage or 10,
        capacity_kg=vehicle.capacity_kg or 1000,
        route=data.get("route", "Shortest"),
        weather=data.get("weather", "Clear"),
        traffic=data.get("traffic", "Medium"),
        vehicle_type=vehicle.vehicle_type,
        fuel_type=vehicle.fuel_type,
        temperature=temperature,
        humidity=humidity,
        wind_kmph=wind_kmph,
        delay_min=delay_min,
        avg_speed=avg_speed,
        vehicle_row=vehicle,
        recent_avg_fuel_per_km=recent_avg_fuel_per_km,
    )
    return jsonify(result)


def _notify_setting_enabled(key):
    row = Settings.query.filter_by(key=key).first()
    return (row.value if row else "true") == "true"


@trips_bp.route("", methods=["POST"])
@token_required(["driver"])
@limiter.limit("20/minute")
@idempotent("trip.create")
def create_trip():
    data = request.get_json(force=True) or {}
    driver = db.get_or_404(Driver, request.user["user_id"])
    _require_active_driver(driver)
    if not driver.assigned_vehicle_id:
        return jsonify({"error": "No vehicle assigned"}), 400
    vehicle = db.session.get(Vehicle, driver.assigned_vehicle_id)
    if not vehicle or vehicle.status != "Active":
        raise ForbiddenError("Your assigned vehicle is not active. Contact admin.", code="VEHICLE_NOT_ACTIVE")

    require_fields(data, ["source", "destination", "distance_km"])
    data["distance_km"] = validate_positive_number(data.get("distance_km"), "distance_km", allow_zero=False, required=True)
    if data.get("load_kg") is not None:
        data["load_kg"] = validate_positive_number(data.get("load_kg"), "load_kg", allow_zero=True, required=False)
        if vehicle and vehicle.capacity_kg and data["load_kg"] > vehicle.capacity_kg:
            raise ValidationError(f"load_kg ({data['load_kg']}) exceeds the assigned vehicle's rated capacity ({vehicle.capacity_kg} kg)")
    for lat_f, lng_f in (("origin_lat", "origin_lng"), ("dest_lat", "dest_lng")):
        if data.get(lat_f) is not None or data.get(lng_f) is not None:
            validate_lat_lng(data.get(lat_f), data.get(lng_f))

    src = (data.get("source") or "").strip()
    dst = (data.get("destination") or "").strip()
    if src and dst and src.lower() == dst.lower():
        raise ValidationError("Source and destination cannot be the same.")
    # If both endpoints were geocoded, catch the "different text, same place"
    # case too (e.g. two spellings of the same address) rather than relying
    # on string equality alone.
    if (data.get("origin_lat") is not None and data.get("dest_lat") is not None
            and abs(data["origin_lat"] - data["dest_lat"]) < 1e-5
            and abs(data["origin_lng"] - data["dest_lng"]) < 1e-5):
        raise ValidationError("Source and destination cannot be the same location.")

    # One active (Ongoing) trip at a time - checked here too (not just at
    # /start) so a driver can't stack up multiple Planned trips indefinitely
    # while one is already Ongoing. The database-level partial unique index
    # (models/db.py: uq_trip_one_ongoing_per_driver) is still the actual
    # race-condition guard; this is just a friendlier pre-check.
    if Trip.query.filter_by(driver_id=driver.id, status="Ongoing").first():
        raise ConflictError("You already have a trip in progress. Finish it before starting a new one.",
                             code="ACTIVE_TRIP_EXISTS")

    last = Trip.query.order_by(Trip.id.desc()).first()
    trip_code = f"T{((last.id if last else 0) + 1):06d}"

    ai = data.get("ai_prediction", {})
    trip = Trip(
        trip_code=trip_code, driver_id=driver.id, vehicle_id=driver.assigned_vehicle_id,
        source=data.get("source"), destination=data.get("destination"),
        distance_km=data.get("distance_km"), load_kg=data.get("load_kg"),
        purpose=data.get("purpose"), preferred_route=data.get("preferred_route"),
        route_chosen=data.get("route_chosen", data.get("preferred_route")),
        weather_condition=data.get("weather"), traffic_condition=data.get("traffic"),
        predicted_fuel_l=ai.get("predicted_fuel_l"), predicted_co2_kg=ai.get("predicted_co2_kg"),
        predicted_cost=ai.get("predicted_cost"), predicted_eco_score=ai.get("predicted_eco_score"),
        maintenance_risk=ai.get("maintenance_risk"), recommended_route=ai.get("recommended_route"),
        ai_confidence=ai.get("ai_confidence"), status="Planned",
        origin_lat=data.get("origin_lat"), origin_lng=data.get("origin_lng"),
        dest_lat=data.get("dest_lat"), dest_lng=data.get("dest_lng"),
        estimated_duration_min=data.get("estimated_duration_min"),
        route_polyline=data.get("route_polyline"),
    )
    db.session.add(trip)
    db.session.flush()  # get trip.id before commit for notification linkage

    # ---- Automated alerts (Notification Center: A7 weather/fuel/traffic) ----
    weather = (data.get("weather") or "").lower()
    traffic = (data.get("traffic") or "").lower()

    if weather in ("storm", "fog") and _notify_setting_enabled("notify_weather"):
        notify(
            audience="admin", notif_type="WEATHER", priority="WARNING",
            title="Trip starting in poor weather", category="weather",
            message=f"{driver.name} is starting trip {trip.trip_code} in {data.get('weather')} conditions — route: {trip.source} to {trip.destination}.",
            driver_id=driver.id, trip_id=trip.id,
        )

    if traffic == "high" and _notify_setting_enabled("notify_traffic"):
        notify(
            audience="admin", notif_type="TRIP", priority="WARNING",
            title="Heavy traffic on active trip", category="traffic",
            message=f"Heavy traffic reported for {trip.trip_code} ({trip.source} to {trip.destination}) — expect delays.",
            driver_id=driver.id, trip_id=trip.id,
        )

    if vehicle and ai.get("predicted_fuel_l") and vehicle.capacity_kg:
        load_ratio = (data.get("load_kg") or 0) / vehicle.capacity_kg
        if load_ratio > 0.95 and _notify_setting_enabled("notify_maintenance"):
            notify(
                audience="admin", notif_type="VEHICLE", priority="WARNING",
                title="Vehicle overloaded", category="fuel",
                message=f"{trip.trip_code} is loaded at {round(load_ratio*100)}% of {vehicle.vehicle_no}'s rated capacity — fuel efficiency will be reduced.",
                driver_id=driver.id, trip_id=trip.id, vehicle_id=vehicle.id,
            )

    db.session.commit()
    return jsonify(trip.to_dict()), 201


@trips_bp.route("/<int:trip_id>/start", methods=["POST"])
@token_required(["driver"])
@limiter.limit("20/minute")
@idempotent(lambda trip_id: f"trip.start:{trip_id}")
def start_trip(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    if trip.driver_id != request.user["user_id"]:
        return jsonify({"error": "Forbidden"}), 403
    driver = db.get_or_404(Driver, trip.driver_id)
    _require_active_driver(driver)

    # A driver should never end up with two IN_PROGRESS ("Ongoing") trips at
    # once — if one is already active, hand that one back instead of
    # silently creating a second active trip (which is what let the old
    # frontend-only trip state get out of sync with the backend).
    existing_active = Trip.query.filter(
        Trip.driver_id == trip.driver_id, Trip.status == "Ongoing", Trip.id != trip.id,
    ).order_by(Trip.started_at.desc()).first()
    if existing_active:
        return jsonify({
            "error": "You already have a trip in progress. Finish it before starting a new one.",
            "trip": existing_active.to_dict(),
        }), 409

    if trip.status == "Ongoing":
        # Already started (e.g. duplicate click) — return the same trip rather than re-stamping started_at.
        return jsonify(trip.to_dict())

    trip.status = "Ongoing"
    trip.started_at = utcnow()
    log_driver_action("trip.start", "Trip", trip.id, {"trip_code": trip.trip_code})
    notify(
        audience="driver", notif_type="TRIP", priority="INFO",
        title="Trip started", category="trip_started",
        message=f"Trip {trip.trip_code} to {trip.destination} has started.",
        driver_id=trip.driver_id, trip_id=trip.id,
    )
    db.session.commit()
    return jsonify(trip.to_dict())


@trips_bp.route("/<int:trip_id>/end", methods=["POST"])
@token_required(["driver"])
@limiter.limit("20/minute")
@idempotent(lambda trip_id: f"trip.end:{trip_id}")
def end_trip(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    if trip.driver_id != request.user["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    # Idempotent completion: if this trip was already completed (e.g. a
    # duplicate/race request from a double-click, or the driver retried
    # after a flaky network response) hand back the existing completed
    # record instead of recalculating or erroring. Never corrupt already
    # -saved final trip data.
    if trip.status == "Completed":
        return jsonify(trip.to_dict())

    if trip.status != "Ongoing":
        return jsonify({"error": f"Trip cannot be ended from status '{trip.status}'."}), 400

    data = request.get_json(silent=True) or {}

    # Sections 15-18 (5km Destination Lock): the frontend disabling the End
    # Trip button is only a convenience — this is the actual, authoritative
    # check. A direct API call (bypassing the UI entirely) must fail exactly
    # the same way. Reuses the identical distance/accuracy logic the
    # location-ping endpoint already surfaces to the frontend, so the two
    # can never disagree about whether the driver has arrived.
    dest_status = destination_status(trip)
    if not dest_status["destination_known"]:
        raise ValidationError(
            "Destination coordinates are missing for this trip — cannot verify arrival.",
            code="DESTINATION_UNKNOWN",
        )
    if not dest_status["gps_available"]:
        raise ValidationError(
            "Unable to verify your location. Send a GPS location update before ending the trip.",
            code="LOCATION_UNAVAILABLE",
        )
    if not dest_status["gps_accuracy_ok"]:
        raise ValidationError(
            "GPS accuracy is too low to verify arrival.",
            code="GPS_ACCURACY_TOO_LOW",
        )
    if not dest_status["destination_reached"]:
        raise ValidationError(
            f"You have not reached the destination yet ({dest_status['distance_to_destination_m']}m away; "
            f"must be within {dest_status['arrival_radius_m']}m).",
            code="DESTINATION_NOT_REACHED",
        )

    # Sections 18/19: driver must enter actual fuel and fuel price - never
    # hardcoded, never optional. (Existing trips that predate this change
    # and only ever set predicted_* values are unaffected; this validation
    # only applies going forward, at the point of ending a NEW trip.)
    actual_fuel_l = validate_fuel_liters(data.get("actual_fuel_l"), "actual_fuel_l", required=True)
    actual_fuel_price = validate_fuel_price(data.get("actual_fuel_price"), "actual_fuel_price", required=True)

    try:
        trip.status = "Completed"
        trip.ended_at = utcnow()
        RouteDeviation.query.filter_by(trip_id=trip.id, status="Active").update(
            {"status": "Resolved", "resolved_at": trip.ended_at}
        )

        # Section 20/21: carbon/cost are ALWAYS computed here, server-side,
        # from the driver-entered fuel + the CURRENTLY ACTIVE
        # CarbonMethodology's emission-factor snapshot (not the live
        # ml/data_formulas.py constants directly) - so this trip's
        # methodology_id permanently records exactly which numbers were
        # used, and stays reproducible even after an admin activates a new
        # methodology version later. Any client-submitted actual_co2_kg /
        # actual_cost in the request body is ignored - ignored, not merely
        # unused - so a tampered request body can't inject a fabricated
        # carbon figure into the trusted record.
        vehicle = db.session.get(Vehicle, trip.vehicle_id)
        fuel_type = vehicle.fuel_type if vehicle else None
        methodology = CarbonMethodology.query.filter_by(is_active=True).first()
        if methodology is None:
            # Should only happen on a database that skipped the app-startup
            # seed entirely (e.g. a raw `flask db upgrade` with seeding
            # disabled) - fail loudly rather than silently using an
            # unversioned fallback, since an unattributed CO2 figure is
            # exactly what section 21 exists to prevent.
            raise RuntimeError(
                "No active CarbonMethodology found - cannot compute an authoritative "
                "CO2 figure without one. Seed one via _seed_default_carbon_methodology() "
                "or POST /api/v1/admin/carbon-methodologies."
            )
        emission_factor = methodology.emission_factor_for(fuel_type)

        trip.actual_fuel_l = actual_fuel_l
        trip.actual_fuel_price = actual_fuel_price
        trip.actual_co2_kg = round(actual_fuel_l * emission_factor, 2)
        trip.actual_cost = round(actual_fuel_l * actual_fuel_price, 2)
        trip.co2_methodology_version = methodology.version_label
        trip.methodology_id = methodology.id

        # Update driver eco score (rolling average toward predicted eco score of this trip)
        driver = db.session.get(Driver, trip.driver_id)
        if trip.predicted_eco_score is not None:
            driver.eco_score = round((driver.eco_score * 0.8) + (trip.predicted_eco_score * 0.2), 1)

        # Vehicle health nudge based on maintenance risk flagged during the trip
        if vehicle and trip.distance_km:
            vehicle.total_km = (vehicle.total_km or 0) + trip.distance_km
        if vehicle and trip.maintenance_risk == "High":
            vehicle.health_score = max(0, vehicle.health_score - 5)
            notify(
                audience="admin", notif_type="VEHICLE", priority="WARNING",
                title="High maintenance risk", category="maintenance",
                message=f"High maintenance risk flagged on vehicle {vehicle.vehicle_no} after trip {trip.trip_code}.",
                trip_id=trip.id, vehicle_id=vehicle.id,
            )
            notify(
                audience="driver", notif_type="VEHICLE", priority="WARNING",
                title="Vehicle maintenance risk", category="maintenance",
                message=f"Your assigned vehicle {vehicle.vehicle_no} was flagged HIGH maintenance risk after this trip. Please report any issues to admin.",
                driver_id=trip.driver_id, trip_id=trip.id, vehicle_id=vehicle.id,
            )

        # Section 10/20/45: notify on trip completion and on predicted-vs-actual
        # carbon variance so the driver isn't left to dig it out of a report.
        notify(
            audience="driver", notif_type="TRIP", priority="INFO",
            title="Trip completed", category="trip_completed",
            message=f"Trip {trip.trip_code} completed. Actual CO2: {trip.actual_co2_kg} kg, cost: ₹{trip.actual_cost}.",
            driver_id=trip.driver_id, trip_id=trip.id,
        )
        if trip.predicted_co2_kg and trip.actual_co2_kg and trip.predicted_co2_kg > 0:
            co2_variance_pct = round(((trip.actual_co2_kg - trip.predicted_co2_kg) / trip.predicted_co2_kg) * 100, 1)
            if co2_variance_pct >= 20:
                notify(
                    audience="driver", notif_type="CARBON", priority="WARNING",
                    title="Actual CO2 well above prediction", category="carbon_variance",
                    message=f"Trip {trip.trip_code} emitted {co2_variance_pct}% more CO2 than predicted. Possible causes: route deviation, traffic, weather, or load.",
                    driver_id=trip.driver_id, trip_id=trip.id,
                )
                notify(
                    audience="admin", notif_type="CARBON", priority="WARNING",
                    title="High-carbon trip", category="carbon_variance",
                    message=f"Trip {trip.trip_code} ({driver.name}) emitted {co2_variance_pct}% more CO2 than predicted ({trip.actual_co2_kg} kg vs {trip.predicted_co2_kg} kg predicted).",
                    driver_id=trip.driver_id, trip_id=trip.id, vehicle_id=vehicle.id if vehicle else None,
                )

        # ---- Anomaly detection: is this trip's CO2 a statistical outlier for its vehicle type? ----
        if vehicle and trip.actual_co2_kg:
            peers = Trip.query.join(Vehicle, Trip.vehicle_id == Vehicle.id) \
                .filter(Vehicle.vehicle_type == vehicle.vehicle_type, Trip.status == "Completed",
                        Trip.actual_co2_kg.isnot(None)).all()
            values = [t.actual_co2_kg for t in peers]
            if len(values) >= 5:
                mean = statistics.mean(values)
                stdev = statistics.pstdev(values) or 1
                z = (trip.actual_co2_kg - mean) / stdev
                if z > 2:
                    trip.is_anomaly = True
                    notify(
                        audience="admin", notif_type="CARBON", priority="WARNING",
                        title="Anomalous high-CO2 trip", category="anomaly",
                        message=f"Trip {trip.trip_code} emitted {trip.actual_co2_kg} kg CO2 — {round(z,1)} std. deviations above the {vehicle.vehicle_type} fleet average.",
                        driver_id=driver.id, trip_id=trip.id, vehicle_id=vehicle.id,
                    )

        log_driver_action("trip.end", "Trip", trip.id, {
            "trip_code": trip.trip_code, "actual_fuel_l": trip.actual_fuel_l,
            "actual_co2_kg": trip.actual_co2_kg, "co2_methodology_version": trip.co2_methodology_version,
        })
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify(trip.to_dict())


@trips_bp.route("/<int:trip_id>/feedback", methods=["POST"])
@token_required(["driver"])
@limiter.limit("20/minute")
@idempotent(lambda trip_id: f"trip.feedback:{trip_id}")
def submit_trip_feedback(trip_id):
    """Post-Trip Feedback. Shown to the driver right after End Trip
    completes, before the trip summary — but not gated to that exact
    moment: any driver who owns a Completed trip may submit feedback for it
    once (matching the "Skip for now" flow, where the driver may return
    later without the frontend forcing the decision now)."""
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("Trip not found.")

    # IDOR guard: a driver may only leave feedback on their own trip, never
    # another driver's, even by guessing/incrementing trip IDs.
    if trip.driver_id != request.user["user_id"]:
        raise ForbiddenError("You may only submit feedback for your own trips.")

    # Feedback only makes sense once a trip has actually finished — an
    # Ongoing/Planned/Cancelled trip has no "how was your trip" to answer yet.
    if trip.status != "Completed":
        raise ValidationError(
            f"Feedback can only be submitted for a completed trip (current status: '{trip.status}').",
            code="TRIP_NOT_COMPLETED",
        )

    # One feedback submission per trip. The DB-level unique constraint
    # (models/db.py: uq_tripfeedback_trip_id) is the real race-condition
    # guard; this is the friendlier pre-check that gives a clear message
    # for the common (non-racing) case.
    if TripFeedback.query.filter_by(trip_id=trip.id).first() is not None:
        raise ConflictError("Feedback has already been submitted for this trip.", code="FEEDBACK_ALREADY_SUBMITTED")

    data = request.get_json(silent=True) or {}
    overall_rating = validate_rating(data.get("overall_rating"), "overall_rating")
    navigation_rating = validate_rating(data.get("navigation_rating"), "navigation_rating")
    eco_route_rating = validate_rating(data.get("eco_route_rating"), "eco_route_rating")
    experience = validate_choice(data.get("experience"), VALID_FEEDBACK_EXPERIENCES, "experience")
    comments = validate_text_length(data.get("comments"), "comments", FEEDBACK_COMMENTS_MAX_LEN, required=False)

    feedback = TripFeedback(
        trip_id=trip.id,
        # Never trust a driver_id from the request body — always derive it
        # from the authenticated JWT, same as the ownership check above.
        driver_id=request.user["user_id"],
        overall_rating=overall_rating,
        navigation_rating=navigation_rating,
        eco_route_rating=eco_route_rating,
        experience=experience,
        comments=comments,
    )
    db.session.add(feedback)
    try:
        log_driver_action("trip.feedback", "Trip", trip.id, {
            "trip_code": trip.trip_code, "overall_rating": overall_rating,
            "navigation_rating": navigation_rating, "eco_route_rating": eco_route_rating,
            "experience": experience,
        })
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify(feedback.to_dict()), 201


@trips_bp.route("/<int:trip_id>/feedback", methods=["GET"])
@token_required(["driver", "admin"])
def get_trip_feedback(trip_id):
    """Lets the frontend check whether feedback already exists for a trip
    (e.g. after a page refresh mid-flow) without relying on client-side
    state alone. Shares the same driver/admin access rule as GET /trips/<id>."""
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("Trip not found.")
    if request.user["role"] == "driver" and trip.driver_id != request.user["user_id"]:
        raise ForbiddenError("Forbidden")
    feedback = TripFeedback.query.filter_by(trip_id=trip.id).first()
    return jsonify(feedback.to_dict() if feedback else None)


@trips_bp.route("/<int:trip_id>", methods=["GET"])
@token_required(["driver", "admin"])
def get_trip(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    # IDOR guard: this route is intentionally shared between drivers and
    # admins (unlike most driver_bp routes, which are driver-only by
    # construction), so the ownership check has to happen here explicitly.
    # An admin may view any trip; a driver may only view their own - never
    # trust the driver/admin split alone to imply "this caller may see this
    # resource."
    if request.user["role"] == "driver" and trip.driver_id != request.user["user_id"]:
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(trip.to_dict())

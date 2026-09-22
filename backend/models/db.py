from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json

db = SQLAlchemy()


def utcnow():
    """Naive UTC 'now' - matches the exact semantics datetime.utcnow() used to
    provide, which is what every timestamp column/comparison in this codebase
    assumes (SQLite/Postgres DateTime columns here are naive, not tz-aware).
    datetime.utcnow() itself is deprecated as of Python 3.12 and scheduled for
    removal; this wrapper keeps the identical naive-datetime behavior
    everywhere without the deprecation warning, and without the breakage that
    switching to aware datetimes would cause when compared against existing
    naive values already in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)



class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), default="Admin")  # "SuperAdmin" or "Admin"
    status = db.Column(db.String(20), default="Active")
    # Section 4 (brute-force protection): per-account lockout, on top of the
    # IP-based rate limiting on /auth/login. Five consecutive bad passwords
    # locks THIS account for 15 minutes regardless of which IP is trying it
    # (so a distributed brute-force attempt across many IPs is still
    # stopped, not just a single-IP one).
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "username": self.username,
                "role": self.role, "status": self.status,
                "created_at": self.created_at.isoformat() if self.created_at else None}


class Depot(db.Model):
    """A branch/hub location. Not full multi-tenancy (separate isolated
    companies) — this is one organization operating multiple depots, which
    covers the common "fleet spread across branch offices" case without the
    much larger scope of per-tenant data isolation and auth."""
    __tablename__ = "depots"
    id = db.Column(db.Integer, primary_key=True)
    depot_code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(80))
    address = db.Column(db.String(255))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id, "depot_code": self.depot_code, "name": self.name,
            "city": self.city, "address": self.address, "lat": self.lat, "lng": self.lng,
        }


class Driver(db.Model):
    __tablename__ = "drivers"
    id = db.Column(db.Integer, primary_key=True)
    driver_code = db.Column(db.String(20), unique=True)  # D0001 style
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20), unique=True)
    dob = db.Column(db.String(20))
    address = db.Column(db.String(255))
    license_no = db.Column(db.String(60))
    experience_years = db.Column(db.Integer, default=0)
    emergency_contact = db.Column(db.String(20))
    license_doc_path = db.Column(db.String(255))
    profile_photo_path = db.Column(db.String(255))
    address_proof_path = db.Column(db.String(255))
    eco_score = db.Column(db.Float, default=70)
    status = db.Column(db.String(20), default="Pending")  # Pending / Approved / Rejected / Blocked
    rejection_reason = db.Column(db.String(255))
    # Section 4 (brute-force protection): see Admin.failed_login_attempts above.
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    assigned_vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    depot_id = db.Column(db.Integer, db.ForeignKey("depots.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    trips = db.relationship("Trip", backref="driver", lazy=True)

    def to_dict(self, include_sensitive=False):
        d = {
            "id": self.id, "driver_code": self.driver_code, "name": self.name,
            "username": self.username, "email": self.email, "phone": self.phone,
            "license_no": self.license_no, "experience_years": self.experience_years,
            "eco_score": self.eco_score, "status": self.status,
            "assigned_vehicle_id": self.assigned_vehicle_id,
            "depot_id": self.depot_id,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return d


class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_code = db.Column(db.String(20), unique=True)
    vehicle_no = db.Column(db.String(30), unique=True, nullable=False)
    vehicle_type = db.Column(db.String(40))
    fuel_type = db.Column(db.String(30))
    mileage = db.Column(db.Float)
    capacity_kg = db.Column(db.Float)
    status = db.Column(db.String(20), default="Active")
    health_score = db.Column(db.Float, default=90)
    insurance_expiry = db.Column(db.Date)
    permit_expiry = db.Column(db.Date)
    pollution_cert_expiry = db.Column(db.Date)
    depot_id = db.Column(db.Integer, db.ForeignKey("depots.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # ---- Maintenance-history fields (Priority 1 #6: Maintenance Model) ----
    # Real usage/service history instead of just point-in-time trip stats -
    # these are what actually distinguish "old, poorly serviced, breakdown-
    # prone vehicle" from "young, well-serviced one" for the maintenance
    # classifier. No IoT/sensors involved - total_km accumulates from
    # completed trips (routes/trips.py:end_trip) and the rest comes from
    # admin-logged ServiceRecord entries, both things a real fleet office
    # already tracks on paper/spreadsheets today.
    purchase_date = db.Column(db.Date)  # vehicle age = today - purchase_date
    total_km = db.Column(db.Float, default=0)  # lifetime odometer, accumulated from completed trips
    last_service_date = db.Column(db.Date)
    service_count = db.Column(db.Integer, default=0)
    breakdown_count = db.Column(db.Integer, default=0)
    maintenance_cost_total = db.Column(db.Float, default=0)

    __table_args__ = (
        db.CheckConstraint("capacity_kg IS NULL OR capacity_kg > 0", name="ck_vehicle_capacity_positive"),
        db.CheckConstraint("mileage IS NULL OR mileage > 0", name="ck_vehicle_mileage_positive"),
        db.CheckConstraint("health_score IS NULL OR (health_score >= 0 AND health_score <= 100)", name="ck_vehicle_health_score_range"),
    )

    drivers = db.relationship("Driver", backref="vehicle", lazy=True)

    def to_dict(self):
        age_years = None
        if self.purchase_date:
            age_years = round((utcnow().date() - self.purchase_date).days / 365.25, 1)
        days_since_service = None
        if self.last_service_date:
            days_since_service = (utcnow().date() - self.last_service_date).days
        return {
            "id": self.id, "vehicle_code": self.vehicle_code, "vehicle_no": self.vehicle_no,
            "vehicle_type": self.vehicle_type, "fuel_type": self.fuel_type,
            "mileage": self.mileage, "capacity_kg": self.capacity_kg,
            "status": self.status, "health_score": self.health_score,
            "insurance_expiry": self.insurance_expiry.isoformat() if self.insurance_expiry else None,
            "permit_expiry": self.permit_expiry.isoformat() if self.permit_expiry else None,
            "pollution_cert_expiry": self.pollution_cert_expiry.isoformat() if self.pollution_cert_expiry else None,
            "depot_id": self.depot_id,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "vehicle_age_years": age_years,
            "total_km": round(self.total_km, 1) if self.total_km is not None else 0,
            "last_service_date": self.last_service_date.isoformat() if self.last_service_date else None,
            "days_since_service": days_since_service,
            "service_count": self.service_count or 0,
            "breakdown_count": self.breakdown_count or 0,
            "maintenance_cost_total": round(self.maintenance_cost_total, 2) if self.maintenance_cost_total else 0,
        }


class ServiceRecord(db.Model):
    """One row per admin-logged service/maintenance event for a vehicle -
    the "Service History" the maintenance model is trained against.
    Logging one updates the parent Vehicle's rollup fields (service_count,
    last_service_date, maintenance_cost_total, breakdown_count)."""
    __tablename__ = "service_records"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    service_date = db.Column(db.Date, nullable=False)
    service_type = db.Column(db.String(60))  # e.g. "Routine", "Breakdown Repair", "Tyre Change"
    cost = db.Column(db.Float, default=0)
    was_breakdown = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.CheckConstraint("cost >= 0", name="ck_servicerecord_cost_non_negative"),
    )

    def to_dict(self):
        return {
            "id": self.id, "vehicle_id": self.vehicle_id,
            "service_date": self.service_date.isoformat() if self.service_date else None,
            "service_type": self.service_type, "cost": self.cost,
            "was_breakdown": self.was_breakdown, "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Trip(db.Model):
    __tablename__ = "trips"
    id = db.Column(db.Integer, primary_key=True)
    trip_code = db.Column(db.String(20), unique=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)

    source = db.Column(db.String(150))
    destination = db.Column(db.String(150))
    distance_km = db.Column(db.Float)
    load_kg = db.Column(db.Float)
    purpose = db.Column(db.String(150))
    preferred_route = db.Column(db.String(50))  # Eco / Shortest / Fastest

    route_chosen = db.Column(db.String(50))
    weather_condition = db.Column(db.String(50))
    traffic_condition = db.Column(db.String(50))

    predicted_fuel_l = db.Column(db.Float)
    predicted_co2_kg = db.Column(db.Float)
    predicted_cost = db.Column(db.Float)
    predicted_eco_score = db.Column(db.Float)
    maintenance_risk = db.Column(db.String(20))
    recommended_route = db.Column(db.String(50))
    ai_confidence = db.Column(db.Float)

    # Geocoded coordinates + estimated duration, used for simulated live position
    # on the admin Live Fleet map and for the turn-by-turn navigation panel.
    origin_lat = db.Column(db.Float)
    origin_lng = db.Column(db.Float)
    dest_lat = db.Column(db.Float)
    dest_lng = db.Column(db.Float)
    estimated_duration_min = db.Column(db.Float)
    is_anomaly = db.Column(db.Boolean, default=False)

    # Encoded polyline of the route the driver picked at planning time — kept so
    # live GPS pings can be checked against it for automatic deviation detection.
    route_polyline = db.Column(db.Text)
    deviation_flagged = db.Column(db.Boolean, default=False)

    actual_fuel_l = db.Column(db.Float)
    actual_co2_kg = db.Column(db.Float)
    actual_cost = db.Column(db.Float)
    # Section 19: driver-entered fuel price at trip end (never hardcoded).
    actual_fuel_price = db.Column(db.Float)
    # Section 21 (Carbon Methodology Versioning): which EMISSION_FACTOR/
    # PRICE_PER_UNIT table version computed this trip's actual_co2_kg/
    # actual_cost, so a later change to those constants doesn't silently
    # rewrite the meaning of historical trips. Bump CO2_METHODOLOGY_VERSION
    # in routes/trips.py whenever the emission-factor table changes.
    co2_methodology_version = db.Column(db.String(20))
    methodology_id = db.Column(db.Integer, db.ForeignKey("carbon_methodologies.id"), nullable=True, index=True)

    status = db.Column(db.String(20), default="Planned", index=True)  # Planned / Ongoing / Completed / Cancelled
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.CheckConstraint("distance_km IS NULL OR distance_km > 0", name="ck_trip_distance_positive"),
        db.CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="ck_trip_load_non_negative"),
        db.CheckConstraint("status IN ('Planned','Ongoing','Completed','Cancelled')", name="ck_trip_status_valid"),
        db.CheckConstraint("actual_fuel_l IS NULL OR actual_fuel_l >= 0", name="ck_trip_actual_fuel_non_negative"),
        db.CheckConstraint("actual_fuel_price IS NULL OR actual_fuel_price >= 0", name="ck_trip_actual_fuel_price_non_negative"),
        # Section 14 (One Active Trip): a partial unique index, not just an
        # application-level check-then-act, so two concurrent "start trip"
        # requests for the same driver can't both succeed - the second
        # INSERT/UPDATE that would create a second Ongoing row for the same
        # driver_id is rejected by the database itself (IntegrityError,
        # handled centrally in errors.py -> 409 CONFLICT), regardless of
        # request timing. Supported on SQLite 3.8+ and PostgreSQL alike.
        db.Index(
            "uq_trip_one_ongoing_per_driver", "driver_id",
            unique=True,
            sqlite_where=db.text("status = 'Ongoing'"),
            postgresql_where=db.text("status = 'Ongoing'"),
        ),
    )

    def to_dict(self):
        return {
            "id": self.id, "trip_code": self.trip_code, "driver_id": self.driver_id,
            "vehicle_id": self.vehicle_id, "source": self.source, "destination": self.destination,
            "distance_km": self.distance_km, "load_kg": self.load_kg, "purpose": self.purpose,
            "preferred_route": self.preferred_route, "route_chosen": self.route_chosen,
            "weather_condition": self.weather_condition, "traffic_condition": self.traffic_condition,
            "predicted_fuel_l": self.predicted_fuel_l, "predicted_co2_kg": self.predicted_co2_kg,
            "predicted_cost": self.predicted_cost, "predicted_eco_score": self.predicted_eco_score,
            "maintenance_risk": self.maintenance_risk, "recommended_route": self.recommended_route,
            "ai_confidence": self.ai_confidence,
            "actual_fuel_l": self.actual_fuel_l, "actual_co2_kg": self.actual_co2_kg,
            "actual_cost": self.actual_cost, "actual_fuel_price": self.actual_fuel_price,
            "co2_methodology_version": self.co2_methodology_version, "methodology_id": self.methodology_id, "status": self.status,
            "prediction_error": self._prediction_error(),
            "origin_lat": self.origin_lat, "origin_lng": self.origin_lng,
            "dest_lat": self.dest_lat, "dest_lng": self.dest_lng,
            "estimated_duration_min": self.estimated_duration_min,
            "is_anomaly": self.is_anomaly,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _prediction_error(self):
        """Section 31 (Predicted vs Actual): computes the actual error
        between what the model predicted before the trip and what really
        happened, for fuel and CO2. Returns None (not a fabricated 0%) for
        any trip that isn't complete yet, or where either side of the
        comparison is missing - there is nothing honest to report until
        both numbers exist."""
        if self.status != "Completed" or self.actual_fuel_l is None or self.predicted_fuel_l is None:
            return None

        def _pct_error(predicted, actual):
            if predicted is None or actual is None:
                return None
            if predicted == 0:
                return None  # avoid divide-by-zero; a 0 prediction has no meaningful % error
            return round(((actual - predicted) / predicted) * 100, 1)

        return {
            "fuel_predicted_l": self.predicted_fuel_l,
            "fuel_actual_l": self.actual_fuel_l,
            "fuel_error_pct": _pct_error(self.predicted_fuel_l, self.actual_fuel_l),
            "co2_predicted_kg": self.predicted_co2_kg,
            "co2_actual_kg": self.actual_co2_kg,
            "co2_error_pct": _pct_error(self.predicted_co2_kg, self.actual_co2_kg),
        }


class TripFeedback(db.Model):
    """Post-trip driver feedback. One row per (trip, driver) — a driver may
    submit at most one feedback record per trip (enforced by the unique
    constraint below, on top of the application-level duplicate check in
    routes/trips.py:submit_trip_feedback). Kept as its own table rather than
    columns on Trip so feedback stays optional/append-only and doesn't force
    a migration of the (much larger, already-wide) Trip table for what is,
    functionally, a separate concern with its own lifecycle.

    Structured this way (numeric ratings + a fixed `experience` enum) so it
    can later support fleet-wide reporting (average rating by driver,
    vehicle, date, etc.) without any schema changes — see Trip relationship
    below and Vehicle/Driver already being reachable via trip.vehicle_id /
    trip.driver_id."""
    __tablename__ = "trip_feedback"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)

    overall_rating = db.Column(db.Integer, nullable=False)
    navigation_rating = db.Column(db.Integer, nullable=False)
    eco_route_rating = db.Column(db.Integer, nullable=False)
    experience = db.Column(db.String(20), nullable=False)  # Excellent / Good / Average / Poor / Very Poor
    comments = db.Column(db.String(1000))

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    trip = db.relationship("Trip", backref=db.backref("feedback", uselist=False, lazy=True))

    __table_args__ = (
        db.UniqueConstraint("trip_id", name="uq_tripfeedback_trip_id"),
        db.CheckConstraint("overall_rating >= 1 AND overall_rating <= 5", name="ck_tripfeedback_overall_rating_range"),
        db.CheckConstraint("navigation_rating >= 1 AND navigation_rating <= 5", name="ck_tripfeedback_navigation_rating_range"),
        db.CheckConstraint("eco_route_rating >= 1 AND eco_route_rating <= 5", name="ck_tripfeedback_eco_route_rating_range"),
        db.CheckConstraint(
            "experience IN ('Excellent','Good','Average','Poor','Very Poor')",
            name="ck_tripfeedback_experience_valid",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id, "trip_id": self.trip_id, "driver_id": self.driver_id,
            "overall_rating": self.overall_rating, "navigation_rating": self.navigation_rating,
            "eco_route_rating": self.eco_route_rating, "experience": self.experience,
            "comments": self.comments,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TripLocation(db.Model):
    """One row per GPS fix reported by the driver's browser while a trip is
    ongoing (this is the "DriverLocation" ping log called for in the brief -
    kept under its original name since Live Fleet, Trip Replay, and the
    deviation check already query it as TripLocation; renaming would touch
    a lot of surface area for zero functional gain). Append-only ping log —
    kept as its own table (rather than columns on Trip) so adding this
    feature doesn't require migrating the Trip table on databases that
    already exist. driver_id is denormalized here (in addition to being
    reachable via trip.driver_id) so pings can be queried/audited directly
    without a join, matching the payload fields the brief asks for."""
    __tablename__ = "trip_locations"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True, index=True)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    speed_kmph = db.Column(db.Float)  # ground speed at the time of the fix, if the device reports one
    heading = db.Column(db.Float)  # degrees, 0-360, if the device reports one
    accuracy_m = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=utcnow, index=True)

    __table_args__ = (
        db.CheckConstraint("lat >= -90 AND lat <= 90", name="ck_triploc_lat_range"),
        db.CheckConstraint("lng >= -180 AND lng <= 180", name="ck_triploc_lng_range"),
        db.CheckConstraint("speed_kmph IS NULL OR speed_kmph >= 0", name="ck_triploc_speed_non_negative"),
    )


class RouteDeviation(db.Model):
    """One row per detected route deviation (current GPS fix vs. the planned
    Google route polyline, >threshold apart). A Notification is still raised
    for the admin notification feed, but this table is the structured,
    queryable record: which trip/driver, exact location, how far off, when,
    and whether it's still open or was resolved (e.g. by an automatic
    reroute)."""
    __tablename__ = "route_deviations"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    deviation_m = db.Column(db.Float, nullable=False)
    detected_at = db.Column(db.DateTime, default=utcnow, index=True)
    status = db.Column(db.String(20), default="Active", index=True)  # Active / Resolved
    resolved_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint("status IN ('Active','Resolved')", name="ck_routedev_status_valid"),
    )

    def to_dict(self):
        trip = db.session.get(Trip, self.trip_id)
        driver = db.session.get(Driver, self.driver_id)
        return {
            "id": self.id, "trip_id": self.trip_id, "trip_code": trip.trip_code if trip else None,
            "driver_id": self.driver_id, "driver_name": driver.name if driver else None,
            "lat": self.lat, "lng": self.lng, "deviation_m": round(self.deviation_m),
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "status": self.status,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class ModelVersion(db.Model):
    """Model Registry (Priority 1 #8). One row per training run of a given
    model (fuel_model, co2_model, eco_score_model, maintenance_model,
    route_model). The actual weights for each version live in
    ml/saved/versions/{model_name}_v{version}.pkl (see ml/registry.py) -
    this table is the index: which version is currently active, when it was
    trained, on how many rows, and with what metrics, so a worse retrain can
    be identified and rolled back."""
    __tablename__ = "model_versions"
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(40), nullable=False, index=True)  # e.g. "fuel_model"
    version = db.Column(db.Integer, nullable=False)  # 1, 2, 3... per model_name
    metric_name = db.Column(db.String(40))  # e.g. "fuel_mae_l" or "maintenance_accuracy"
    metric_value = db.Column(db.Float)
    higher_is_better = db.Column(db.Boolean, default=False)
    metrics_json = db.Column(db.Text)  # full metrics dict for this run, not just the headline metric
    dataset_rows = db.Column(db.Integer)
    file_path = db.Column(db.String(255))  # path to this version's .pkl under ml/saved/versions/
    is_active = db.Column(db.Boolean, default=False, index=True)
    trained_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("model_name", "version", name="uq_modelversion_name_version"),
    )

    def to_dict(self):
        return {
            "id": self.id, "model_name": self.model_name, "version": self.version,
            "metric_name": self.metric_name, "metric_value": self.metric_value,
            "higher_is_better": self.higher_is_better,
            "metrics": json.loads(self.metrics_json) if self.metrics_json else None,
            "dataset_rows": self.dataset_rows, "is_active": self.is_active,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
        }


class OTP(db.Model):
    """OTP codes are never stored in plaintext - only a bcrypt hash
    (code_hash), checked the same way a password would be. `attempts`
    tracks failed /otp/verify calls against this specific code so it can be
    locked out after too many guesses (see routes/auth.py:MAX_OTP_ATTEMPTS),
    independent of the identifier-level request cooldown."""
    __tablename__ = "otps"
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(120), nullable=False, index=True)  # email (phone OTP removed - no SMS provider)
    code_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(40), default="registration")
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0)
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class Notification(db.Model):
    """Centralized notification feed (spec sections 18-25/45).

    `notif_type` is the canonical 5-value taxonomy the spec requires
    (TRIP / WEATHER / VEHICLE / CARBON / SYSTEM). `category` is kept as a
    finer-grained legacy/display label (e.g. "route_deviation", "fuel",
    "sos") so existing filters/i18n strings keyed on it don't break, but new
    code should treat `notif_type` as authoritative.

    `priority` is the canonical 4-value scale (INFO / ACTION / WARNING /
    CRITICAL). `severity` is kept in lockstep (lowercased) for backward
    compatibility with any code/UI still reading it.

    `dedup_key` + `active` implement stateful dedup/cooldown (section 44):
    a new event with the same dedup_key while an earlier one is still
    `active=True` is suppressed rather than creating a duplicate row; the
    engine (see notifications.py) resolves the old one first (active=False)
    when the underlying condition clears (e.g. route restored) so a genuinely
    new occurrence can re-fire later.
    """
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    audience = db.Column(db.String(20))  # admin / driver / all
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=True, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    category = db.Column(db.String(40))  # maintenance / weather / fuel / traffic / route / sos / ...
    notif_type = db.Column(db.String(20), default="SYSTEM", index=True)  # TRIP/WEATHER/VEHICLE/CARBON/SYSTEM
    title = db.Column(db.String(120))
    message = db.Column(db.String(255))
    severity = db.Column(db.String(20), default="info")
    priority = db.Column(db.String(20), default="INFO", index=True)  # INFO/ACTION/WARNING/CRITICAL
    action_type = db.Column(db.String(40))  # e.g. "open_trip", "review_vehicle" - optional deep-link hint
    dedup_key = db.Column(db.String(120), index=True)
    active = db.Column(db.Boolean, default=True)  # for dedup_key'd events: still-open condition?
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    __table_args__ = (
        db.CheckConstraint(
            "notif_type IN ('TRIP','WEATHER','VEHICLE','CARBON','SYSTEM')", name="ck_notif_type_valid"
        ),
        db.CheckConstraint(
            "priority IN ('INFO','ACTION','WARNING','CRITICAL')", name="ck_notif_priority_valid"
        ),
    )

    def to_dict(self):
        return {
            "id": self.id, "audience": self.audience, "driver_id": self.driver_id,
            "trip_id": self.trip_id, "vehicle_id": self.vehicle_id,
            "category": self.category, "notif_type": self.notif_type, "title": self.title,
            "message": self.message, "severity": self.severity, "priority": self.priority,
            "action_type": self.action_type, "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }


class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True)
    value = db.Column(db.String(255))


class SavedTip(db.Model):
    """Reserved for future use (e.g. per-driver AI assistant preferences)."""
    __tablename__ = "saved_tips"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"))
    text = db.Column(db.String(255))


class AuditLog(db.Model):
    """Section 38 (Audit Logs). One row per security/business-significant
    action - who did it, what it was, what it touched, and when. Deliberately
    separate from Notification (which is a user-facing feed of things
    someone should look at) - this is the append-only compliance trail.
    Never write passwords/JWTs/API keys/secrets into `details` (see
    audit.py:log_audit, which the caller is expected to use rather than
    constructing rows directly)."""
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_type = db.Column(db.String(20), index=True)  # "admin" / "driver" / "system"
    actor_id = db.Column(db.Integer, index=True)
    actor_name = db.Column(db.String(120))
    action = db.Column(db.String(80), nullable=False, index=True)  # e.g. "driver.approve", "trip.end"
    resource_type = db.Column(db.String(40))  # e.g. "Driver", "Vehicle", "Trip"
    resource_id = db.Column(db.Integer, index=True)
    details = db.Column(db.Text)  # short JSON-serialized context, never secrets
    request_id = db.Column(db.String(40))
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id, "actor_type": self.actor_type, "actor_id": self.actor_id,
            "actor_name": self.actor_name, "action": self.action,
            "resource_type": self.resource_type, "resource_id": self.resource_id,
            "details": json.loads(self.details) if self.details else None,
            "request_id": self.request_id, "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IdempotencyRecord(db.Model):
    """Section 23 (Duplicate Request Protection). If a client sends an
    `Idempotency-Key` header on Create/Start/End Trip, the first request for
    that key+endpoint+actor is executed and its response cached here; any
    retry with the same key (double-click, multi-tab, a network layer
    retrying a timed-out request, etc.) gets the ORIGINAL response replayed
    instead of the action running twice. See backend/idempotency.py.
    Opt-in via the header - requests without one are unaffected."""
    __tablename__ = "idempotency_records"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), nullable=False, index=True)
    scope = db.Column(db.String(80), nullable=False)  # e.g. "trip.create"
    actor_id = db.Column(db.Integer, nullable=False)
    status_code = db.Column(db.Integer)
    response_body = db.Column(db.Text)  # JSON-serialized response, replayed verbatim on retry
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("key", "scope", "actor_id", name="uq_idempotency_key_scope_actor"),
    )


class CarbonMethodology(db.Model):
    """Section 21 (Carbon Methodology Versioning). A named, dated snapshot of
    the emission-factor / fuel-price table used to compute a trip's actual
    CO2/cost. Exactly one row is is_active=True at a time - that's the one
    new trips use. Changing emission factors means creating a NEW row (and
    activating it) rather than editing an existing one, so a trip completed
    under v1.0 stays computed under v1.0's numbers forever, even after v1.1
    becomes active. Trip.methodology_id points at the exact row used."""
    __tablename__ = "carbon_methodologies"
    id = db.Column(db.Integer, primary_key=True)
    version_label = db.Column(db.String(20), unique=True, nullable=False)  # e.g. "v1.0"
    effective_date = db.Column(db.Date, nullable=False)
    # JSON snapshots so this row is self-contained and immutable once other
    # trips reference it — never re-read from the live ml/data_formulas.py
    # constants, which can and will change over time.
    emission_factors = db.Column(db.Text, nullable=False)  # {"Diesel": 2.68, ...} kg CO2 / litre-equivalent
    price_per_unit = db.Column(db.Text)  # {"Diesel": 95, ...} - reference only, actual price is driver-entered
    notes = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def emission_factor_for(self, fuel_type, default_fuel_type="Diesel"):
        factors = json.loads(self.emission_factors)
        return factors.get(fuel_type, factors.get(default_fuel_type, 2.68))

    def to_dict(self):
        return {
            "id": self.id, "version_label": self.version_label,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "emission_factors": json.loads(self.emission_factors) if self.emission_factors else {},
            "price_per_unit": json.loads(self.price_per_unit) if self.price_per_unit else {},
            "notes": self.notes, "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ModelRun(db.Model):
    """Continuous Learning Pipeline log — one row per training run (manual or scheduled)."""
    __tablename__ = "model_runs"
    id = db.Column(db.Integer, primary_key=True)
    triggered_by = db.Column(db.String(20), default="manual")  # manual / scheduled
    status = db.Column(db.String(20), default="running")  # running / success / failed
    metrics_json = db.Column(db.Text)
    training_rows = db.Column(db.Integer)
    started_at = db.Column(db.DateTime, default=utcnow)
    finished_at = db.Column(db.DateTime)

    def to_dict(self):
        import json
        return {
            "id": self.id, "triggered_by": self.triggered_by, "status": self.status,
            "metrics": json.loads(self.metrics_json) if self.metrics_json else None,
            "training_rows": self.training_rows,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class ReassignmentRequest(db.Model):
    """Section 19-21 (Emergency / Personal Problem — Trip Reassignment).
    A driver's request to hand an Ongoing trip to a different driver without
    completing it. Approving a request changes Trip.driver_id and leaves the
    trip's id/status untouched — a completely separate action from End Trip.
    """
    __tablename__ = "reassignment_requests"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    requesting_driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    reason = db.Column(db.String(40), nullable=False)
    description = db.Column(db.Text)
    request_lat = db.Column(db.Float)
    request_lng = db.Column(db.Float)

    status = db.Column(db.String(20), default="Pending", index=True)  # Pending / Approved / Rejected
    replacement_driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True)
    resolved_by_admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=True)
    resolution_note = db.Column(db.String(255))

    requested_at = db.Column(db.DateTime, default=utcnow, index=True)
    resolved_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('Pending','Approved','Rejected')", name="ck_reassignment_status_valid"
        ),
    )

    def to_dict(self):
        trip = db.session.get(Trip, self.trip_id)
        requesting_driver = db.session.get(Driver, self.requesting_driver_id)
        replacement_driver = db.session.get(Driver, self.replacement_driver_id) if self.replacement_driver_id else None
        vehicle = db.session.get(Vehicle, trip.vehicle_id) if trip else None
        last_ping = None
        if trip:
            last_ping = (TripLocation.query.filter_by(trip_id=trip.id)
                         .order_by(TripLocation.recorded_at.desc()).first())
        return {
            "id": self.id, "trip_id": self.trip_id,
            "trip_code": trip.trip_code if trip else None,
            "destination": trip.destination if trip else None,
            "vehicle_no": vehicle.vehicle_no if vehicle else None,
            "requesting_driver_id": self.requesting_driver_id,
            "requesting_driver_name": requesting_driver.name if requesting_driver else None,
            "reason": self.reason, "description": self.description,
            "request_lat": self.request_lat, "request_lng": self.request_lng,
            "current_lat": last_ping.lat if last_ping else None,
            "current_lng": last_ping.lng if last_ping else None,
            "status": self.status,
            "replacement_driver_id": self.replacement_driver_id,
            "replacement_driver_name": replacement_driver.name if replacement_driver else None,
            "resolution_note": self.resolution_note,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class Conversation(db.Model):
    """Section 22-26 (Driver <-> Admin Chat). One thread per driver, or per
    (driver, trip) when opened from a specific trip's active-trip screen so
    the conversation stays contextually linked to that trip (section 23)."""
    __tablename__ = "conversations"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    status = db.Column(db.String(20), default="Open")  # Open / Closed
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self, viewer_role=None):
        driver = db.session.get(Driver, self.driver_id)
        trip = db.session.get(Trip, self.trip_id) if self.trip_id else None
        unread_field = Message.sender_role == ("admin" if viewer_role == "driver" else "driver")
        unread_count = Message.query.filter_by(conversation_id=self.id, is_read=False).filter(unread_field).count() \
            if viewer_role else None
        last_msg = Message.query.filter_by(conversation_id=self.id).order_by(Message.created_at.desc()).first()
        return {
            "id": self.id, "trip_id": self.trip_id, "trip_code": trip.trip_code if trip else None,
            "driver_id": self.driver_id, "driver_name": driver.name if driver else None,
            "status": self.status,
            "last_message": last_msg.message if last_msg else None,
            "last_message_at": last_msg.created_at.isoformat() if last_msg else None,
            "unread_count": unread_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, nullable=False)
    sender_role = db.Column(db.String(10), nullable=False)  # "driver" / "admin"
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    __table_args__ = (
        db.CheckConstraint("sender_role IN ('driver','admin')", name="ck_message_sender_role_valid"),
    )

    def to_dict(self):
        return {
            "id": self.id, "conversation_id": self.conversation_id,
            "sender_id": self.sender_id, "sender_role": self.sender_role,
            "message": self.message, "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

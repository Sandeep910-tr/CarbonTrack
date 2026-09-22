from flask import Blueprint, request, jsonify, send_file, send_from_directory
from sqlalchemy import func
from datetime import datetime, timedelta
import os
import mimetypes
import io
import json
import statistics
from models.db import db, Admin, Driver, Vehicle, Trip, Notification, Settings, ModelRun, ModelVersion, TripLocation, Depot, RouteDeviation, ServiceRecord, AuditLog, CarbonMethodology, ReassignmentRequest, Conversation, Message, TripFeedback, utcnow
from routes.auth_utils import token_required, super_admin_required, hash_password
from errors import ValidationError, NotFoundError, ConflictError, ForbiddenError
from validators import (
    require_fields, validate_vehicle_no, validate_positive_number,
    validate_username, validate_password, validate_choice, validate_lat_lng, VALID_ROLES,
    VALID_FUEL_TYPES, VALID_VEHICLE_TYPES, validate_text_length,
)
from audit import log_admin_action
from notifications import notify
from idempotency import idempotent

admin_bp = Blueprint("admin", __name__)

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _pagination_params():
    """Section 36 (Pagination). Returns (page, per_page) if the caller opted
    in via ?page=, else (None, None) so existing callers that never send
    ?page get the old unpaginated array response unchanged."""
    page_raw = request.args.get("page")
    if page_raw is None:
        return None, None
    try:
        page = max(1, int(page_raw))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page", DEFAULT_PAGE_SIZE))
    except ValueError:
        per_page = DEFAULT_PAGE_SIZE
    per_page = max(1, min(per_page, MAX_PAGE_SIZE))
    return page, per_page


def _paginated_response(pagination, key):
    return {
        "items": [item.to_dict() for item in pagination.items],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "total_pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


def _parse_date(value):
    """Accepts an ISO date string ('YYYY-MM-DD') or None; returns a date object or None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


DEFAULT_SETTINGS = {
    "carbon_budget_target_kg": "50000",
    "fuel_budget_target": "500000",
    "notify_maintenance": "true",
    "notify_weather": "true",
    "notify_traffic": "true",
    "company_name": "CarbonTrack Logistics",
    "certificate_eco_threshold": "80",
    # EV transition planning assumptions — editable in Settings, used by the
    # ICE-vs-EV comparison. Defaults are reasonable ballpark figures for an
    # Indian logistics fleet (₹, kWh, kg CO2/kWh for grid electricity).
    "ev_purchase_premium_pct": "35",
    "ev_vehicle_price_inr": "1800000",
    "ice_vehicle_price_inr": "1300000",
    "fuel_price_per_l": "95",
    "electricity_price_per_kwh": "8",
    "ev_efficiency_kwh_per_km": "0.18",
    "ev_grid_emission_factor_kg_per_kwh": "0.71",
    "ev_maintenance_cost_per_km": "1.2",
    "ice_maintenance_cost_per_km": "2.5",
}


@admin_bp.route("/drivers/<int:driver_id>/documents", methods=["GET"])
@token_required(["admin"])
def get_driver_documents(driver_id):
    d = db.get_or_404(Driver, driver_id)
    docs = []
    if d.license_doc_path:
        docs.append({"type": "license", "label": "Driving License", "filename": d.license_doc_path})
    if d.profile_photo_path:
        docs.append({"type": "photo", "label": "Profile Photo", "filename": d.profile_photo_path})
    if d.address_proof_path:
        docs.append({"type": "address", "label": "Address Proof", "filename": d.address_proof_path})
    return jsonify(docs)


def _detect_mime_type(file_path, filename=""):
    """Safely detect the MIME type of a document from file signatures (magic bytes),
    falling back to file extension and system mimetypes.
    Supports application/pdf, image/jpeg, image/png, image/webp, image/gif, image/svg+xml."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
        if header.startswith(b"%PDF-"):
            return "application/pdf"
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
            return "image/webp"
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return "image/gif"
        if header.startswith(b"BM"):
            return "image/bmp"
        if header.startswith(b"<?xml") or header.startswith(b"<svg"):
            return "image/svg+xml"
    except Exception:
        pass

    ext_to_mime = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
    }
    ext = os.path.splitext(filename or file_path)[1].lower()
    if ext in ext_to_mime:
        return ext_to_mime[ext]

    guessed, _ = mimetypes.guess_type(filename or file_path)
    return guessed or "application/octet-stream"


@admin_bp.route("/documents/<string:filename>", methods=["GET"])
@token_required(["admin"])
def serve_driver_document(filename):
    from flask import current_app
    from werkzeug.security import safe_join

    upload_folder = current_app.config.get("UPLOAD_FOLDER")
    safe_path = safe_join(upload_folder, filename) if upload_folder else None
    if not safe_path or not os.path.isfile(safe_path):
        raise NotFoundError("Document not found")

    mimetype = _detect_mime_type(safe_path, filename)
    return send_file(
        safe_path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=os.path.basename(safe_path),
    )
@admin_bp.route("/drivers", methods=["GET"])
@token_required(["admin"])
def list_drivers():
    status = request.args.get("status")
    q = Driver.query
    if status:
        q = q.filter_by(status=status)
    q = q.order_by(Driver.created_at.desc())
    page, per_page = _pagination_params()
    if page is None:
        # Back-compat: no pagination params supplied -> old unpaginated
        # behavior (a plain array), so existing frontend calls don't break.
        return jsonify([d.to_dict() for d in q.all()])
    result = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(_paginated_response(result, "d"))


@admin_bp.route("/drivers/<int:driver_id>/approve", methods=["POST"])
@token_required(["admin"])
def approve_driver(driver_id):
    d = db.get_or_404(Driver, driver_id)
    d.status = "Approved"
    notify(
        audience="driver", notif_type="SYSTEM", priority="INFO",
        title="Account approved", category="approval",
        message="Your registration has been approved. You can now log in.",
        driver_id=d.id,
    )
    log_admin_action("driver.approve", "Driver", d.id, {"driver_code": d.driver_code})
    db.session.commit()
    return jsonify({"message": "Driver approved", "driver": d.to_dict()})


@admin_bp.route("/drivers/<int:driver_id>/reject", methods=["POST"])
@token_required(["admin"])
def reject_driver(driver_id):
    reason = (request.get_json(silent=True) or {}).get("reason", "Documents incomplete")
    d = db.get_or_404(Driver, driver_id)
    d.status = "Rejected"
    d.rejection_reason = reason
    log_admin_action("driver.reject", "Driver", d.id, {"driver_code": d.driver_code, "reason": reason})
    db.session.commit()
    return jsonify({"message": "Driver rejected", "driver": d.to_dict()})


@admin_bp.route("/drivers/<int:driver_id>/block", methods=["POST"])
@token_required(["admin"])
def block_driver(driver_id):
    d = db.get_or_404(Driver, driver_id)
    d.status = "Blocked"
    log_admin_action("driver.block", "Driver", d.id, {"driver_code": d.driver_code})
    db.session.commit()
    return jsonify({"message": "Driver blocked", "driver": d.to_dict()})


@admin_bp.route("/drivers/<int:driver_id>/assign-vehicle", methods=["POST"])
@token_required(["admin"])
def assign_vehicle(driver_id):
    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id")
    d = db.get_or_404(Driver, driver_id)
    if vehicle_id:
        db.get_or_404(Vehicle, vehicle_id)
    d.assigned_vehicle_id = vehicle_id
    log_admin_action("driver.assign_vehicle", "Driver", d.id, {"vehicle_id": vehicle_id})
    db.session.commit()
    return jsonify({"message": "Vehicle assigned", "driver": d.to_dict()})


@admin_bp.route("/drivers/<int:driver_id>/assign-depot", methods=["POST"])
@token_required(["admin"])
def assign_depot(driver_id):
    data = request.get_json(force=True)
    depot_id = data.get("depot_id")
    d = db.get_or_404(Driver, driver_id)
    if depot_id:
        db.get_or_404(Depot, depot_id)
    d.depot_id = depot_id
    db.session.commit()
    return jsonify({"message": "Depot assigned", "driver": d.to_dict()})


# ---------------------------------------------------------- DEPOTS
@admin_bp.route("/depots", methods=["GET"])
@token_required(["admin", "driver"])
def list_depots():
    depots = Depot.query.order_by(Depot.id).all()
    return jsonify([d.to_dict() for d in depots])


@admin_bp.route("/depots", methods=["POST"])
@token_required(["admin"])
@idempotent("depot.create")
def add_depot():
    data = request.get_json(force=True) or {}
    require_fields(data, ["name"])
    if data.get("lat") is not None or data.get("lng") is not None:
        validate_lat_lng(data.get("lat"), data.get("lng"))
    last = Depot.query.order_by(Depot.id.desc()).first()
    code = f"DPT{((last.id if last else 0) + 1):03d}"
    d = Depot(
        depot_code=code, name=data["name"], city=data.get("city"), address=data.get("address"),
        lat=data.get("lat"), lng=data.get("lng"),
    )
    db.session.add(d)
    db.session.commit()
    log_admin_action("depot.create", "Depot", d.id, {"name": d.name})
    db.session.commit()
    return jsonify(d.to_dict()), 201


@admin_bp.route("/depots/<int:depot_id>", methods=["PUT"])
@token_required(["admin"])
def update_depot(depot_id):
    d = db.get_or_404(Depot, depot_id)
    data = request.get_json(force=True) or {}
    if "lat" in data or "lng" in data:
        validate_lat_lng(data.get("lat", d.lat), data.get("lng", d.lng))
    for field in ["name", "city", "address", "lat", "lng"]:
        if field in data:
            setattr(d, field, data[field])
    db.session.commit()
    log_admin_action("depot.update", "Depot", d.id, data)
    db.session.commit()
    return jsonify(d.to_dict())


@admin_bp.route("/depots/<int:depot_id>", methods=["DELETE"])
@token_required(["admin"])
def delete_depot(depot_id):
    d = db.get_or_404(Depot, depot_id)
    # Unassign rather than block deletion — a depot closing shouldn't be
    # blocked by every vehicle/driver that was ever stationed there.
    Vehicle.query.filter_by(depot_id=depot_id).update({"depot_id": None})
    Driver.query.filter_by(depot_id=depot_id).update({"depot_id": None})
    db.session.delete(d)
    db.session.commit()
    log_admin_action("depot.delete", "Depot", d.id, {"name": d.name})
    db.session.commit()
    return jsonify({"message": "Depot deleted"})


# ---------------------------------------------------------- VEHICLES
@admin_bp.route("/vehicles", methods=["GET"])
@token_required(["admin", "driver"])
def list_vehicles():
    q = Vehicle.query.order_by(Vehicle.id)
    page, per_page = _pagination_params()
    if page is None:
        return jsonify([v.to_dict() for v in q.all()])
    result = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(_paginated_response(result, "v"))


@admin_bp.route("/vehicles", methods=["POST"])
@token_required(["admin"])
def add_vehicle():
    data = request.get_json(force=True) or {}
    require_fields(data, ["vehicle_no"])
    vehicle_no = validate_vehicle_no(data["vehicle_no"])
    if Vehicle.query.filter_by(vehicle_no=vehicle_no).first():
        raise ConflictError(f"A vehicle with registration number {vehicle_no} already exists")

    mileage = validate_positive_number(data.get("mileage"), "mileage", allow_zero=False, required=False)
    capacity_kg = validate_positive_number(data.get("capacity_kg"), "capacity_kg", allow_zero=False, required=False)
    health_score = validate_positive_number(data.get("health_score", 90), "health_score", allow_zero=True, required=False)
    if health_score is not None and health_score > 100:
        raise ValidationError("health_score must be between 0 and 100")
    if data.get("depot_id") is not None and not db.session.get(Depot, data.get("depot_id")):
        raise ValidationError("depot_id does not refer to an existing depot")
    vehicle_type = validate_choice(data.get("vehicle_type"), VALID_VEHICLE_TYPES, "vehicle_type") if data.get("vehicle_type") else None
    fuel_type = validate_choice(data.get("fuel_type"), VALID_FUEL_TYPES, "fuel_type") if data.get("fuel_type") else None

    last = Vehicle.query.order_by(Vehicle.id.desc()).first()
    code = f"V{((last.id if last else 0) + 1):04d}"
    v = Vehicle(
        vehicle_code=code, vehicle_no=vehicle_no, vehicle_type=vehicle_type,
        fuel_type=fuel_type, mileage=mileage,
        capacity_kg=capacity_kg, health_score=health_score if health_score is not None else 90,
        insurance_expiry=_parse_date(data.get("insurance_expiry")),
        permit_expiry=_parse_date(data.get("permit_expiry")),
        pollution_cert_expiry=_parse_date(data.get("pollution_cert_expiry")),
        depot_id=data.get("depot_id"),
    )
    db.session.add(v)
    db.session.flush()
    log_admin_action("vehicle.create", "Vehicle", v.id, {"vehicle_no": v.vehicle_no})
    db.session.commit()
    return jsonify(v.to_dict()), 201


@admin_bp.route("/vehicles/<int:vehicle_id>", methods=["PUT"])
@token_required(["admin"])
def update_vehicle(vehicle_id):
    v = db.get_or_404(Vehicle, vehicle_id)
    data = request.get_json(force=True) or {}

    if "vehicle_no" in data:
        new_no = validate_vehicle_no(data["vehicle_no"])
        clash = Vehicle.query.filter(Vehicle.vehicle_no == new_no, Vehicle.id != v.id).first()
        if clash:
            raise ConflictError(f"A vehicle with registration number {new_no} already exists")
        data["vehicle_no"] = new_no
    if "mileage" in data:
        data["mileage"] = validate_positive_number(data["mileage"], "mileage", allow_zero=False, required=False)
    if "capacity_kg" in data:
        data["capacity_kg"] = validate_positive_number(data["capacity_kg"], "capacity_kg", allow_zero=False, required=False)
    if "vehicle_type" in data and data["vehicle_type"]:
        data["vehicle_type"] = validate_choice(data["vehicle_type"], VALID_VEHICLE_TYPES, "vehicle_type")
    if "fuel_type" in data and data["fuel_type"]:
        data["fuel_type"] = validate_choice(data["fuel_type"], VALID_FUEL_TYPES, "fuel_type")
    if "health_score" in data:
        hs = validate_positive_number(data["health_score"], "health_score", allow_zero=True, required=False)
        if hs is not None and hs > 100:
            raise ValidationError("health_score must be between 0 and 100")
        data["health_score"] = hs
    if "depot_id" in data and data["depot_id"] is not None and not db.session.get(Depot, data["depot_id"]):
        raise ValidationError("depot_id does not refer to an existing depot")

    for field in ["vehicle_no", "vehicle_type", "fuel_type", "mileage", "capacity_kg", "status", "health_score", "depot_id"]:
        if field in data:
            setattr(v, field, data[field])
    for field in ["insurance_expiry", "permit_expiry", "pollution_cert_expiry"]:
        if field in data:
            setattr(v, field, _parse_date(data[field]))
    db.session.commit()
    log_admin_action("vehicle.update", "Vehicle", v.id, data)
    db.session.commit()
    return jsonify(v.to_dict())


@admin_bp.route("/vehicles/<int:vehicle_id>", methods=["DELETE"])
@token_required(["admin"])
def delete_vehicle(vehicle_id):
    v = db.get_or_404(Vehicle, vehicle_id)
    db.session.delete(v)
    db.session.commit()
    log_admin_action("vehicle.delete", "Vehicle", v.id, {"vehicle_no": v.vehicle_no})
    db.session.commit()
    return jsonify({"message": "Vehicle deleted"})


# ---------------------------------------------------------- SERVICE HISTORY (maintenance model input)
@admin_bp.route("/vehicles/<int:vehicle_id>/service-records", methods=["GET"])
@token_required(["admin"])
def list_service_records(vehicle_id):
    db.get_or_404(Vehicle, vehicle_id)
    rows = ServiceRecord.query.filter_by(vehicle_id=vehicle_id).order_by(ServiceRecord.service_date.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@admin_bp.route("/vehicles/<int:vehicle_id>/service-records", methods=["POST"])
@token_required(["admin"])
@idempotent(lambda vehicle_id: f"vehicle.service_record.create:{vehicle_id}")
def add_service_record(vehicle_id):
    """Logs a real service/repair event - this is the "Service History" the
    maintenance model trains on (see ml/vehicle_features.py). Updates the
    vehicle's rollup fields so the very next prediction for this vehicle
    already reflects it."""
    v = db.get_or_404(Vehicle, vehicle_id)
    data = request.get_json(force=True) or {}
    require_fields(data, ["service_date"])
    service_date = _parse_date(data["service_date"])
    if not service_date:
        raise ValidationError("service_date must be a valid date (YYYY-MM-DD)")
    cost = validate_positive_number(data.get("cost", 0), "cost", allow_zero=True, required=False) or 0
    was_breakdown = bool(data.get("was_breakdown", False))

    record = ServiceRecord(
        vehicle_id=v.id, service_date=service_date, service_type=data.get("service_type", "Routine"),
        cost=cost, was_breakdown=was_breakdown, notes=data.get("notes"),
    )
    db.session.add(record)

    v.service_count = (v.service_count or 0) + 1
    v.maintenance_cost_total = (v.maintenance_cost_total or 0) + cost
    if was_breakdown:
        v.breakdown_count = (v.breakdown_count or 0) + 1
    if not v.last_service_date or service_date > v.last_service_date:
        v.last_service_date = service_date

    db.session.commit()
    log_admin_action("vehicle.service_record.create", "ServiceRecord", record.id, {"vehicle_id": v.id})
    db.session.commit()
    return jsonify({"message": "Service record logged", "vehicle": v.to_dict(), "record": record.to_dict()}), 201


# ---------------------------------------------------------- TRIPS (admin view)
@admin_bp.route("/trips", methods=["GET"])
@token_required(["admin"])
def all_trips():
    q = Trip.query.order_by(Trip.created_at.desc())
    page, per_page = _pagination_params()
    if page is None:
        # Back-compat cap: unpaginated callers keep getting a bounded list
        # rather than the entire trips table.
        return jsonify([t.to_dict() for t in q.limit(500).all()])
    result = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(_paginated_response(result, "t"))


@admin_bp.route("/audit-logs", methods=["GET"])
@token_required(["admin"])
def list_audit_logs():
    """Section 38 (Audit Logs). Filterable by ?actor_type=, ?action=,
    ?resource_type=, ?resource_id=; always paginated (never an unbounded dump)."""
    q = AuditLog.query
    if request.args.get("actor_type"):
        q = q.filter_by(actor_type=request.args["actor_type"])
    if request.args.get("action"):
        q = q.filter_by(action=request.args["action"])
    if request.args.get("resource_type"):
        q = q.filter_by(resource_type=request.args["resource_type"])
    if request.args.get("resource_id"):
        q = q.filter_by(resource_id=request.args["resource_id"])
    q = q.order_by(AuditLog.created_at.desc())
    page, per_page = _pagination_params()
    page, per_page = page or 1, per_page or DEFAULT_PAGE_SIZE
    result = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(_paginated_response(result, "a"))


@admin_bp.route("/route-deviations", methods=["GET"])
@token_required(["admin"])
def list_route_deviations():
    """Structured deviation alerts (Trip, Driver, Lat/Lng, Distance, Detected
    Time, Status) for the Admin Dashboard - the driver-facing detection logic
    lives in routes/driver.py:report_location, this just surfaces the records
    it creates. ?status=Active|Resolved filters; defaults to all, newest first."""
    q = RouteDeviation.query
    status = request.args.get("status")
    if status:
        status = validate_choice(status, {"Active", "Resolved"}, "status")
        q = q.filter_by(status=status)
    rows = q.order_by(RouteDeviation.detected_at.desc()).limit(200).all()
    return jsonify([r.to_dict() for r in rows])


@admin_bp.route("/route-deviations/<int:deviation_id>/resolve", methods=["POST"])
@token_required(["admin"])
def resolve_route_deviation(deviation_id):
    dev = db.get_or_404(RouteDeviation, deviation_id)
    dev.status = "Resolved"
    dev.resolved_at = utcnow()
    db.session.commit()
    return jsonify(dev.to_dict())


@admin_bp.route("/trips/<int:trip_id>/locations", methods=["GET"])
@token_required(["admin"])
def trip_locations(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    pings = TripLocation.query.filter_by(trip_id=trip.id).order_by(TripLocation.recorded_at.asc()).all()

    origin = trip.started_at or trip.created_at
    points = [{
        "lat": p.lat, "lng": p.lng, "heading": p.heading, "accuracy_m": p.accuracy_m,
        "speed_kmph": p.speed_kmph,
        "recorded_at": p.recorded_at.isoformat(),
        "elapsed_sec": round((p.recorded_at - origin).total_seconds()) if origin else None,
    } for p in pings]

    return jsonify({
        "trip_id": trip.id, "trip_code": trip.trip_code,
        "source": trip.source, "destination": trip.destination,
        "distance_km": trip.distance_km,
        "origin_lat": trip.origin_lat, "origin_lng": trip.origin_lng,
        "dest_lat": trip.dest_lat, "dest_lng": trip.dest_lng,
        "started_at": trip.started_at.isoformat() if trip.started_at else None,
        "ended_at": trip.ended_at.isoformat() if trip.ended_at else None,
        "has_real_gps": len(points) > 0,
        "points": points,
    })


# ---------------------------------------------------------- ANALYTICS / REPORTS
@admin_bp.route("/analytics/overview", methods=["GET"])
@token_required(["admin"])
def analytics_overview():
    total_drivers = Driver.query.count()
    approved_drivers = Driver.query.filter_by(status="Approved").count()
    pending_drivers = Driver.query.filter_by(status="Pending").count()
    total_vehicles = Vehicle.query.count()
    total_trips = Trip.query.count()
    completed_trips = Trip.query.filter_by(status="Completed").count()

    co2_total = db.session.query(func.coalesce(func.sum(Trip.actual_co2_kg), 0.0)).scalar()
    fuel_total = db.session.query(func.coalesce(func.sum(Trip.actual_fuel_l), 0.0)).scalar()
    cost_total = db.session.query(func.coalesce(func.sum(Trip.actual_cost), 0.0)).scalar()
    avg_eco = db.session.query(func.coalesce(func.avg(Driver.eco_score), 0.0)).scalar()
    avg_fleet_health = db.session.query(func.coalesce(func.avg(Vehicle.health_score), 0.0)).scalar()

    return jsonify({
        "total_drivers": total_drivers, "approved_drivers": approved_drivers,
        "pending_drivers": pending_drivers, "total_vehicles": total_vehicles,
        "total_trips": total_trips, "completed_trips": completed_trips,
        "total_co2_kg": round(co2_total, 2), "total_fuel_l": round(fuel_total, 2),
        "total_cost": round(cost_total, 2), "avg_eco_score": round(avg_eco, 1),
        "avg_fleet_health": round(avg_fleet_health, 1),
        "trees_equivalent": round(co2_total / 21, 1),  # ~21kg CO2 absorbed per tree/year
    })


@admin_bp.route("/analytics/leaderboard", methods=["GET"])
@token_required(["admin", "driver"])
def leaderboard():
    drivers = Driver.query.filter_by(status="Approved").order_by(Driver.eco_score.desc()).limit(20).all()
    return jsonify([{"name": d.name, "driver_code": d.driver_code, "eco_score": d.eco_score} for d in drivers])


@admin_bp.route("/analytics/carbon-trend", methods=["GET"])
@token_required(["admin"])
def carbon_trend():
    rows = db.session.query(
        func.strftime("%Y-%m-%d", Trip.created_at).label("day"),
        func.sum(Trip.actual_co2_kg).label("co2"),
        func.sum(Trip.actual_fuel_l).label("fuel"),
    ).group_by("day").order_by("day").limit(30).all()
    return jsonify([{"day": r.day, "co2": round(r.co2 or 0, 2), "fuel": round(r.fuel or 0, 2)} for r in rows])


# ---------------------------------------------------------- NOTIFICATIONS
@admin_bp.route("/notifications", methods=["GET"])
@token_required(["admin"])
def admin_notifications():
    notes = Notification.query.filter(Notification.audience.in_(["admin", "all"])) \
        .order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notes])


@admin_bp.route("/notifications/unread-count", methods=["GET"])
@token_required(["admin"])
def admin_notifications_unread_count():
    from notifications import unread_count
    return jsonify({"unread": unread_count(audience="admin")})


@admin_bp.route("/notifications/read-all", methods=["POST"])
@token_required(["admin"])
def admin_notifications_mark_all_read():
    from notifications import mark_all_read
    mark_all_read(audience="admin")
    db.session.commit()
    return jsonify({"message": "All notifications marked as read."})


@admin_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@token_required(["admin"])
def admin_notification_mark_read(notification_id):
    from notifications import mark_read
    mark_read([notification_id], audience="admin")
    db.session.commit()
    return jsonify({"message": "Notification marked as read."})


# ---------------------------------------------------------- SETTINGS
@admin_bp.route("/settings", methods=["GET"])
@token_required(["admin"])
def get_settings():
    rows = {s.key: s.value for s in Settings.query.all()}
    merged = {**DEFAULT_SETTINGS, **rows}
    return jsonify(merged)


@admin_bp.route("/settings", methods=["PUT"])
@token_required(["admin"])
def update_settings():
    data = request.get_json(force=True)
    for key, value in data.items():
        row = Settings.query.filter_by(key=key).first()
        if row:
            row.value = str(value)
        else:
            db.session.add(Settings(key=key, value=str(value)))
    db.session.commit()
    return jsonify({"message": "Settings updated"})


# ---------------------------------------------------------- LIVE FLEET MONITORING
@admin_bp.route("/live-fleet", methods=["GET"])
@token_required(["admin"])
def live_fleet():
    depot_id = request.args.get("depot_id", type=int)
    ongoing = Trip.query.filter_by(status="Ongoing").order_by(Trip.started_at.desc()).all()
    result = []
    for t in ongoing:
        driver = db.session.get(Driver, t.driver_id)
        vehicle = db.session.get(Vehicle, t.vehicle_id)
        if depot_id and (not vehicle or vehicle.depot_id != depot_id):
            continue
        elapsed_min = None
        current_lat = current_lng = None
        progress_pct = None
        live = False
        heading = None
        speed_kmph = None
        last_ping_sec_ago = None
        last_ping_at = None

        # Prefer a real GPS ping from the driver's browser if one has arrived
        # recently. "Recently" = within the last 2 minutes, so a driver who
        # closed the tab or lost signal falls back to the simulated position
        # below instead of freezing the marker at a stale spot forever.
        latest_ping = (TripLocation.query.filter_by(trip_id=t.id)
                        .order_by(TripLocation.recorded_at.desc()).first())
        if latest_ping:
            last_ping_sec_ago = round((utcnow() - latest_ping.recorded_at).total_seconds())
            last_ping_at = latest_ping.recorded_at.isoformat()
            if last_ping_sec_ago < 120:
                current_lat, current_lng = latest_ping.lat, latest_ping.lng
                heading = latest_ping.heading
                speed_kmph = latest_ping.speed_kmph
                live = True

        if t.started_at:
            elapsed_min = round((utcnow() - t.started_at).total_seconds() / 60, 1)
            frac = None
            if t.origin_lat is not None and t.dest_lat is not None and t.estimated_duration_min:
                frac = min(elapsed_min / t.estimated_duration_min, 1.0)
                progress_pct = round(frac * 100, 1)
            if not live and frac is not None:
                # Simulated position: linear interpolation between geocoded origin/destination,
                # scaled by elapsed time vs. the estimated trip duration. This is a fallback for
                # when no real GPS ping exists yet (or has gone stale) so Live Fleet Monitoring
                # still has something to plot and animate.
                current_lat = t.origin_lat + (t.dest_lat - t.origin_lat) * frac
                current_lng = t.origin_lng + (t.dest_lng - t.origin_lng) * frac
        result.append({
            "trip_id": t.id, "trip_code": t.trip_code,
            "driver_name": driver.name if driver else None,
            "vehicle_no": vehicle.vehicle_no if vehicle else None,
            "depot_id": vehicle.depot_id if vehicle else None,
            "source": t.source, "destination": t.destination,
            "distance_km": t.distance_km, "route": t.route_chosen,
            "predicted_co2_kg": t.predicted_co2_kg, "maintenance_risk": t.maintenance_risk,
            "elapsed_min": elapsed_min,
            "origin_lat": t.origin_lat, "origin_lng": t.origin_lng,
            "dest_lat": t.dest_lat, "dest_lng": t.dest_lng,
            "current_lat": current_lat, "current_lng": current_lng,
            "progress_pct": progress_pct,
            "live": live, "heading": heading, "speed_kmph": speed_kmph,
            "last_ping_sec_ago": last_ping_sec_ago, "last_ping_at": last_ping_at,
        })
    return jsonify(result)


# ---------------------------------------------------------- AI COMMAND CENTER (rule-based insights)
@admin_bp.route("/insights", methods=["GET"])
@token_required(["admin"])
def ai_insights():
    """Rule-based fleet insights, computed live from current DB state.
    Not an LLM — deterministic thresholds over real fleet data, in the spirit
    of the flowchart's 'AI Command Center > Insights & Recommendations'."""
    insights = []

    risky_vehicles = Vehicle.query.filter(Vehicle.health_score < 55).order_by(Vehicle.health_score).limit(5).all()
    for v in risky_vehicles:
        insights.append({
            "type": "maintenance", "severity": "high" if v.health_score < 40 else "medium",
            "message": f"{v.vehicle_no} has a fleet health score of {v.health_score}% — schedule inspection soon.",
        })

    top_driver = Driver.query.filter_by(status="Approved").order_by(Driver.eco_score.desc()).first()
    if top_driver:
        insights.append({
            "type": "recognition", "severity": "info",
            "message": f"{top_driver.name} leads the eco-score leaderboard at {top_driver.eco_score} pts — consider recognizing this driver.",
        })

    low_driver = Driver.query.filter_by(status="Approved").order_by(Driver.eco_score.asc()).first()
    if low_driver and low_driver.eco_score < 55:
        insights.append({
            "type": "coaching", "severity": "medium",
            "message": f"{low_driver.name} has an eco score of {low_driver.eco_score} pts — may benefit from eco-driving coaching.",
        })

    high_co2_trips = Trip.query.filter(Trip.actual_co2_kg != None).order_by(Trip.actual_co2_kg.desc()).limit(1).all()
    if high_co2_trips:
        t = high_co2_trips[0]
        insights.append({
            "type": "carbon", "severity": "medium",
            "message": f"Trip {t.trip_code} ({t.source} → {t.destination}) emitted {t.actual_co2_kg} kg CO2, the highest on record — review route choice.",
        })

    pending = Driver.query.filter_by(status="Pending").count()
    if pending > 0:
        insights.append({
            "type": "approval", "severity": "info",
            "message": f"{pending} driver registration(s) are awaiting approval.",
        })

    if not insights:
        insights.append({"type": "info", "severity": "info", "message": "Fleet is operating within normal parameters — no action items right now."})

    return jsonify(insights)


@admin_bp.route("/ai-chat", methods=["POST"])
@token_required(["admin", "driver"])
def ai_chat():
    """Rule-based AI Command Center assistant. Answers common fleet questions
    directly from the database. This is intent-matching, not a generative LLM —
    documented as such since the flowchart's 'AI Chat Assistant' box doesn't
    specify an underlying model and no LLM API key was provided."""
    data = request.get_json(force=True)
    msg = (data.get("message") or "").lower()
    is_driver = request.user["role"] == "driver"

    def money(v): return f"Rs.{v:,.0f}"

    # Section 6/7/33: the Fleet AI Assistant is intentionally shared with
    # drivers (spec requires it stay usable by drivers on mobile), but that
    # doesn't mean every intent it answers should be. Company financials
    # (total fuel spend/budget) and admin operational queues (pending
    # approval counts) are admin-only topics regardless of which role asked
    # - a driver asking "what's our fuel budget" gets redirected, not a real
    # answer, the same way any other admin-only endpoint would 403 them.
    if is_driver and any(k in msg for k in ["cost", "spend", "budget", "pending", "approval", "approve"]):
        reply = "That's fleet operational/financial data available to admins only. Ask me about CO2, fuel use, top drivers, or vehicle maintenance instead."
        return jsonify({"reply": reply})

    if any(k in msg for k in ["total co2", "carbon", "emission"]):
        total = db.session.query(func.coalesce(func.sum(Trip.actual_co2_kg), 0)).scalar()
        reply = f"The fleet has emitted a total of {total:.1f} kg of CO2 across all logged trips so far."
    elif any(k in msg for k in ["fuel used", "total fuel"]):
        total = db.session.query(func.coalesce(func.sum(Trip.actual_fuel_l), 0)).scalar()
        reply = f"Total fuel consumed across all trips is {total:.1f} litres."
    elif any(k in msg for k in ["best driver", "top driver", "eco score"]):
        d = Driver.query.filter_by(status="Approved").order_by(Driver.eco_score.desc()).first()
        reply = f"{d.name} ({d.driver_code}) currently has the top eco score at {d.eco_score} pts." if d else "No approved drivers yet."
    elif any(k in msg for k in ["maintenance", "vehicle health", "repair"]):
        v = Vehicle.query.order_by(Vehicle.health_score.asc()).first()
        reply = f"{v.vehicle_no} needs the most attention — health score is {v.health_score}%." if v else "No vehicles registered yet."
    elif any(k in msg for k in ["pending", "approval", "approve"]):
        n = Driver.query.filter_by(status="Pending").count()
        reply = f"There are {n} driver registration(s) waiting for approval." if n else "No pending driver approvals right now."
    elif any(k in msg for k in ["cost", "spend", "budget"]):
        total = db.session.query(func.coalesce(func.sum(Trip.actual_cost), 0)).scalar()
        reply = f"Total fuel cost logged so far is {money(total)}."
    elif any(k in msg for k in ["trip", "distance"]):
        n = Trip.query.filter_by(status="Completed").count()
        reply = f"{n} trips have been completed and logged in the system."
    elif any(k in msg for k in ["hello", "hi", "hey"]):
        reply = "Hi! Ask me about fleet CO2, fuel usage, top drivers, vehicle maintenance, or pending approvals."
    else:
        reply = "I can answer questions about fleet CO2, fuel use, cost, top/bottom drivers, vehicle maintenance risk, and pending approvals — try one of those."

    return jsonify({"reply": reply})


# ---------------------------------------------------------- SUSTAINABILITY DASHBOARD
@admin_bp.route("/sustainability", methods=["GET"])
@token_required(["admin", "driver"])
def sustainability():
    settings = {s.key: s.value for s in Settings.query.all()}
    target = float(settings.get("carbon_budget_target_kg", DEFAULT_SETTINGS["carbon_budget_target_kg"]))

    completed = Trip.query.filter_by(status="Completed").all()
    total_trips = len(completed)

    total_co2 = sum(t.actual_co2_kg or 0 for t in completed)
    total_fuel = sum(t.actual_fuel_l or 0 for t in completed)
    total_distance = sum(t.distance_km or 0 for t in completed)

    green_trips = Trip.query.filter(Trip.route_chosen == "Eco", Trip.status == "Completed").count()

    # Operational Metrics
    co2_per_km = (total_co2 / total_distance) if total_distance else 0
    fuel_per_100km = (total_fuel / total_distance * 100) if total_distance else 0
    avg_co2 = (total_co2 / total_trips) if total_trips else 0

    # Prediction Coverage
    predicted_count = sum(1 for t in completed if t.predicted_co2_kg is not None)
    prediction_coverage = (predicted_count / total_trips * 100) if total_trips else 0

    # Reduction Opportunity (Estimate)
    # Compare actual CO2 of Non-Eco trips vs what would have been if they were Eco
    # Simplified: assume Eco routes save ~10-15% CO2 on average
    non_eco_co2 = sum(t.actual_co2_kg or 0 for t in completed if t.route_chosen != "Eco")
    est_reduction = non_eco_co2 * 0.12  # 12% estimated saving

    return jsonify({
        "kpis": {
            "carbon_budget_target_kg": target,
            "carbon_budget_used_kg": round(total_co2, 1),
            "carbon_budget_pct": round(min(total_co2 / target * 100, 999), 1) if target else 0,
            "green_trips": green_trips,
            "total_trips": total_trips,
            "green_trip_pct": round((green_trips / total_trips * 100), 1) if total_trips else 0,
            "trees_equivalent": round(total_co2 / 21, 1),
        },
        "operational": {
            "total_distance_km": round(total_distance, 1),
            "total_fuel_l": round(total_fuel, 1),
            "co2_per_km": round(co2_per_km, 3),
            "fuel_per_100km": round(fuel_per_100km, 2),
            "avg_co2_kg": round(avg_co2, 2),
            "prediction_coverage_pct": round(prediction_coverage, 1),
        },
        "analytics": {
            "est_reduction_opportunity_kg": round(est_reduction, 1),
        }
    })


# ---------------------------------------------------------- EV TRANSITION PLANNING
@admin_bp.route("/ev-planning", methods=["GET"])
@token_required(["admin"])
def ev_planning():
    """Projects ICE-vs-EV total cost of ownership and CO2 over N years for the
    fleet's current non-electric vehicles, using real observed fuel/distance
    from completed trips (annualized from the actual date span of that data)
    plus admin-editable cost/efficiency assumptions from Settings."""
    years = min(max(int(request.args.get("years", 5)), 1), 15)
    settings = {s.key: s.value for s in Settings.query.all()}

    def s(key):
        return float(settings.get(key, DEFAULT_SETTINGS[key]))

    ice_vehicles = Vehicle.query.filter(Vehicle.fuel_type != "Electric").all()
    ice_vehicle_ids = [v.id for v in ice_vehicles]
    ev_vehicle_count = Vehicle.query.filter_by(fuel_type="Electric").count()

    trips = Trip.query.filter(Trip.vehicle_id.in_(ice_vehicle_ids), Trip.status == "Completed").all() if ice_vehicle_ids else []
    total_km = sum(t.distance_km or 0 for t in trips)
    total_fuel_l = sum(t.actual_fuel_l or 0 for t in trips)
    total_co2_kg = sum(t.actual_co2_kg or 0 for t in trips)
    dates = [t.created_at for t in trips if t.created_at]
    span_days = max((max(dates) - min(dates)).days, 1) if dates else 365
    annualize = 365 / span_days

    annual_km = total_km * annualize
    annual_fuel_l = total_fuel_l * annualize
    annual_co2_ice_kg = total_co2_kg * annualize

    fuel_price = s("fuel_price_per_l")
    elec_price = s("electricity_price_per_kwh")
    ev_kwh_per_km = s("ev_efficiency_kwh_per_km")
    ev_grid_factor = s("ev_grid_emission_factor_kg_per_kwh")
    ev_maint_per_km = s("ev_maintenance_cost_per_km")
    ice_maint_per_km = s("ice_maintenance_cost_per_km")
    ice_price = s("ice_vehicle_price_inr")
    ev_price = s("ev_vehicle_price_inr") if s("ev_vehicle_price_inr") > 0 else ice_price * (1 + s("ev_purchase_premium_pct") / 100)

    fleet_size = len(ice_vehicles)
    annual_energy_cost_ice = annual_fuel_l * fuel_price
    annual_energy_cost_ev = annual_km * ev_kwh_per_km * elec_price
    annual_maint_cost_ice = annual_km * ice_maint_per_km
    annual_maint_cost_ev = annual_km * ev_maint_per_km
    annual_co2_ev_kg = annual_km * ev_kwh_per_km * ev_grid_factor

    upfront_premium_per_vehicle = max(ev_price - ice_price, 0)
    fleet_upfront_premium = upfront_premium_per_vehicle * fleet_size

    timeline = []
    payback_year = None
    for year in range(1, years + 1):
        cum_ice_cost = (annual_energy_cost_ice + annual_maint_cost_ice) * year
        cum_ev_cost = fleet_upfront_premium + (annual_energy_cost_ev + annual_maint_cost_ev) * year
        if payback_year is None and cum_ev_cost <= cum_ice_cost:
            payback_year = year
        timeline.append({
            "year": year,
            "cumulative_cost_ice": round(cum_ice_cost),
            "cumulative_cost_ev": round(cum_ev_cost),
            "cumulative_co2_ice_kg": round(annual_co2_ice_kg * year),
            "cumulative_co2_ev_kg": round(annual_co2_ev_kg * year),
        })

    return jsonify({
        "fleet_size_ice": fleet_size,
        "fleet_size_ev_current": ev_vehicle_count,
        "data_basis": {"trips_analyzed": len(trips), "annualized_from_days": span_days},
        "annual": {
            "distance_km": round(annual_km),
            "fuel_l_ice": round(annual_fuel_l),
            "energy_cost_ice_inr": round(annual_energy_cost_ice),
            "energy_cost_ev_inr": round(annual_energy_cost_ev),
            "maintenance_cost_ice_inr": round(annual_maint_cost_ice),
            "maintenance_cost_ev_inr": round(annual_maint_cost_ev),
            "co2_ice_kg": round(annual_co2_ice_kg),
            "co2_ev_kg": round(annual_co2_ev_kg),
            "co2_saved_kg": round(annual_co2_ice_kg - annual_co2_ev_kg),
        },
        "upfront_premium_per_vehicle_inr": round(upfront_premium_per_vehicle),
        "fleet_upfront_premium_inr": round(fleet_upfront_premium),
        "payback_year": payback_year,
        "timeline": timeline,
        "assumptions": {
            "fuel_price_per_l": fuel_price, "electricity_price_per_kwh": elec_price,
            "ev_efficiency_kwh_per_km": ev_kwh_per_km, "ev_grid_emission_factor_kg_per_kwh": ev_grid_factor,
            "ev_maintenance_cost_per_km": ev_maint_per_km, "ice_maintenance_cost_per_km": ice_maint_per_km,
            "ice_vehicle_price_inr": ice_price, "ev_vehicle_price_inr": ev_price,
        },
    })


# ---------------------------------------------------------- PDF EXPORT
@admin_bp.route("/export/report.pdf", methods=["GET"])
@token_required(["admin"])
def export_pdf():
    from fpdf import FPDF

    overview_total_co2 = db.session.query(func.coalesce(func.sum(Trip.actual_co2_kg), 0.0)).scalar()
    overview_total_fuel = db.session.query(func.coalesce(func.sum(Trip.actual_fuel_l), 0.0)).scalar()
    overview_total_cost = db.session.query(func.coalesce(func.sum(Trip.actual_cost), 0.0)).scalar()
    total_trips = Trip.query.filter_by(status="Completed").count()
    total_drivers = Driver.query.filter_by(status="Approved").count()
    total_vehicles = Vehicle.query.count()
    top_drivers = Driver.query.filter_by(status="Approved").order_by(Driver.eco_score.desc()).limit(10).all()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Carbon Footprint Logistics - Fleet Report", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generated {utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Fleet Summary", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Approved Drivers", total_drivers), ("Vehicles", total_vehicles),
        ("Completed Trips", total_trips), ("Total CO2 Emitted (kg)", round(overview_total_co2, 1)),
        ("Total Fuel Used (L)", round(overview_total_fuel, 1)), ("Total Fuel Cost (Rs.)", round(overview_total_cost, 1)),
    ]:
        pdf.cell(0, 7, f"{label}: {value}", ln=True)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Top 10 Drivers by Eco Score", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for i, d in enumerate(top_drivers, start=1):
        pdf.cell(0, 7, f"{i}. {d.name} ({d.driver_code}) - {d.eco_score} pts", ln=True)

    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="fleet_report.pdf")


# ---------------------------------------------------------- ADMIN MANAGEMENT (SuperAdmin only)
@admin_bp.route("/admins", methods=["GET"])
@token_required(["admin"])
@super_admin_required
def list_admins():
    admins = Admin.query.order_by(Admin.id).all()
    return jsonify([a.to_dict() for a in admins])


@admin_bp.route("/admins", methods=["POST"])
@token_required(["admin"])
@super_admin_required
def create_admin():
    data = request.get_json(force=True) or {}
    require_fields(data, ["name", "username", "password"])
    username = validate_username(data["username"])
    validate_password(data["password"])
    role = validate_choice(data.get("role", "Admin"), VALID_ROLES, "role")
    if Admin.query.filter_by(username=username).first():
        raise ConflictError("Username already taken")
    a = Admin(
        name=data["name"].strip(), username=username,
        password_hash=hash_password(data["password"]),
        role=role, status="Active",
    )
    db.session.add(a)
    db.session.flush()
    log_admin_action("admin.create", "Admin", a.id, {"username": a.username, "role": a.role})
    db.session.commit()
    return jsonify(a.to_dict()), 201


@admin_bp.route("/admins/<int:admin_id>", methods=["PUT"])
@token_required(["admin"])
@super_admin_required
def update_admin(admin_id):
    a = db.get_or_404(Admin, admin_id)
    data = request.get_json(force=True) or {}
    if "name" in data:
        if not data["name"] or not data["name"].strip():
            raise ValidationError("name cannot be empty")
        a.name = data["name"].strip()
    if "role" in data:
        a.role = validate_choice(data["role"], VALID_ROLES, "role")
    if "status" in data:
        a.status = validate_choice(data["status"], {"Active", "Inactive"}, "status")
    if data.get("password"):
        validate_password(data["password"])
        a.password_hash = hash_password(data["password"])
    log_admin_action("admin.update", "Admin", a.id, {k: v for k, v in data.items() if k != "password"})
    db.session.commit()
    return jsonify(a.to_dict())


@admin_bp.route("/admins/<int:admin_id>", methods=["DELETE"])
@token_required(["admin"])
@super_admin_required
def delete_admin(admin_id):
    a = db.get_or_404(Admin, admin_id)
    if a.role == "SuperAdmin":
        return jsonify({"error": "Cannot delete the SuperAdmin account"}), 400
    log_admin_action("admin.delete", "Admin", a.id, {"username": a.username})
    db.session.delete(a)
    db.session.commit()
    return jsonify({"message": "Admin removed"})


# ---------------------------------------------------------- BACKUP / RESTORE (SuperAdmin only)
@admin_bp.route("/backup", methods=["GET"])
@token_required(["admin"])
@super_admin_required
def backup():
    def rows(model):
        return [
            {c.name: (getattr(r, c.name).isoformat() if hasattr(getattr(r, c.name), "isoformat") else getattr(r, c.name))
             for c in model.__table__.columns}
            for r in model.query.all()
        ]

    dump = {
        "generated_at": utcnow().isoformat(),
        "admins": rows(Admin), "drivers": rows(Driver), "vehicles": rows(Vehicle),
        "trips": rows(Trip), "notifications": rows(Notification), "settings": rows(Settings),
    }
    buf = io.BytesIO(json.dumps(dump, indent=2).encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="application/json", as_attachment=True,
                      download_name=f"carbontrack_backup_{utcnow().strftime('%Y%m%d_%H%M%S')}.json")


@admin_bp.route("/restore", methods=["POST"])
@token_required(["admin"])
@super_admin_required
def restore():
    """Restores Vehicles, Trips, Notifications and Settings from a backup JSON produced
    by /backup. Admins and Drivers are NOT overwritten by restore (to avoid locking out
    the account performing the restore, or wiping out newer driver registrations/approvals
    that happened after the backup was taken)."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Upload a backup JSON file as 'file'"}), 400
    try:
        dump = json.load(file.stream)
    except Exception:
        return jsonify({"error": "Invalid backup file"}), 400

    def parse_dt(v):
        return datetime.fromisoformat(v) if v else None

    Vehicle.query.delete()
    for row in dump.get("vehicles", []):
        db.session.add(Vehicle(**{**row, "created_at": parse_dt(row.get("created_at"))}))

    Trip.query.delete()
    for row in dump.get("trips", []):
        row = dict(row)
        for k in ["started_at", "ended_at", "created_at"]:
            row[k] = parse_dt(row.get(k))
        db.session.add(Trip(**row))

    Notification.query.delete()
    for row in dump.get("notifications", []):
        db.session.add(Notification(**{**row, "created_at": parse_dt(row.get("created_at"))}))

    Settings.query.delete()
    for row in dump.get("settings", []):
        db.session.add(Settings(id=row["id"], key=row["key"], value=row["value"]))

    db.session.commit()
    return jsonify({"message": "Restore complete (vehicles, trips, notifications, settings)."})


# ---------------------------------------------------------- DEDICATED REPORTS
@admin_bp.route("/reports/vehicles", methods=["GET"])
@token_required(["admin"])
def report_vehicles():
    vehicles = Vehicle.query.all()
    result = []
    for v in vehicles:
        trips = Trip.query.filter_by(vehicle_id=v.id, status="Completed").all()
        total_km = sum(t.distance_km or 0 for t in trips)
        total_fuel = sum(t.actual_fuel_l or 0 for t in trips)
        total_co2 = sum(t.actual_co2_kg or 0 for t in trips)
        result.append({
            "vehicle_id": v.id, "vehicle_no": v.vehicle_no, "vehicle_type": v.vehicle_type,
            "health_score": v.health_score, "trip_count": len(trips),
            "total_km": round(total_km, 1), "total_fuel_l": round(total_fuel, 1),
            "total_co2_kg": round(total_co2, 1),
            "avg_fuel_per_100km": round((total_fuel / total_km * 100), 2) if total_km else 0,
        })
    return jsonify(sorted(result, key=lambda r: r["total_co2_kg"], reverse=True))


@admin_bp.route("/reports/drivers", methods=["GET"])
@token_required(["admin"])
def report_drivers():
    drivers = Driver.query.filter_by(status="Approved").all()
    result = []
    for d in drivers:
        trips = Trip.query.filter_by(driver_id=d.id, status="Completed").all()
        total_km = sum(t.distance_km or 0 for t in trips)
        total_co2 = sum(t.actual_co2_kg or 0 for t in trips)
        result.append({
            "driver_id": d.id, "driver_code": d.driver_code, "name": d.name,
            "eco_score": d.eco_score, "trip_count": len(trips),
            "total_km": round(total_km, 1), "total_co2_kg": round(total_co2, 1),
        })
    return jsonify(sorted(result, key=lambda r: r["eco_score"], reverse=True))


@admin_bp.route("/reports/fuel", methods=["GET"])
@token_required(["admin"])
def report_fuel():
    rows = db.session.query(
        Vehicle.fuel_type, func.sum(Trip.actual_fuel_l), func.sum(Trip.actual_cost), func.count(Trip.id)
    ).join(Trip, Trip.vehicle_id == Vehicle.id).filter(Trip.status == "Completed") \
     .group_by(Vehicle.fuel_type).all()
    return jsonify([
        {"fuel_type": r[0], "total_fuel_l": round(r[1] or 0, 1), "total_cost": round(r[2] or 0, 1), "trip_count": r[3]}
        for r in rows
    ])


@admin_bp.route("/export/report.xlsx", methods=["GET"])
@token_required(["admin"])
def export_xlsx():
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vehicle Report"
    headers = ["Vehicle No", "Type", "Health %", "Trips", "Total KM", "Fuel (L)", "CO2 (kg)"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for v in Vehicle.query.all():
        trips = Trip.query.filter_by(vehicle_id=v.id, status="Completed").all()
        ws.append([
            v.vehicle_no, v.vehicle_type, v.health_score, len(trips),
            round(sum(t.distance_km or 0 for t in trips), 1),
            round(sum(t.actual_fuel_l or 0 for t in trips), 1),
            round(sum(t.actual_co2_kg or 0 for t in trips), 1),
        ])

    ws2 = wb.create_sheet("Driver Report")
    ws2.append(["Driver Code", "Name", "Eco Score", "Trips", "Total KM", "CO2 (kg)"])
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    for d in Driver.query.filter_by(status="Approved").all():
        trips = Trip.query.filter_by(driver_id=d.id, status="Completed").all()
        ws2.append([
            d.driver_code, d.name, d.eco_score, len(trips),
            round(sum(t.distance_km or 0 for t in trips), 1),
            round(sum(t.actual_co2_kg or 0 for t in trips), 1),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      as_attachment=True, download_name="fleet_report.xlsx")


# ---------------------------------------------------------- ANOMALY DETECTION
@admin_bp.route("/anomalies", methods=["GET"])
@token_required(["admin"])
def anomalies():
    """Flags completed trips whose actual CO2 is a statistical outlier (>2 std devs
    above the mean) versus other trips on the same vehicle type."""
    trips = Trip.query.filter(Trip.status == "Completed", Trip.actual_co2_kg != None).all()
    by_type = {}
    for t in trips:
        v = db.session.get(Vehicle, t.vehicle_id)
        vt = v.vehicle_type if v else "Unknown"
        by_type.setdefault(vt, []).append(t)

    flagged = []
    for vt, group in by_type.items():
        values = [t.actual_co2_kg for t in group]
        if len(values) < 5:
            continue
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values) or 1
        for t in group:
            z = (t.actual_co2_kg - mean) / stdev
            if z > 2:
                flagged.append({
                    "trip_code": t.trip_code, "vehicle_type": vt, "co2_kg": t.actual_co2_kg,
                    "fleet_avg_co2_kg": round(mean, 1), "z_score": round(z, 2),
                    "source": t.source, "destination": t.destination,
                })
    return jsonify(sorted(flagged, key=lambda f: f["z_score"], reverse=True)[:25])


# ---------------------------------------------------------- CONTINUOUS LEARNING PIPELINE
@admin_bp.route("/ml/runs", methods=["GET"])
@token_required(["admin"])
def ml_runs():
    runs = ModelRun.query.order_by(ModelRun.started_at.desc()).limit(20).all()
    return jsonify([r.to_dict() for r in runs])


@admin_bp.route("/ml/retrain", methods=["POST"])
@token_required(["admin"])
def trigger_retrain():
    from ml.pipeline import run_training_pipeline
    run = ModelRun(triggered_by="manual", status="running")
    db.session.add(run)
    db.session.commit()
    try:
        metrics, n_rows = run_training_pipeline()
        run.status = "success"
        run.metrics_json = json.dumps(metrics)
        run.training_rows = n_rows
        notify(
            audience="admin", notif_type="SYSTEM", priority="INFO",
            title="Model training completed", category="ml_training",
            message=f"Manual retraining completed on {n_rows} rows.",
        )
    except Exception as e:
        run.status = "failed"
        run.metrics_json = json.dumps({"error": str(e)})
        notify(
            audience="admin", notif_type="SYSTEM", priority="CRITICAL",
            title="Model training failed", category="ml_training",
            message=f"Manual retraining failed: {e}",
        )
    run.finished_at = utcnow()
    db.session.commit()
    return jsonify(run.to_dict())


@admin_bp.route("/ml/models", methods=["GET"])
@token_required(["admin"])
def list_model_versions():
    """Model Registry (Priority 1 #8): every trained version of every model,
    which one is currently active, its metrics, dataset size, and training
    date - grouped by model so the Admin UI can show one row per model with
    an expandable version history."""
    rows = ModelVersion.query.order_by(ModelVersion.model_name, ModelVersion.version.desc()).all()
    grouped = {}
    for r in rows:
        grouped.setdefault(r.model_name, []).append(r.to_dict())
    return jsonify(grouped)


@admin_bp.route("/ml/models/<string:model_name>/rollback/<int:version_id>", methods=["POST"])
@token_required(["admin"])
@super_admin_required
def rollback_model(model_name, version_id):
    """Reactivates a specific past version of a model - e.g. if a retrain's
    metrics looked fine at training time but the model behaves badly in
    practice. SuperAdmin-only since this directly changes what the live
    prediction pipeline serves to every driver."""
    from ml import registry
    target = db.get_or_404(ModelVersion, version_id)
    if target.model_name != model_name:
        raise ValidationError(f"Version {version_id} belongs to model '{target.model_name}', not '{model_name}'")
    try:
        row = registry.rollback_to(version_id)
    except FileNotFoundError as e:
        raise NotFoundError(str(e))
    return jsonify({"message": f"Rolled back {model_name} to v{row.version}", "active_version": row.to_dict()})


# ---------------------------------------------------------- DAILY AI REPORT
@admin_bp.route("/reports/daily", methods=["GET"])
@token_required(["admin"])
def daily_report():
    target_date = request.args.get("date")
    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        day = utcnow() - timedelta(days=1)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    trips = Trip.query.filter(Trip.created_at >= start, Trip.created_at < end, Trip.status == "Completed").all()
    total_co2 = sum(t.actual_co2_kg or 0 for t in trips)
    total_fuel = sum(t.actual_fuel_l or 0 for t in trips)
    total_cost = sum(t.actual_cost or 0 for t in trips)

    return jsonify({
        "date": start.strftime("%Y-%m-%d"), "trip_count": len(trips),
        "total_co2_kg": round(total_co2, 1), "total_fuel_l": round(total_fuel, 1),
        "total_cost": round(total_cost, 1),
        "avg_co2_per_trip": round(total_co2 / len(trips), 1) if trips else 0,
    })


# ---------------------------------------------------------- API DIAGNOSTICS
@admin_bp.route("/diagnostics", methods=["GET"])
@token_required(["admin"])
def diagnostics():
    """One-click health check for every external API this app depends on.
    Runs a real, minimal call against each service and reports pass/fail with
    a plain-language reason - built specifically so you can check everything
    works BEFORE a demo instead of discovering a broken key mid-presentation."""
    import requests as _requests
    from config import Config

    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append({"name": name, "status": "ok", "detail": detail})
        except _requests.exceptions.ConnectionError:
            results.append({"name": name, "status": "fail", "detail": "Could not reach the service at all — check this machine's internet connection (or firewall/proxy) rather than the API key."})
        except _requests.exceptions.Timeout:
            results.append({"name": name, "status": "fail", "detail": "Request timed out — the service may be slow or unreachable right now. Try again."})
        except Exception as e:
            results.append({"name": name, "status": "fail", "detail": str(e)})

    def check_maps_js_key():
        key = Config.GOOGLE_MAPS_API_KEY
        if not key:
            raise Exception("GOOGLE_MAPS_API_KEY is empty in backend/.env")
        return f"Key present ({key[:10]}...). This can't be fully verified server-side — open the app and check the map actually renders."

    def check_geocoding():
        key = Config.GOOGLE_MAPS_API_KEY
        if not key:
            raise Exception("GOOGLE_MAPS_API_KEY is empty in backend/.env")
        r = _requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                           params={"address": "New Delhi, India", "key": key}, timeout=10)
        if not r.ok:
            raise Exception(f"HTTP {r.status_code} from Google — {r.text[:150]}")
        body = r.json()
        if body.get("status") != "OK":
            raise Exception(f"{body.get('status')}: {body.get('error_message', 'Enable Geocoding API in Cloud Console, and confirm billing is active on the project.')}")
        return f"Resolved to {body['results'][0]['formatted_address']}"

    def check_routes():
        key = Config.GOOGLE_ROUTES_API_KEY
        if not key:
            raise Exception("GOOGLE_ROUTES_API_KEY is empty in backend/.env")
        body = {"origin": {"address": "Bengaluru, India"}, "destination": {"address": "Mysuru, India"}, "travelMode": "DRIVE"}
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
                   "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"}
        r = _requests.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers, timeout=15)
        if not r.ok:
            try:
                err = r.json().get("error", {})
                raise Exception(f"{err.get('status', r.status_code)}: {err.get('message', 'Enable Routes API in Cloud Console.')}")
            except ValueError:
                raise Exception(f"HTTP {r.status_code} from Google — {r.text[:150]}")
        try:
            routes = r.json().get("routes", [])
        except ValueError:
            raise Exception(f"Got HTTP 200 but the response wasn't valid JSON — {r.text[:150]}")
        if not routes:
            raise Exception("Request succeeded but returned zero routes — unexpected for this test address pair.")
        return f"Got {len(routes)} route(s), {round(routes[0]['distanceMeters']/1000,1)} km"

    def check_places():
        key = Config.GOOGLE_PLACES_API_KEY
        if not key:
            raise Exception("GOOGLE_PLACES_API_KEY is empty in backend/.env")
        r = _requests.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            json={
                "includedTypes": ["gas_station"], "maxResultCount": 10,
                "locationRestriction": {"circle": {"center": {"latitude": 12.9716, "longitude": 77.5946}, "radius": 5000.0}},
            },
            headers={
                "Content-Type": "application/json", "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.location",
            },
            timeout=10,
        )
        if not r.ok:
            try:
                err = r.json().get("error", {})
                raise Exception(f"{err.get('status', r.status_code)}: {err.get('message', 'Enable Places API (New) in Cloud Console.')}")
            except ValueError:
                raise Exception(f"HTTP {r.status_code} from Google — {r.text[:150]}")
        places = r.json().get("places", [])
        return f"Found {len(places)} nearby place(s) around a test location in Bengaluru"

    def check_weather():
        key = Config.OPENWEATHER_API_KEY
        if not key:
            raise Exception("OPENWEATHER_API_KEY is empty in backend/.env")
        r = _requests.get("https://api.openweathermap.org/data/2.5/weather",
                           params={"q": "Bengaluru", "appid": key, "units": "metric"}, timeout=10)
        if r.status_code == 401:
            raise Exception("401 Unauthorized — key is invalid, or (common with brand-new keys) it hasn't finished activating yet. New OpenWeather keys can take up to 2 hours to activate.")
        r.raise_for_status()
        body = r.json()
        return f"{body['main']['temp']}°C, {body['weather'][0]['main']} in Bengaluru right now"

    def check_smtp():
        import os
        host, user, pw = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
        if not (host and user and pw):
            return "Not configured — OTPs will use dev-mode fallback (printed to console), which is fine for a demo."
        return f"Configured with host {host}"

    check("Google Maps JavaScript key (for map rendering)", check_maps_js_key)
    check("Google Geocoding API", check_geocoding)
    check("Google Routes API", check_routes)
    check("Google Places API", check_places)
    check("OpenWeather API", check_weather)
    check("SMTP (email OTP)", check_smtp)

    return jsonify(results)


# ==================================================================
# Section 21: Carbon Methodology Versioning
# ==================================================================

@admin_bp.route("/carbon-methodologies", methods=["GET"])
@token_required(["admin"])
def list_carbon_methodologies():
    methodologies = CarbonMethodology.query.order_by(CarbonMethodology.effective_date.desc()).all()
    return jsonify([m.to_dict() for m in methodologies])


@admin_bp.route("/carbon-methodologies", methods=["POST"])
@token_required(["admin"])
@super_admin_required
def create_carbon_methodology():
    """Creates a NEW methodology version. Never edits an existing one in
    place — see CarbonMethodology's docstring for why: trips already
    completed under an older version must stay reproducible against the
    numbers that were active when they were computed."""
    data = request.get_json(force=True) or {}
    require_fields(data, ["version_label", "emission_factors"])
    version_label = str(data["version_label"]).strip()
    if not version_label:
        raise ValidationError("version_label is required")
    if CarbonMethodology.query.filter_by(version_label=version_label).first():
        raise ConflictError(f"A methodology version '{version_label}' already exists.")

    emission_factors = data["emission_factors"]
    if not isinstance(emission_factors, dict) or not emission_factors:
        raise ValidationError("emission_factors must be a non-empty object, e.g. {'Diesel': 2.68}")
    for fuel, factor in emission_factors.items():
        validate_positive_number(factor, f"emission_factors.{fuel}", allow_zero=False, required=True, max_value=10)

    price_per_unit = data.get("price_per_unit") or {}
    if price_per_unit and not isinstance(price_per_unit, dict):
        raise ValidationError("price_per_unit must be an object if provided, e.g. {'Diesel': 95}")

    effective_date = _parse_date(data.get("effective_date")) or utcnow().date()

    methodology = CarbonMethodology(
        version_label=version_label,
        effective_date=effective_date,
        emission_factors=json.dumps(emission_factors),
        price_per_unit=json.dumps(price_per_unit) if price_per_unit else None,
        notes=(data.get("notes") or "")[:255],
        is_active=False,  # created inactive — must be explicitly activated (see below)
    )
    db.session.add(methodology)
    db.session.flush()
    log_admin_action("carbon_methodology.create", "CarbonMethodology", methodology.id,
                      {"version_label": version_label})
    db.session.commit()
    return jsonify(methodology.to_dict()), 201


@admin_bp.route("/carbon-methodologies/<int:methodology_id>/activate", methods=["POST"])
@token_required(["admin"])
@super_admin_required
def activate_carbon_methodology(methodology_id):
    """Makes this the ONE active methodology (deactivates all others).
    Every trip ended from this point forward uses this version's emission
    factors; every trip already completed keeps whatever methodology_id it
    was computed under, unaffected by this change."""
    methodology = db.get_or_404(CarbonMethodology, methodology_id)
    CarbonMethodology.query.filter(CarbonMethodology.id != methodology.id).update({"is_active": False})
    methodology.is_active = True
    log_admin_action("carbon_methodology.activate", "CarbonMethodology", methodology.id,
                      {"version_label": methodology.version_label})
    db.session.commit()
    return jsonify(methodology.to_dict())


# ============================================================================
# ADMIN — TRIP REASSIGNMENT REVIEW (spec sections 19-21)
# ============================================================================
MAX_RESOLUTION_NOTE_LEN = 500


@admin_bp.route("/reassignment-requests", methods=["GET"])
@token_required(["admin"])
def list_reassignment_requests():
    q = ReassignmentRequest.query
    status = request.args.get("status")
    if status:
        q = q.filter_by(status=status)
    reqs = q.order_by(ReassignmentRequest.requested_at.desc()).all()
    return jsonify([r.to_dict() for r in reqs])


@admin_bp.route("/reassignment-requests/<int:request_id>", methods=["GET"])
@token_required(["admin"])
def get_reassignment_request(request_id):
    req = db.get_or_404(ReassignmentRequest, request_id)
    return jsonify(req.to_dict())


@admin_bp.route("/reassignment-requests/<int:request_id>/eligible-drivers", methods=["GET"])
@token_required(["admin"])
def eligible_replacement_drivers(request_id):
    """Only Approved drivers who don't already have an Ongoing trip of their
    own may be selected as a replacement (section 21: 'Do not assign an
    inactive driver')."""
    req = db.get_or_404(ReassignmentRequest, request_id)
    busy_ids = {t.driver_id for t in Trip.query.filter_by(status="Ongoing").all()}
    eligible = (Driver.query.filter(Driver.status == "Approved", Driver.id != req.requesting_driver_id)
                .filter(~Driver.id.in_(busy_ids) if busy_ids else True).all())
    return jsonify([d.to_dict() for d in eligible])


@admin_bp.route("/reassignment-requests/<int:request_id>/reject", methods=["POST"])
@token_required(["admin"])
@idempotent(lambda request_id: f"reassignment.reject:{request_id}")
def reject_reassignment_request(request_id):
    req = db.get_or_404(ReassignmentRequest, request_id)
    if req.status != "Pending":
        raise ConflictError(f"This request was already {req.status.lower()}.", code="REASSIGNMENT_NOT_PENDING")
    data = request.get_json(silent=True) or {}
    req.status = "Rejected"
    req.resolution_note = validate_text_length(data.get("note"), "note", MAX_RESOLUTION_NOTE_LEN, required=False)
    req.resolved_by_admin_id = request.user["user_id"]
    req.resolved_at = utcnow()

    trip = db.session.get(Trip, req.trip_id)
    log_admin_action("reassignment.reject", "ReassignmentRequest", req.id, {"trip_code": trip.trip_code if trip else None})
    notify(
        audience="driver", notif_type="TRIP", priority="WARNING",
        title="Reassignment request rejected", category="reassignment",
        message=f"Your reassignment request for {trip.trip_code if trip else 'the trip'} was rejected."
                + (f" Note: {req.resolution_note}" if req.resolution_note else " Please continue the trip if it is safe to do so."),
        driver_id=req.requesting_driver_id, trip_id=req.trip_id,
    )
    db.session.commit()
    return jsonify(req.to_dict())


@admin_bp.route("/reassignment-requests/<int:request_id>/approve", methods=["POST"])
@token_required(["admin"])
@idempotent(lambda request_id: f"reassignment.approve:{request_id}")
def approve_reassignment_request(request_id):
    """Section 20/21: approving does NOT complete the trip. The same Trip
    row keeps its id/status ('Ongoing') — only driver_id changes, to a
    validated, eligible replacement driver."""
    req = db.get_or_404(ReassignmentRequest, request_id)
    if req.status != "Pending":
        raise ConflictError(f"This request was already {req.status.lower()}.", code="REASSIGNMENT_NOT_PENDING")

    data = request.get_json(force=True) or {}
    replacement_driver_id = data.get("replacement_driver_id")
    if not replacement_driver_id:
        raise ValidationError("replacement_driver_id is required.")
    replacement = db.get_or_404(Driver, replacement_driver_id)
    if replacement.id == req.requesting_driver_id:
        raise ValidationError("The replacement driver must be different from the requesting driver.")
    if replacement.status != "Approved":
        raise ValidationError("The replacement driver must be an Approved, active driver.", code="DRIVER_NOT_ELIGIBLE")
    if Trip.query.filter_by(driver_id=replacement.id, status="Ongoing").first():
        raise ConflictError("The replacement driver already has an Ongoing trip.", code="DRIVER_NOT_ELIGIBLE")

    trip = db.get_or_404(Trip, req.trip_id)
    if trip.status != "Ongoing":
        raise ConflictError(f"Trip is no longer Ongoing (status: {trip.status}) — cannot reassign.", code="TRIP_NOT_ONGOING")

    original_driver_id = trip.driver_id
    trip.driver_id = replacement.id  # same trip id/status — never a duplicate trip

    req.status = "Approved"
    req.replacement_driver_id = replacement.id
    req.resolution_note = validate_text_length(data.get("note"), "note", MAX_RESOLUTION_NOTE_LEN, required=False)
    req.resolved_by_admin_id = request.user["user_id"]
    req.resolved_at = utcnow()

    log_admin_action("reassignment.approve", "ReassignmentRequest", req.id, {
        "trip_code": trip.trip_code, "from_driver_id": original_driver_id, "to_driver_id": replacement.id,
    })
    notify(
        audience="driver", notif_type="TRIP", priority="INFO",
        title="Reassignment approved", category="reassignment",
        message=f"Your reassignment request for {trip.trip_code} was approved. {replacement.name} will take over.",
        driver_id=original_driver_id, trip_id=trip.id,
    )
    notify(
        audience="driver", notif_type="TRIP", priority="ACTION",
        title="Trip assigned to you", category="reassignment",
        message=f"Trip {trip.trip_code} ({trip.source} to {trip.destination}) has been reassigned to you. Continue to the destination.",
        driver_id=replacement.id, trip_id=trip.id,
    )
    db.session.commit()
    return jsonify(req.to_dict())


# ============================================================================
# ADMIN — DRIVER CONVERSATIONS / CHAT (spec sections 22-26)
# ============================================================================
from routes.driver import MAX_MESSAGE_LEN  # shared limit, single source of truth


@admin_bp.route("/conversations", methods=["POST"])
@token_required(["admin"])
def open_conversation():
    """Opens (or creates) a conversation with a specific driver."""
    data = request.get_json(force=True) or {}
    driver_id = data.get("driver_id")
    if not driver_id:
        raise ValidationError("driver_id is required")

    db.get_or_404(Driver, driver_id)

    conv = Conversation.query.filter_by(driver_id=driver_id).first()
    if not conv:
        conv = Conversation(driver_id=driver_id, status="Open")
        db.session.add(conv)
        db.session.commit()

    return jsonify(conv.to_dict(viewer_role="admin")), 201

@admin_bp.route("/conversations", methods=["GET"])
@token_required(["admin"])
def list_conversations():
    q = Conversation.query
    driver_id = request.args.get("driver_id")
    trip_id = request.args.get("trip_id")
    status = request.args.get("status")
    if driver_id:
        q = q.filter_by(driver_id=driver_id)
    if trip_id:
        q = q.filter_by(trip_id=trip_id)
    if status:
        q = q.filter_by(status=status)
    convs = q.order_by(Conversation.updated_at.desc()).all()
    return jsonify([c.to_dict(viewer_role="admin") for c in convs])


@admin_bp.route("/conversations/unread-count", methods=["GET"])
@token_required(["admin"])
def get_conversations_unread_count():
    """Total unread messages across all conversations for the admin."""
    # The admin is the 'viewer', so we count messages sent by drivers that are not read.
    # Note: in Conversation.to_dict(viewer_role="admin"), unread_count is computed
    # as the sum of messages where sender_role == "driver" and is_read == False.
    total = db.session.query(func.count(Message.id)).filter(
        Message.sender_role == "driver",
        Message.is_read == False
    ).scalar()
    return jsonify({"unread": total or 0})


@admin_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@token_required(["admin"])
def admin_get_conversation_messages(conversation_id):
    conv = db.get_or_404(Conversation, conversation_id)
    msgs = Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at.asc()).all()
    return jsonify([m.to_dict() for m in msgs])


@admin_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@token_required(["admin"])
@idempotent(lambda conversation_id: f"chat.message:{conversation_id}")
def admin_send_conversation_message(conversation_id):
    conv = db.get_or_404(Conversation, conversation_id)
    data = request.get_json(force=True) or {}
    text = validate_text_length(data.get("message"), "message", MAX_MESSAGE_LEN, required=True)

    msg = Message(conversation_id=conv.id, sender_id=request.user["user_id"], sender_role="admin",
                  message=text.strip(), is_read=False)
    conv.updated_at = utcnow()
    db.session.add(msg)
    db.session.flush()

    notify(
        audience="driver", notif_type="SYSTEM", priority="ACTION",
        title="New message from admin", category="chat",
        message=text.strip()[:200], driver_id=conv.driver_id, trip_id=conv.trip_id,
    )
    db.session.commit()
    return jsonify(msg.to_dict()), 201


@admin_bp.route("/conversations/<int:conversation_id>/read", methods=["POST"])
@token_required(["admin"])
def admin_mark_conversation_read(conversation_id):
    conv = db.get_or_404(Conversation, conversation_id)
    Message.query.filter_by(conversation_id=conv.id, sender_role="driver", is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "Marked as read."})


# ============================================================================
# ADMIN — FEEDBACK (spec section 29: "View feedback")
# ============================================================================
@admin_bp.route("/feedback", methods=["GET"])
@token_required(["admin"])
def list_feedback():
    """All post-trip feedback, newest first. Optional ?experience= filter
    and ?min_rating= (applied to overall_rating) for surfacing complaints."""
    q = TripFeedback.query
    experience = request.args.get("experience")
    if experience:
        q = q.filter_by(experience=experience)
    min_rating = request.args.get("min_rating")
    if min_rating:
        q = q.filter(TripFeedback.overall_rating <= int(min_rating))
    q = q.order_by(TripFeedback.created_at.desc())

    page, per_page = _pagination_params()
    if page:
        result = q.paginate(page=page, per_page=per_page, error_out=False)
        payload = _paginated_response(result, "f")
        items = result.items
    else:
        items = q.limit(500).all()
        payload = {"items": [i.to_dict() for i in items]}

    # Enrich with trip/driver context the raw TripFeedback.to_dict() doesn't carry.
    enriched = []
    for f, item in zip(items, payload["items"]):
        trip = db.session.get(Trip, f.trip_id)
        driver = db.session.get(Driver, f.driver_id)
        enriched.append({
            **item,
            "trip_code": trip.trip_code if trip else None,
            "route": f"{trip.source} → {trip.destination}" if trip else None,
            "driver_name": driver.name if driver else None,
        })
    payload["items"] = enriched
    return jsonify(payload)

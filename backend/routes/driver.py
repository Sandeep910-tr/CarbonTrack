import io
from flask import Blueprint, request, jsonify, send_file, current_app
import polyline as polyline_lib
from models.db import (
    db, Driver, Vehicle, Trip, Notification, Settings, TripLocation, RouteDeviation,
    ReassignmentRequest, Conversation, Message, utcnow,
)
from routes.auth_utils import token_required
from validators import validate_lat_lng, validate_choice, validate_text_length
from audit import log_driver_action
from notifications import notify, resolve
from idempotency import idempotent
from geo import haversine_m
from errors import ValidationError, ForbiddenError, ConflictError, NotFoundError

driver_bp = Blueprint("driver", __name__)

# Tiered deviation thresholds (spec section 16):
#   < 200m            no alert
#   200-500m          driver awareness only (surfaced in UI via deviation_m, no notification)
#   500m-1km          driver notification
#   > 1km             high-priority driver + admin notification
DEVIATION_AWARENESS_M = 200
DEVIATION_NOTIFY_M = 500
DEVIATION_CRITICAL_M = 1000
DEVIATION_THRESHOLD_M = DEVIATION_NOTIFY_M  # kept for any other reference to "the" deviation threshold

# _haversine_m kept as a local alias (module already had callers using this
# name) - the actual implementation now lives in geo.py so trips.py's
# destination-lock check can reuse the exact same formula instead of a copy.
_haversine_m = haversine_m


def _min_distance_to_route_m(lat, lng, route_points):
    return min(_haversine_m(lat, lng, p[0], p[1]) for p in route_points)


# ------------------------------------------------------------ DESTINATION LOCK (5km arrival radius)
REASSIGNMENT_REASONS = (
    "Medical Emergency", "Vehicle Breakdown", "Accident / Safety Issue",
    "Personal Emergency", "Vehicle Problem", "Unable to Continue", "Other",
)


def destination_status(trip):
    """Section 15/16: single source of truth for "how far is this trip's
    driver from the destination, and is End Trip currently allowed" - used
    by the location-ping response, GET /driver/active-trip (so a page
    reload/reconnect restores the correct lock state), and reused by
    routes/trips.py:end_trip for the authoritative backend check. Returns
    None fields rather than fabricated numbers whenever something required
    (destination coords, a GPS fix, an accurate-enough fix) is missing -
    the caller decides what that means for its own response.
    """
    radius_m = current_app.config.get("DESTINATION_ARRIVAL_RADIUS_M", 5000)
    accuracy_threshold_m = current_app.config.get("GPS_ACCURACY_THRESHOLD_M", 75)

    result = {
        "arrival_radius_m": radius_m,
        "distance_to_destination_m": None,
        "destination_reached": False,
        "gps_available": False,
        "gps_accuracy_ok": False,
        "destination_known": trip.dest_lat is not None and trip.dest_lng is not None,
        "end_trip_allowed": False,
        "reason": None,
    }
    if not result["destination_known"]:
        result["reason"] = "Destination coordinates are missing for this trip."
        return result

    last_ping = (TripLocation.query.filter_by(trip_id=trip.id)
                 .order_by(TripLocation.recorded_at.desc()).first())
    if last_ping is None:
        result["reason"] = "Waiting for a GPS location before arrival can be verified."
        return result
    result["gps_available"] = True

    if last_ping.accuracy_m is None or last_ping.accuracy_m > accuracy_threshold_m:
        result["reason"] = "GPS accuracy is insufficient to verify your destination."
        # Still report distance for UI context, even though it isn't trusted yet.
        result["distance_to_destination_m"] = round(
            _haversine_m(last_ping.lat, last_ping.lng, trip.dest_lat, trip.dest_lng)
        )
        return result
    result["gps_accuracy_ok"] = True

    distance_m = _haversine_m(last_ping.lat, last_ping.lng, trip.dest_lat, trip.dest_lng)
    result["distance_to_destination_m"] = round(distance_m)
    if distance_m <= radius_m:
        result["destination_reached"] = True
        result["end_trip_allowed"] = True
    else:
        result["reason"] = f"You are still ~{round(distance_m)}m from the destination."
    return result


@driver_bp.route("/conversations/unread-count", methods=["GET"])
@token_required(["driver"])
def get_conversations_unread_count():
    """Total unread messages from admin across all conversations for the driver."""
    total = db.session.query(func.count(Message.id)).join(Conversation).filter(
        Conversation.driver_id == request.user["user_id"],
        Message.sender_role == "admin",
        Message.is_read == False
    ).scalar()
    return jsonify({"unread": total or 0})

@driver_bp.route("/profile", methods=["GET"])
@token_required(["driver"])
def profile():
    d = db.get_or_404(Driver, request.user["user_id"])
    data = d.to_dict()
    if d.assigned_vehicle_id:
        v = db.session.get(Vehicle, d.assigned_vehicle_id)
        data["vehicle"] = v.to_dict() if v else None
    else:
        data["vehicle"] = None
    return jsonify(data)


@driver_bp.route("/profile", methods=["PUT"])
@token_required(["driver"])
def update_profile():
    """Section 4: Driver profile editing. Allows updating personal details
    but prevents modification of security/administrative fields (role, status, etc)."""
    d = db.get_or_404(Driver, request.user["user_id"])
    data = request.get_json(force=True) or {}

    # Validation
    if "name" in data:
        d.name = validate_text_length(data["name"], "name", 120, required=True)
    if "email" in data:
        email = validate_email(data["email"])
        if Driver.query.filter(Driver.email == email, Driver.id != d.id).first():
            raise ConflictError("This email is already registered to another account")
        d.email = email
    if "phone" in data:
        phone = validate_phone(data["phone"])
        if Driver.query.filter(Driver.phone == phone, Driver.id != d.id).first():
            raise ConflictError("This phone number is already registered to another account")
        d.phone = phone
    if "dob" in data:
        d.dob = validate_text_length(data["dob"], "dob", 20, required=False)
    if "address" in data:
        d.address = validate_text_length(data["address"], "address", 255, required=False)
    if "experience_years" in data:
        d.experience_years = validate_positive_number(data["experience_years"], "experience_years", allow_zero=True, required=False)
    if "emergency_contact" in data:
        d.emergency_contact = validate_phone(data["emergency_contact"], "emergency_contact")

    log_driver_action("DRIVER_PROFILE_UPDATED", "Driver", d.id, {"updated_fields": list(data.keys())})
    db.session.commit()
    return jsonify({"message": "Profile updated successfully", "profile": d.to_dict()})


@driver_bp.route("/trips", methods=["GET"])
@token_required(["driver"])
def my_trips():
    trips = Trip.query.filter_by(driver_id=request.user["user_id"]) \
        .order_by(Trip.created_at.desc()).all()
    return jsonify([t.to_dict() for t in trips])


@driver_bp.route("/active-trip", methods=["GET"])
@token_required(["driver"])
def active_trip():
    """Source of truth for whether the logged-in driver currently has a
    trip in progress. The frontend calls this on mount (and whenever it
    needs to know) instead of trusting local/session state, so a trip
    started earlier — then left, refreshed away from, or reopened in a new
    tab/session — is always correctly restored (or correctly NOT restored,
    once it's completed). Only ever returns a trip belonging to the
    authenticated driver."""
    trip = (
        Trip.query.filter_by(driver_id=request.user["user_id"], status="Ongoing")
        .order_by(Trip.started_at.desc())
        .first()
    )
    payload = {"trip": trip.to_dict() if trip else None}
    if trip:
        payload["destination_status"] = destination_status(trip)
    return jsonify(payload)


@driver_bp.route("/notifications", methods=["GET"])
@token_required(["driver"])
def my_notifications():
    driver_id = request.user["user_id"]
    notes = Notification.query.filter(
        (Notification.driver_id == driver_id) | (Notification.audience.in_(["all"]))
    ).order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notes])


@driver_bp.route("/notifications/unread-count", methods=["GET"])
@token_required(["driver"])
def my_notifications_unread_count():
    from notifications import unread_count
    return jsonify({"unread": unread_count(driver_id=request.user["user_id"])})


@driver_bp.route("/notifications/read-all", methods=["POST"])
@token_required(["driver"])
def my_notifications_mark_all_read():
    from notifications import mark_all_read
    mark_all_read(driver_id=request.user["user_id"])
    db.session.commit()
    return jsonify({"message": "All notifications marked as read."})


@driver_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@token_required(["driver"])
def my_notification_mark_read(notification_id):
    from notifications import mark_read
    mark_read([notification_id], driver_id=request.user["user_id"])
    db.session.commit()
    return jsonify({"message": "Notification marked as read."})


@driver_bp.route("/sos", methods=["POST"])
@token_required(["driver"])
def send_sos():
    data = request.get_json(silent=True) or {}
    driver = db.get_or_404(Driver, request.user["user_id"])
    notify(
        audience="admin", notif_type="SYSTEM", priority="CRITICAL",
        title="SOS alert", category="sos",
        message=f"SOS from {driver.name} ({driver.driver_code}): {data.get('note', 'Emergency assistance requested.')}",
        driver_id=driver.id,
    )
    db.session.commit()
    return jsonify({"message": "SOS alert sent to fleet admins."}), 201


# ---------------------------------------------------------- LIVE LOCATION PING
def _record_location_ping(trip_id, data):
    """Shared implementation behind both location-ping routes (trip-scoped and
    the flat /driver/location route). Kept as one function so validation,
    the deviation check, and the response shape can never drift between the
    two entry points."""
    lat, lng = data.get("lat"), data.get("lng")
    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400
    lat, lng = validate_lat_lng(lat, lng)

    speed_kmph = data.get("speed")
    if speed_kmph is not None:
        try:
            speed_kmph = max(0.0, float(speed_kmph))
        except (TypeError, ValueError):
            return jsonify({"error": "speed must be a number"}), 400

    accuracy_m = data.get("accuracy")
    if accuracy_m is not None:
        try:
            accuracy_m = max(0.0, float(accuracy_m))
        except (TypeError, ValueError):
            return jsonify({"error": "accuracy must be a number"}), 400

    heading = data.get("heading")
    if heading is not None:
        try:
            heading = float(heading) % 360
        except (TypeError, ValueError):
            return jsonify({"error": "heading must be a number"}), 400

    trip = db.get_or_404(Trip, trip_id)
    # Authenticated driver only, and only for their own trip.
    if trip.driver_id != request.user["user_id"]:
        return jsonify({"error": "This trip doesn't belong to you"}), 403
    # Active trip required — pings outside an Ongoing trip are rejected.
    if trip.status != "Ongoing":
        return jsonify({"error": "Location pings are only accepted while a trip is Ongoing"}), 400

    # Section 24 (GPS): detect impossible GPS jumps. Compare this fix
    # against the driver's last recorded ping for the same trip - if the
    # implied speed between the two is something no road vehicle in this
    # fleet could achieve (a satellite-positioning glitch, a spoofed
    # coordinate, or a client bug), reject the ping rather than silently
    # accepting a movement that didn't happen. The elapsed-time floor avoids
    # false positives from two pings arriving in the same second (where
    # ordinary GPS jitter, divided by a near-zero time delta, would produce
    # an enormous but meaningless "speed").
    MAX_PLAUSIBLE_SPEED_KMPH = 220
    MIN_ELAPSED_SECONDS_FOR_CHECK = 2
    last_ping = (TripLocation.query.filter_by(trip_id=trip.id)
                 .order_by(TripLocation.recorded_at.desc()).first())
    if last_ping is not None:
        elapsed_s = (utcnow() - last_ping.recorded_at).total_seconds()
        if elapsed_s >= MIN_ELAPSED_SECONDS_FOR_CHECK:
            jump_km = _haversine_m(lat, lng, last_ping.lat, last_ping.lng) / 1000
            implied_speed_kmph = jump_km / (elapsed_s / 3600)
            if implied_speed_kmph > MAX_PLAUSIBLE_SPEED_KMPH:
                current_app.logger.warning(
                    "Rejected GPS ping for trip %s: implied speed %.0f km/h over %.0fs (%.2f km jump)",
                    trip.id, implied_speed_kmph, elapsed_s, jump_km,
                )
                return jsonify({
                    "error": "This location update implies an impossible speed and was not recorded. "
                             "If your GPS signal was briefly lost, the next good fix will be accepted normally.",
                    "code": "IMPOSSIBLE_GPS_JUMP",
                }), 400

    ping = TripLocation(
        trip_id=trip.id, driver_id=trip.driver_id, lat=lat, lng=lng,
        heading=heading, accuracy_m=accuracy_m, speed_kmph=speed_kmph,
    )
    db.session.add(ping)

    # Automatic geofence check: how far is this fix from the planned route?
    # Tiered by distance (section 16) and deduped per-trip via dedup_key
    # (section 44) so a driver who's genuinely off-route gets exactly one
    # notification per severity tier, not one per GPS ping — and the
    # notification auto-resolves (so a fresh one CAN fire again) once the
    # driver gets back within the awareness band.
    deviation_m = None
    if trip.route_polyline:
        try:
            route_points = polyline_lib.decode(trip.route_polyline)
            if route_points:
                deviation_m = _min_distance_to_route_m(lat, lng, route_points)
                dedup_key = f"trip:{trip.id}:route_deviation"

                if deviation_m <= DEVIATION_AWARENESS_M:
                    # Back on route: close out any open deviation record/notification
                    # so the NEXT genuine deviation can notify again.
                    if trip.deviation_flagged:
                        trip.deviation_flagged = False
                        now = utcnow()
                        RouteDeviation.query.filter_by(trip_id=trip.id, status="Active").update(
                            {"status": "Resolved", "resolved_at": now}
                        )
                        resolve(dedup_key)
                elif deviation_m > DEVIATION_AWARENESS_M:
                    if not trip.deviation_flagged:
                        trip.deviation_flagged = True
                        db.session.add(RouteDeviation(
                            trip_id=trip.id, driver_id=trip.driver_id, lat=lat, lng=lng,
                            deviation_m=deviation_m, status="Active",
                        ))
                    if deviation_m > DEVIATION_CRITICAL_M:
                        # High priority: driver + admin
                        notify(
                            audience="driver", notif_type="TRIP", priority="CRITICAL",
                            title="Significant route deviation", category="route_deviation",
                            message=f"You are ~{round(deviation_m)}m off the planned route on {trip.trip_code}. Recalculating route.",
                            driver_id=trip.driver_id, trip_id=trip.id, dedup_key=dedup_key,
                        )
                        notify(
                            audience="admin", notif_type="TRIP", priority="CRITICAL",
                            title="Significant route deviation", category="route_deviation",
                            message=f"{trip.trip_code} is ~{round(deviation_m)}m off its planned route — over 1km.",
                            driver_id=trip.driver_id, trip_id=trip.id, dedup_key=dedup_key,
                        )
                    elif deviation_m > DEVIATION_NOTIFY_M:
                        # Driver notification only; admin sees it in the "large only" tier
                        notify(
                            audience="driver", notif_type="TRIP", priority="WARNING",
                            title="Route deviation", category="route_deviation",
                            message=f"You are ~{round(deviation_m)}m off the planned route on {trip.trip_code}.",
                            driver_id=trip.driver_id, trip_id=trip.id, dedup_key=dedup_key,
                        )
                    # 200-500m: awareness only, surfaced via deviation_m in the response, no notification row.
        except Exception:
            current_app.logger.exception("Route-deviation check failed for trip %s (ping still recorded)", trip.id)

    db.session.commit()
    resp = {"message": "Location recorded", "recorded_at": ping.recorded_at.isoformat(), "trip_id": trip.id}
    if deviation_m is not None:
        resp["deviation_m"] = round(deviation_m)
    # Section 15/16: every ping response tells the frontend exactly whether
    # End Trip should currently be enabled, so the UI never has to guess or
    # duplicate the distance/accuracy logic itself.
    resp["destination_status"] = destination_status(trip)
    return jsonify(resp), 201


@driver_bp.route("/trips/<int:trip_id>/location", methods=["POST"])
@token_required(["driver"])
def report_location(trip_id):
    """Original trip-scoped ping route. Kept exactly as-is for backward
    compatibility — the driver frontend (NewTrip.jsx) and the offline retry
    queue both already call this URL, so nothing else needs to change."""
    data = request.get_json(silent=True) or {}
    return _record_location_ping(trip_id, data)


@driver_bp.route("/location", methods=["POST"])
@token_required(["driver"])
def report_location_flat():
    """POST /api/driver/location — flat route matching the requested API
    contract (trip_id in the JSON body instead of the URL). Delegates to the
    exact same validation/storage/deviation logic as the trip-scoped route
    above, so behavior is identical either way."""
    data = request.get_json(silent=True) or {}
    trip_id = data.get("trip_id")
    if trip_id is None:
        return jsonify({"error": "trip_id is required"}), 400
    try:
        trip_id = int(trip_id)
    except (TypeError, ValueError):
        return jsonify({"error": "trip_id must be an integer"}), 400
    return _record_location_ping(trip_id, data)


@driver_bp.route("/trips/<int:trip_id>/route", methods=["PATCH"])
@token_required(["driver"])
def update_trip_route(trip_id):
    """Called after the client automatically recalculates a route (the driver
    went far enough off-path). Replaces the stored planned route so future
    location pings are checked against the NEW path instead of the stale one,
    and un-flags deviation so a genuinely new deviation can be caught again."""
    trip = db.get_or_404(Trip, trip_id)
    if trip.driver_id != request.user["user_id"]:
        return jsonify({"error": "This trip doesn't belong to you"}), 403
    if trip.status != "Ongoing":
        return jsonify({"error": "Can only reroute an Ongoing trip"}), 400

    data = request.get_json(silent=True) or {}
    polyline_str = data.get("route_polyline")
    if not polyline_str:
        return jsonify({"error": "route_polyline is required"}), 400

    trip.route_polyline = polyline_str
    trip.deviation_flagged = False
    now = utcnow()
    RouteDeviation.query.filter_by(trip_id=trip.id, status="Active").update(
        {"status": "Resolved", "resolved_at": now}
    )
    resolve(f"trip:{trip.id}:route_deviation")
    notify(
        audience="driver", notif_type="TRIP", priority="INFO",
        title="Route updated", category="reroute",
        message="A new route has been calculated.",
        driver_id=trip.driver_id, trip_id=trip.id,
    )
    notify(
        audience="admin", notif_type="TRIP", priority="INFO",
        title="Trip rerouted", category="reroute",
        message=f"{trip.trip_code} was automatically rerouted after going off the planned route.",
        driver_id=trip.driver_id, trip_id=trip.id,
    )
    db.session.commit()
    return jsonify({"message": "Route updated"})


@driver_bp.route("/route-deviation", methods=["POST"])
@token_required(["driver"])
def report_route_deviation():
    data = request.get_json(force=True)
    trip_id = data.get("trip_id")
    driver = db.get_or_404(Driver, request.user["user_id"])
    trip = db.session.get(Trip, trip_id) if trip_id else None
    # Ownership check: never trust a trip_id from the request body as-is.
    # Without this, any driver could reference an arbitrary OTHER driver's
    # trip_code in an admin-facing notification (spoofing/confusing the
    # audit trail), even though nothing here reads back the other trip's
    # data to the caller. Treat an unowned trip_id the same as no trip_id.
    if trip is not None and trip.driver_id != driver.id:
        trip = None
    label = trip.trip_code if trip else "current trip"
    notify(
        audience="admin", notif_type="TRIP", priority="WARNING",
        title="Route deviation reported", category="route_deviation",
        message=f"Route deviation flagged by {driver.name} on {label}.",
        driver_id=driver.id, trip_id=trip.id if trip else None,
    )
    db.session.commit()
    return jsonify({"message": "Route deviation logged."}), 201


# ---------------------------------------------------------- ECO-DRIVING CERTIFICATE
def _certificate_threshold():
    row = Settings.query.filter_by(key="certificate_eco_threshold").first()
    return float(row.value) if row else 80.0


@driver_bp.route("/certificate/status", methods=["GET"])
@token_required(["driver"])
def certificate_status():
    driver = db.get_or_404(Driver, request.user["user_id"])
    threshold = _certificate_threshold()
    eligible = driver.eco_score >= threshold
    return jsonify({
        "eligible": eligible,
        "eco_score": driver.eco_score,
        "threshold": threshold,
        "points_to_go": max(0, round(threshold - driver.eco_score, 1)),
    })


def _fit_font_size(pdf, text, style, max_size, min_size, max_width_mm):
    """Shrinks a font size (Times, given style) until `text` fits within
    max_width_mm, without ever going below min_size — the adaptive-sizing
    safeguard against clipping/overlap for very long driver names or, in
    principle, a very long title, per the certificate QA requirements
    (short name, long name, etc. must all render cleanly)."""
    size = max_size
    while size > min_size:
        pdf.set_font("Times", style, size)
        if pdf.get_string_width(text) <= max_width_mm:
            return size
        size -= 1
    pdf.set_font("Times", style, min_size)
    return min_size


def _corner_flourish(pdf, x, y, dx, dy, gold):
    """A small restrained corner accent (two short lines forming an open
    angle bracket) at one inner-border corner — decorative only, kept
    deliberately minimal per 'do not overdecorate'."""
    pdf.set_draw_color(*gold)
    pdf.set_line_width(0.5)
    pdf.line(x, y, x + dx * 7, y)
    pdf.line(x, y, x, y + dy * 7)


@driver_bp.route("/certificate/download", methods=["GET"])
@token_required(["driver"])
def certificate_download():
    from fpdf import FPDF

    driver = db.get_or_404(Driver, request.user["user_id"])
    threshold = _certificate_threshold()
    if driver.eco_score < threshold:
        return jsonify({"error": f"Not eligible yet — eco score must reach {threshold}, currently at {driver.eco_score}."}), 403

    company = Settings.query.filter_by(key="company_name").first()
    company_name = company.value if company else "CarbonTrack Logistics"
    trip_count = Trip.query.filter_by(driver_id=driver.id, status="Completed").count()
    issued_str = utcnow().strftime("%d %B %Y")

    # ---- Palette: ivory paper, deep charcoal ink, emerald green, refined
    # gold — the brief's own sustainability/corporate direction, deliberately
    # distinct from the app's dark-UI amber/indigo/cyan theme (appropriate
    # here: this is a printed/downloaded document, not a screen). ----
    IVORY = (250, 247, 239)
    CHARCOAL = (32, 36, 32)
    CHARCOAL_SOFT = (95, 103, 96)
    EMERALD = (13, 92, 66)
    EMERALD_SOFT = (99, 122, 111)
    GOLD = (176, 137, 58)
    GOLD_SOFT = (201, 173, 117)

    PAGE_W, PAGE_H = 297, 210
    MARGIN_OUTER, MARGIN_INNER = 8, 14
    CONTENT_L, CONTENT_R = 30, PAGE_W - 30
    CONTENT_W = CONTENT_R - CONTENT_L

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    # Every element below is placed at an absolute, hand-checked coordinate
    # within this single A4-landscape page — fpdf2's default 20mm
    # auto-page-break margin has no use here and, left enabled, silently
    # pushed the signature/seal block onto an unwanted second page.
    pdf.set_auto_page_break(False)
    pdf.set_fill_color(*IVORY)
    pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")

    # ---- Refined double border (outer gold, inner emerald) + a thin
    # hairline between them, per the brief's 'refined double border'. ----
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.9)
    pdf.rect(MARGIN_OUTER, MARGIN_OUTER, PAGE_W - 2 * MARGIN_OUTER, PAGE_H - 2 * MARGIN_OUTER)
    pdf.set_draw_color(*GOLD_SOFT)
    pdf.set_line_width(0.25)
    pdf.rect(MARGIN_OUTER + 3, MARGIN_OUTER + 3, PAGE_W - 2 * (MARGIN_OUTER + 3), PAGE_H - 2 * (MARGIN_OUTER + 3))
    pdf.set_draw_color(*EMERALD)
    pdf.set_line_width(0.6)
    pdf.rect(MARGIN_INNER, MARGIN_INNER, PAGE_W - 2 * MARGIN_INNER, PAGE_H - 2 * MARGIN_INNER)

    # Minimal corner flourishes at the inner border's four corners.
    ix0, iy0 = MARGIN_INNER, MARGIN_INNER
    ix1, iy1 = PAGE_W - MARGIN_INNER, PAGE_H - MARGIN_INNER
    _corner_flourish(pdf, ix0, iy0, 1, 1, GOLD)
    _corner_flourish(pdf, ix1, iy0, -1, 1, GOLD)
    _corner_flourish(pdf, ix0, iy1, 1, -1, GOLD)
    _corner_flourish(pdf, ix1, iy1, -1, -1, GOLD)

    # ---- Brand ----
    pdf.set_y(26)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*EMERALD)
    pdf.cell(0, 7, " ".join(company_name.upper()), align="C", ln=True)
    pdf.set_y(34)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 5, "E C O - D R I V I N G   R E C O G N I T I O N   P R O G R A M", align="C", ln=True)

    # Short centered divider under the brand block.
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.4)
    pdf.line(PAGE_W / 2 - 16, 43, PAGE_W / 2 + 16, 43)

    # ---- Title (adaptive-fit: never overflows CONTENT_W) ----
    title = "Certificate of Eco-Driving Excellence"
    title_size = _fit_font_size(pdf, title, "B", 30, 20, CONTENT_W - 10)
    pdf.set_y(52)
    pdf.set_font("Times", "B", title_size)
    pdf.set_text_color(*CHARCOAL)
    pdf.cell(0, 14, title, align="C", ln=True)

    # ---- Recognition line ----
    pdf.set_y(76)
    pdf.set_font("Helvetica", "I", 12)
    pdf.set_text_color(*EMERALD_SOFT)
    pdf.cell(0, 8, "This certificate is proudly presented to", align="C", ln=True)

    # ---- Recipient name: the strongest visual element, adaptively sized
    # so a long name never clips or overlaps neighboring elements. ----
    name_size = _fit_font_size(pdf, driver.name, "B", 34, 18, CONTENT_W - 20)
    pdf.set_y(88)
    pdf.set_font("Times", "B", name_size)
    pdf.set_text_color(*EMERALD)
    pdf.cell(0, 16, driver.name, align="C", ln=True)
    name_w = pdf.get_string_width(driver.name)
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.5)
    pdf.line(PAGE_W / 2 - min(name_w, CONTENT_W - 20) / 2, 106, PAGE_W / 2 + min(name_w, CONTENT_W - 20) / 2, 106)

    # ---- Achievement narrative (same text/values as before) ----
    pdf.set_y(112)
    pdf.set_font("Helvetica", "", 11.5)
    pdf.set_text_color(*CHARCOAL_SOFT)
    pdf.set_x(CONTENT_L)
    pdf.multi_cell(
        CONTENT_W, 7,
        f"for achieving an Eco-Driving Score of {driver.eco_score}/100 across {trip_count} logged trips,\n"
        f"demonstrating consistent fuel-efficient and low-carbon driving practices.",
        align="C",
    )

    # ---- Stat chips: the same 3 data points the previous layout showed
    # (eco score, trip count, driver code) plus the existing issue date,
    # now presented as labeled columns instead of a plain text row. ----
    chip_y = 140
    pdf.set_draw_color(*GOLD_SOFT)
    pdf.set_line_width(0.3)
    pdf.line(CONTENT_L + 20, chip_y - 6, CONTENT_R - 20, chip_y - 6)

    chips = [
        ("ECO-DRIVING SCORE", f"{driver.eco_score}/100"),
        ("COMPLETED TRIPS", str(trip_count)),
        ("DRIVER CODE", driver.driver_code),
        ("ISSUED", issued_str),
    ]
    col_w = (CONTENT_R - CONTENT_L) / len(chips)
    for i, (label, value) in enumerate(chips):
        cx = CONTENT_L + i * col_w
        if i > 0:
            pdf.set_draw_color(*GOLD_SOFT)
            pdf.set_line_width(0.25)
            pdf.line(cx, chip_y - 2, cx, chip_y + 14)
        pdf.set_xy(cx, chip_y)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GOLD)
        pdf.cell(col_w, 5, label, align="C")
        pdf.set_xy(cx, chip_y + 6)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*CHARCOAL)
        pdf.cell(col_w, 7, value, align="C")

    # ---- Signature area: no real signer/signature data exists in this
    # app, so per the brief this uses the existing organizational label
    # (company_name, already fetched above) instead of inventing a person. ----
    sig_y = PAGE_H - MARGIN_INNER - 16
    pdf.set_draw_color(*CHARCOAL_SOFT)
    pdf.set_line_width(0.3)
    pdf.line(CONTENT_L, sig_y, CONTENT_L + 55, sig_y)
    pdf.set_xy(CONTENT_L, sig_y + 2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*CHARCOAL_SOFT)
    pdf.cell(55, 5, "Fleet Operations", align="L")
    pdf.set_xy(CONTENT_L, sig_y + 7)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(55, 5, company_name, align="L")

    # ---- Seal: decorative/branding only — no ISO, government, or
    # third-party certification is claimed anywhere on it. ----
    seal_cx, seal_cy, seal_r = CONTENT_R - 18, sig_y - 2, 15
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.7)
    pdf.circle(seal_cx, seal_cy, seal_r)
    pdf.set_draw_color(*EMERALD)
    pdf.set_line_width(0.3)
    pdf.circle(seal_cx, seal_cy, seal_r - 2.2)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*EMERALD)
    pdf.set_xy(seal_cx - seal_r, seal_cy - 6)
    pdf.cell(seal_r * 2, 4, "CARBONTRACK", align="C")
    pdf.set_font("Helvetica", "", 5.5)
    pdf.set_text_color(*GOLD)
    pdf.set_xy(seal_cx - seal_r, seal_cy - 1.5)
    pdf.cell(seal_r * 2, 3.5, "ECO-DRIVING", align="C")
    pdf.set_xy(seal_cx - seal_r, seal_cy + 2)
    pdf.cell(seal_r * 2, 3.5, "EXCELLENCE", align="C")

    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                      download_name=f"eco_certificate_{driver.driver_code}.pdf")


# ============================================================================
# EMERGENCY / PERSONAL PROBLEM — TRIP REASSIGNMENT (spec sections 19-21)
# ============================================================================
MAX_REASSIGNMENT_DESCRIPTION_LEN = 1000


@driver_bp.route("/trips/<int:trip_id>/reassignment-request", methods=["POST"])
@token_required(["driver"])
@idempotent(lambda trip_id: f"reassignment.request:{trip_id}")
def request_reassignment(trip_id):
    """Driver-initiated request to hand an Ongoing trip to another driver
    because of a genuine problem (medical, breakdown, accident, personal).
    This is deliberately separate from End Trip: it does NOT complete the
    trip (section 20) — the same Trip row keeps its id/status and is simply
    reassigned to a different driver once an admin approves."""
    trip = db.get_or_404(Trip, trip_id)
    if trip.driver_id != request.user["user_id"]:
        raise ForbiddenError("This trip doesn't belong to you.")
    if trip.status != "Ongoing":
        raise ValidationError(f"Only an Ongoing trip can request reassignment (this trip is '{trip.status}').")

    existing = ReassignmentRequest.query.filter_by(trip_id=trip.id, status="Pending").first()
    if existing:
        raise ConflictError("A reassignment request is already pending for this trip.", code="REASSIGNMENT_ALREADY_PENDING")

    data = request.get_json(force=True) or {}
    reason = validate_choice(data.get("reason"), REASSIGNMENT_REASONS, "reason")
    description = validate_text_length(data.get("description"), "description", MAX_REASSIGNMENT_DESCRIPTION_LEN, required=False)
    if reason == "Other" and not (description or "").strip():
        raise ValidationError("An explanation is required when reason is 'Other'.")

    driver = db.get_or_404(Driver, request.user["user_id"])
    last_ping = (TripLocation.query.filter_by(trip_id=trip.id)
                 .order_by(TripLocation.recorded_at.desc()).first())

    req = ReassignmentRequest(
        trip_id=trip.id, requesting_driver_id=driver.id, reason=reason, description=description,
        status="Pending",
        request_lat=last_ping.lat if last_ping else None,
        request_lng=last_ping.lng if last_ping else None,
    )
    db.session.add(req)
    db.session.flush()

    notify(
        audience="admin", notif_type="TRIP", priority="CRITICAL",
        title="Trip reassignment requested", category="reassignment",
        message=f"{driver.name} requested reassignment on {trip.trip_code} ({reason}): {(description or '').strip()[:200] or 'No further details.'}",
        driver_id=driver.id, trip_id=trip.id,
    )
    db.session.commit()
    return jsonify(req.to_dict()), 201


@driver_bp.route("/reassignment-requests", methods=["GET"])
@token_required(["driver"])
def my_reassignment_requests():
    reqs = (ReassignmentRequest.query.filter_by(requesting_driver_id=request.user["user_id"])
            .order_by(ReassignmentRequest.requested_at.desc()).all())
    return jsonify([r.to_dict() for r in reqs])


# ============================================================================
# DRIVER <-> ADMIN CONVERSATIONS / CHAT (spec sections 22-26)
# ============================================================================
MAX_MESSAGE_LEN = 2000


def _driver_owned_conversation_or_404(conversation_id, driver_id):
    """Section 44 (Chat Security): a driver may only ever read/write a
    conversation that belongs to them - never another driver's."""
    conv = db.get_or_404(Conversation, conversation_id)
    if conv.driver_id != driver_id:
        raise ForbiddenError("This conversation doesn't belong to you.")
    return conv


@driver_bp.route("/conversations", methods=["GET"])
@token_required(["driver"])
def list_my_conversations():
    convs = (Conversation.query.filter_by(driver_id=request.user["user_id"])
             .order_by(Conversation.updated_at.desc()).all())
    return jsonify([c.to_dict(viewer_role="driver") for c in convs])


@driver_bp.route("/conversations", methods=["POST"])
@token_required(["driver"])
def open_conversation():
    """Opens (or returns the existing) conversation for this driver,
    optionally scoped to a specific trip (section 23: trip-specific chat)."""
    data = request.get_json(silent=True) or {}
    driver_id = request.user["user_id"]
    trip_id = data.get("trip_id")
    trip = None
    if trip_id is not None:
        trip = db.get_or_404(Trip, trip_id)
        if trip.driver_id != driver_id:
            raise ForbiddenError("This trip doesn't belong to you.")
        existing = Conversation.query.filter_by(driver_id=driver_id, trip_id=trip.id).first()
        if existing:
            return jsonify(existing.to_dict(viewer_role="driver"))
    else:
        existing = Conversation.query.filter_by(driver_id=driver_id, trip_id=None, status="Open").first()
        if existing:
            return jsonify(existing.to_dict(viewer_role="driver"))

    conv = Conversation(driver_id=driver_id, trip_id=trip.id if trip else None, status="Open")
    db.session.add(conv)
    db.session.commit()
    return jsonify(conv.to_dict(viewer_role="driver")), 201


@driver_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@token_required(["driver"])
def get_conversation_messages(conversation_id):
    conv = _driver_owned_conversation_or_404(conversation_id, request.user["user_id"])
    msgs = Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at.asc()).all()
    return jsonify([m.to_dict() for m in msgs])


@driver_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@token_required(["driver"])
@idempotent(lambda conversation_id: f"chat.message:{conversation_id}")
def send_conversation_message(conversation_id):
    conv = _driver_owned_conversation_or_404(conversation_id, request.user["user_id"])
    data = request.get_json(force=True) or {}
    text = validate_text_length(data.get("message"), "message", MAX_MESSAGE_LEN, required=True)
    if not (text or "").strip():
        raise ValidationError("message cannot be empty.")

    msg = Message(conversation_id=conv.id, sender_id=request.user["user_id"], sender_role="driver",
                  message=text.strip(), is_read=False)
    conv.updated_at = utcnow()
    db.session.add(msg)
    db.session.flush()

    driver = db.session.get(Driver, request.user["user_id"])
    trip = db.session.get(Trip, conv.trip_id) if conv.trip_id else None
    label = f" ({trip.trip_code})" if trip else ""
    notify(
        audience="admin", notif_type="SYSTEM", priority="ACTION",
        title=f"New message from {driver.name}{label}", category="chat",
        message=text.strip()[:200], driver_id=driver.id, trip_id=trip.id if trip else None,
    )
    db.session.commit()
    return jsonify(msg.to_dict()), 201


@driver_bp.route("/conversations/<int:conversation_id>/read", methods=["POST"])
@token_required(["driver"])
def mark_conversation_read(conversation_id):
    conv = _driver_owned_conversation_or_404(conversation_id, request.user["user_id"])
    Message.query.filter_by(conversation_id=conv.id, sender_role="admin", is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "Marked as read."})

"""Reusable input validation helpers.

Every function either returns a cleaned value or raises errors.ValidationError
(400, {"success": false, "error": "...", "code": "VALIDATION_ERROR"}). Routes
call these instead of hand-rolling ad-hoc checks so validation is consistent
across Registration, Vehicle CRUD, Trip CRUD, Prediction, and Admin APIs.
"""
import re
from errors import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Accepts optional leading + and 7-15 digits (E.164-ish), or a plain 10-digit
# local number - broad enough for real-world driver-entered numbers without
# being so loose it accepts garbage.
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,32}$")
# e.g. KA01AB1234 / MH12CD5678 - Indian vehicle registration format, with a
# little slack for spaces/dashes the way people actually type it in.
VEHICLE_NO_RE = re.compile(r"^[A-Z]{2}[- ]?\d{1,2}[- ]?[A-Z]{1,3}[- ]?\d{1,4}$")

VALID_TRIP_STATUSES = {"Planned", "Ongoing", "Completed", "Cancelled"}
VALID_ROLES = {"Admin", "SuperAdmin"}
# Section 9 (Vehicle Restrictions): canonical fuel/vehicle type lists, kept
# in sync with the dropdown options in frontend/src/pages/admin/AdminVehicles.jsx
# - if you add a type there, add it here too, or the backend will reject it.
VALID_FUEL_TYPES = {"Diesel", "Petrol", "CNG", "Electric"}
VALID_VEHICLE_TYPES = {"Van", "Mini Truck", "Truck", "Trailer"}
# Post-Trip Feedback: kept in sync with the dropdown options in
# frontend/src/pages/driver/NewTrip.jsx and the CheckConstraint on
# TripFeedback.experience in models/db.py.
VALID_FEEDBACK_EXPERIENCES = {"Excellent", "Good", "Average", "Poor", "Very Poor"}
FEEDBACK_COMMENTS_MAX_LEN = 1000


def require_fields(data, fields):
    """Raises if any of `fields` is missing or blank in `data` (a dict)."""
    missing = [f for f in fields if data.get(f) in (None, "", [])]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def validate_email(value, field="email"):
    value = (value or "").strip()
    if not value:
        raise ValidationError(f"{field} is required")
    if not EMAIL_RE.match(value):
        raise ValidationError(f"{field} is not a valid email address")
    return value


def validate_phone(value, field="phone"):
    value = (value or "").strip().replace(" ", "")
    if not value:
        raise ValidationError(f"{field} is required")
    if not PHONE_RE.match(value):
        raise ValidationError(f"{field} must be a valid phone number (7-15 digits, optional leading +)")
    return value


def validate_username(value, field="username"):
    value = (value or "").strip()
    if not USERNAME_RE.match(value):
        raise ValidationError(f"{field} must be 3-32 characters: letters, numbers, '.', or '_' only")
    return value


def validate_password(value, field="password", min_len=6):
    if not value or len(value) < min_len:
        raise ValidationError(f"{field} must be at least {min_len} characters")
    return value


def validate_vehicle_no(value, field="vehicle_no"):
    value = (value or "").strip().upper()
    if not value:
        raise ValidationError(f"{field} is required")
    if not VEHICLE_NO_RE.match(value):
        raise ValidationError(f"{field} doesn't look like a valid vehicle registration number (e.g. KA01AB1234)")
    return value


def validate_positive_number(value, field, allow_zero=True, required=True, max_value=None):
    import math
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field} is required")
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number")
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{field} must be a finite number")
    if allow_zero and value < 0:
        raise ValidationError(f"{field} cannot be negative")
    if not allow_zero and value <= 0:
        raise ValidationError(f"{field} must be greater than 0")
    if max_value is not None and value > max_value:
        raise ValidationError(f"{field} is unrealistically large (max {max_value})")
    return value


# Sections 18/19: driver-entered fuel consumed and fuel price at trip end.
# Bounds are deliberately generous (this fleet ranges from bikes to trucks)
# but still reject obvious garbage/typo input (NaN, Infinity, "999999999").
def validate_fuel_liters(value, field="actual_fuel_l", required=True):
    return validate_positive_number(value, field, allow_zero=False, required=required, max_value=2000)


def validate_range(value, field, low, high, required=True):
    """Section 27 (ML Input Validation): validates a numeric field is finite
    and falls within [low, high] - e.g. humidity 0-100. Rejects NaN/Infinity
    same as validate_positive_number."""
    import math
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field} is required")
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number")
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{field} must be a finite number")
    if value < low or value > high:
        raise ValidationError(f"{field} must be between {low} and {high}")
    return value


def validate_fuel_price(value, field="actual_fuel_price", required=True):
    return validate_positive_number(value, field, allow_zero=False, required=required, max_value=500)


def validate_lat_lng(lat, lng):
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        raise ValidationError("lat and lng must be valid numbers")
    if not (-90 <= lat <= 90):
        raise ValidationError("lat must be between -90 and 90")
    if not (-180 <= lng <= 180):
        raise ValidationError("lng must be between -180 and 180")
    return lat, lng


def validate_trip_status(value, field="status"):
    value = (value or "").strip()
    if value not in VALID_TRIP_STATUSES:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(VALID_TRIP_STATUSES))}")
    return value


def validate_choice(value, choices, field):
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(choices))}")
    return value


def validate_capacity_kg(value, field="capacity_kg"):
    return validate_positive_number(value, field, allow_zero=False, required=True)


def validate_rating(value, field):
    """Post-Trip Feedback: an integer 1-5 star rating. Required — a missing
    or blank value is rejected the same as an out-of-range one, rather than
    silently defaulting."""
    if value is None or value == "":
        raise ValidationError(f"{field} is required")
    try:
        # Reject "4.5"/True/etc. masquerading as an int the way bool would
        # otherwise slip through (bool is an int subclass in Python).
        if isinstance(value, bool):
            raise ValueError
        int_value = int(value)
        if float(value) != int_value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number between 1 and 5")
    if int_value < 1 or int_value > 5:
        raise ValidationError(f"{field} must be between 1 and 5")
    return int_value


def validate_text_length(value, field, max_len, required=False):
    if value is None:
        if required:
            raise ValidationError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{field} is required")
    if len(value) > max_len:
        raise ValidationError(f"{field} must be {max_len} characters or fewer")
    return value or None

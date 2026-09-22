import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "carbon_logistics.db")
    )
    # Some hosts (old Heroku-style) hand out "postgres://", but SQLAlchemy
    # 1.4+/2.x requires the "postgresql://" scheme - normalize it so
    # DATABASE_URL works either way instead of failing at connect time.
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    GOOGLE_ROUTES_API_KEY = os.getenv("GOOGLE_ROUTES_API_KEY", "")
    GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8MB

    # Comma-separated list of allowed browser origins for the production
    # frontend, e.g. "https://app.example.com,https://admin.example.com".
    # Left unset (empty) in local dev, where app.py falls back to allowing
    # localhost dev-server origins only - never "*" for an authenticated API.
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

    # ---- Section 15/17 (5km Destination Lock) ----
    # Arrival radius: a trip can only be ended once the driver's most recent
    # GPS fix is within this many meters of the trip's destination
    # coordinates. Configurable via env var rather than hardcoded in
    # multiple places (frontend also reads this from GET /api/v1/config).
    DESTINATION_ARRIVAL_RADIUS_M = int(os.getenv("DESTINATION_ARRIVAL_RADIUS_M", "5000"))

    # Section 16 (GPS Accuracy): a GPS fix whose reported accuracy circle is
    # wider than this (in meters) is not trusted to verify arrival - either
    # because the browser reported no accuracy at all, or because it reported
    # one worse than this threshold. Kept generous enough for ordinary phone
    # GPS in light urban cover while still rejecting genuinely unreliable fixes.
    GPS_ACCURACY_THRESHOLD_M = float(os.getenv("GPS_ACCURACY_THRESHOLD_M", "200"))


class TestConfig(Config):
    """Used by the pytest suite (backend/tests/) - isolated in-memory
    database per test run, CSRF/scheduler concerns out of scope, short JWT
    expiry doesn't matter since tests mint fresh tokens as needed."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory, wiped every process
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "test_uploads")

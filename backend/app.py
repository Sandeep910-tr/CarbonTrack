import os
import uuid
import json
import time
import logging
from flask import Flask, jsonify, send_from_directory, request, g
from flask_cors import CORS
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from models.db import db, utcnow
from errors import register_error_handlers
from extensions import limiter

from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.driver import driver_bp
from routes.trips import trips_bp
from routes.external import external_bp

STATIC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_scheduler = None

class _RequestIdFilter(logging.Filter):
    """Injects the current request's trace ID (see _assign_request_id below)
    into every log record so a log line can be matched back to the request
    that produced it. Falls back to "-" for log lines emitted outside a
    request context (startup, scheduled jobs)."""
    def filter(self, record):
        try:
            from flask import g, has_request_context
            record.request_id = g.request_id if has_request_context() and hasattr(g, "request_id") else "-"
        except Exception:
            record.request_id = "-"
        return True


class _JsonFormatter(logging.Formatter):
    """Section 41 (Logging): structured, machine-parseable log lines for
    production log aggregation (CloudWatch/Datadog/ELK/etc). One JSON object
    per line - never includes secrets (this only formats whatever message
    the calling code already passed to logging.*, so the same "never log
    passwords/JWTs/API keys" discipline that applies to log call sites
    elsewhere in this codebase still applies here; this formatter doesn't
    add anything new to the payload beyond level/time/request_id/logger).
    Opt in with LOG_FORMAT=json; human-readable text (the default) is easier
    to read locally during development."""
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s [req:%(request_id)s]: %(message)s",
)
# IMPORTANT: the filter must be attached to the HANDLER, not the root
# Logger. A Filter attached to a Logger object only runs for records
# emitted directly on THAT logger - it is skipped for records that
# propagate up from a child logger (e.g. current_app.logger, or any
# module-level logging.getLogger("carbontrack.access") call), which is
# almost every log line in this app. Attaching to the root handler instead
# means every record that reaches this handler gets request_id injected,
# regardless of which logger it came from.
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_RequestIdFilter())
if os.getenv("LOG_FORMAT", "").lower() == "json":
    for _handler in logging.getLogger().handlers:
        _handler.setFormatter(_JsonFormatter())


def create_app(config_object=None):
    # static_folder=None disables Flask's built-in static route (which would
    # otherwise 404 client-side routes like /admin/drivers before our
    # catch-all below gets a chance to serve index.html for them).
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object or Config)

    # ---- CORS: explicit origins in production, never "*" for an authenticated API ----
    # CORS_ORIGINS (comma-separated env var) drives this in production. In
    # local dev (nothing set) we fall back to the Vite/CRA dev-server ports
    # so `npm run dev` keeps working without extra setup, but production
    # deploys MUST set CORS_ORIGINS or every browser request will be blocked
    # (fails closed, not open).
    allowed_origins = app.config.get("CORS_ORIGINS") or []
    if not allowed_origins and app.config.get("DEV_MODE", True):
        allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173",
                            "http://localhost:3000", "http://127.0.0.1:3000"]
    # Section: CSRF review. This API uses JWT Bearer tokens in the
    # Authorization header (see frontend/src/lib/api.js), never cookies -
    # the browser has no ambient credential to attach automatically to a
    # cross-site request, which is the entire mechanism CSRF exploits. A
    # malicious page cannot forge a request that carries this app's token
    # unless it can already read localStorage (i.e. unless it's already
    # achieved XSS, which is a different threat model with its own
    # mitigation: the CSP header below). Consequently supports_credentials
    # is explicitly OFF - this app never needs the browser to send/receive
    # cookies cross-origin, and leaving it on would be unnecessary attack
    # surface for zero functional benefit. See HARDENING_CHANGELOG.md for
    # the full written review.
    CORS(app, origins=allowed_origins, supports_credentials=False)

    db.init_app(app)
    limiter.init_app(app)
    Migrate(app, db)

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(driver_bp, url_prefix="/api/v1/driver")
    app.register_blueprint(trips_bp, url_prefix="/api/v1/trips")
    app.register_blueprint(external_bp, url_prefix="/api/v1/external")

    # Centralized error handling (backend/errors.py) - every /api/* error,
    # whether it's a raised AppError subclass, a DB integrity error, a bad
    # JWT, a 404, or an uncaught bug, comes back as
    # {"success": false, "error": "...", "code": "..."} instead of an HTML
    # error page or an inconsistent ad-hoc shape.
    register_error_handlers(app)

    # ---- Request ID: every request gets a trace ID, echoed back in the
    # response and included on every log line for that request, so a user-
    # reported error can be matched to the exact backend log entry. ----
    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        g._request_start_time = time.monotonic()

    request_logger = logging.getLogger("carbontrack.access")

    @app.after_request
    def _log_request(resp):
        # Section 41 (Logging): one line per request with the fields the
        # spec asks for (timestamp/level/request-id come from the logging
        # config itself; this adds endpoint/status/duration). Health-check
        # polling is excluded so it doesn't drown out real traffic in the logs.
        if request.path not in ("/api/health", "/api/ready"):
            duration_ms = round((time.monotonic() - getattr(g, "_request_start_time", time.monotonic())) * 1000, 1)
            request_logger.info(
                "%s %s -> %s (%sms)",
                request.method, request.path, resp.status_code, duration_ms,
            )
        return resp

    @app.after_request
    def _security_headers(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        # Defense-in-depth headers. CSP allows Google Maps/Places/Fonts (the
        # app embeds the Maps JS API + tiles) and 'unsafe-inline' for styles
        # only, which the current build relies on for CSS-in-JS/Tailwind.
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        if not app.config.get("DEV_MODE", True):
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://maps.googleapis.com 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https://*.googleapis.com https://*.gstatic.com https://*.ggpht.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "connect-src 'self' https://maps.googleapis.com https://*.google.com; "
                "frame-ancestors 'none'"
            )
        return resp

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "Carbon Footprint Logistics API"})

    @app.route("/api/ready")
    def ready():
        """Readiness probe: unlike /api/health (process is up), this checks the
        app can actually serve traffic - i.e. the database is reachable."""
        try:
            from sqlalchemy import text
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "ready"})
        except Exception:
            logging.getLogger("carbontrack").exception("Readiness check failed")
            return jsonify({"status": "not_ready"}), 503

    # ---- Serve the React production build for every non-API route ----
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react(path):
        if path.startswith("api/"):
            # No blueprint route matched this /api/* path - a genuine 404,
            # not a client-side route. Return JSON instead of falling
            # through to index.html so the frontend gets a parseable error.
            return jsonify({"success": False, "error": "Endpoint not found", "code": "NOT_FOUND"}), 404
        full_path = os.path.join(STATIC_FOLDER, path)
        if path == "sw.js":
            # The service worker script itself must never be served from the
            # browser's HTTP cache: it can be same-content-length as an old
            # version (Flask's default caching only revalidates via ETag/
            # Last-Modified) and any delay in the browser noticing a change
            # here means it keeps running old fetch-handling logic — the
            # exact "stuck on a stale service worker" symptom.
            resp = send_from_directory(STATIC_FOLDER, path)
            resp.headers["Cache-Control"] = "no-cache"
            return resp
        if path and os.path.isfile(full_path):
            return send_from_directory(STATIC_FOLDER, path)
        return send_from_directory(STATIC_FOLDER, "index.html")

    with app.app_context():
        # Section 34: "Do not modify production schema randomly at
        # application startup." The lightweight _auto_migrate() below is a
        # dev-convenience shim (so `python app.py` + SQLite "just works"
        # without an extra migration step while iterating locally) - it is
        # NOT a substitute for real migrations in production. Production
        # deploys must run `flask db upgrade` (Alembic, see backend/migrations/)
        # as a separate release step; this block only runs schema changes
        # automatically when DEV_MODE=true, or if AUTO_MIGRATE=true is set
        # explicitly (e.g. a single-instance deploy that intentionally wants
        # the old behavior).
        if app.config.get("DEV_MODE", True) or os.getenv("AUTO_MIGRATE", "").lower() == "true":
            db.create_all()
            _auto_migrate()
        try:
            if os.getenv("SEED_DEFAULT_SETTINGS", "true").lower() == "true":
                _seed_default_settings()
        except Exception as exc:
            # Don't re-raise for a missing-table error. Re-raising here would
            # crash create_app() itself, and since `app = create_app()` runs
            # at import time (line ~477), that means the app module can
            # never be imported until the tables already exist - including
            # by `flask db upgrade`/`flask db migrate`, whose whole job is to
            # create those tables in the first place. That chicken-and-egg
            # made first-time setup with DEV_MODE=false impossible: you
            # couldn't run migrations because loading the app to run them
            # crashed first. A missing table is expected on a genuinely
            # fresh deploy before migrations have run, so just log and let
            # startup continue; requests that need Settings will error
            # until migrations are applied, but the process (and the
            # `flask db upgrade` command) stays usable. Any other kind of
            # error (bad DATABASE_URL, DB unreachable, etc.) still raises
            # in production, same as before.
            is_missing_table = "no such table" in str(exc).lower() or "does not exist" in str(exc).lower()
            if is_missing_table:
                # Expected on first-time setup (table doesn't exist yet on
                # this call - create_all()/migrations will create it a
                # moment later). One quiet line instead of a full traceback.
                logging.getLogger("carbontrack").warning(
                    "Settings table not ready yet (expected on first-time "
                    "setup) - will retry once migrations/create_all have run."
                )
            else:
                logging.getLogger("carbontrack").exception(
                    "Could not seed default settings - if this is a production "
                    "deploy, make sure you've run 'flask db upgrade' before "
                    "starting the app."
                )
            if not app.config.get("DEV_MODE", True) and not is_missing_table:
                raise

    _start_scheduler(app)
    _warm_place_index(app)

    return app


def _auto_migrate():
    """db.create_all() only creates tables that don't exist yet — it silently
    skips adding new columns to tables that already exist (e.g. an existing
    carbon_logistics.db from before a model change). That's fine for a brand
    new database, but breaks every deploy that already has data. This adds
    any columns present in the models but missing from the actual SQLite
    table, so schema changes don't require dropping the database. It also
    creates any indexes declared on the models (via index=True or
    __table_args__) that don't exist yet on tables that were created before
    those indexes were added — SQLite has no "ALTER TABLE ADD INDEX", so
    these have to be created explicitly with CREATE INDEX IF NOT EXISTS.

    Note: SQLite also has no "ALTER TABLE ADD CONSTRAINT", so CHECK
    constraints declared on models (e.g. Trip/Vehicle __table_args__) only
    take effect on brand-new tables. On a database that already exists,
    those same rules are enforced at the API layer instead (see
    backend/validators.py) — every write endpoint that touches those
    columns validates them before the row is saved, so the guarantee holds
    either way, it's just enforced in Python instead of by SQLite for
    pre-existing tables."""
    from sqlalchemy import inspect, text
    engine = db.engine
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table — create_all() already built it correctly
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            col_type = col.type.compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'))
            print(f"[auto-migrate] added column {table.name}.{col.name} ({col_type})")

        # One-off cleanup: OTP hardening replaced the plaintext `code` column
        # with `code_hash`. On a database created before that change, `code`
        # is still there with a NOT NULL constraint, which would break every
        # new OTP insert (the app no longer writes to that column). SQLite
        # 3.35+ supports DROP COLUMN directly; older SQLite falls back to
        # silently leaving the column in place; it isn't harmful, just
        # dead - see README migration notes for the manual rebuild if needed.
        if table.name == "otps" and "code" in existing_cols and "code_hash" in existing_cols:
            try:
                with engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "otps" DROP COLUMN "code"'))
                print("[auto-migrate] dropped legacy otps.code column")
            except Exception as e:
                print(f"[auto-migrate] could not drop legacy otps.code column automatically ({e}); "
                      f"if OTP requests start failing with a NOT NULL error, drop that column manually.")

        existing_indexes = {ix["name"] for ix in inspector.get_indexes(table.name)}
        for col in table.columns:
            if not col.index:
                continue
            idx_name = f"ix_{table.name}_{col.name}"
            if idx_name in existing_indexes:
                continue
            with engine.begin() as conn:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table.name}" ("{col.name}")'))
            print(f"[auto-migrate] added index {idx_name} on {table.name}.{col.name}")

        # Table-level Index objects declared in __table_args__ (e.g. the
        # partial-unique "one Ongoing trip per driver" index) aren't covered
        # by the column-level loop above, since they aren't attached to a
        # single db.Column(index=True). Create any that are missing on a
        # pre-existing table the same way create_all() would on a fresh one.
        for idx in table.indexes:
            if idx.name in existing_indexes:
                continue
            try:
                idx.create(bind=engine, checkfirst=True)
                print(f"[auto-migrate] added index {idx.name} on {table.name}")
            except Exception as e:
                print(f"[auto-migrate] could not create index {idx.name} on {table.name} ({e}); "
                      f"if existing data already violates it (e.g. a driver with two Ongoing trips), "
                      f"resolve that data first, then restart.")


def _seed_default_settings():
    from models.db import Settings
    from routes.admin import DEFAULT_SETTINGS
    for key, value in DEFAULT_SETTINGS.items():
        if not Settings.query.filter_by(key=key).first():
            db.session.add(Settings(key=key, value=value))
    _seed_default_carbon_methodology()
    db.session.commit()


def _seed_default_carbon_methodology():
    """Section 21: on a fresh database (or one upgrading from before this
    table existed), seed exactly one active CarbonMethodology row from the
    current ml/data_formulas.py constants, so end_trip always has an active
    methodology to compute against. A no-op if any methodology already
    exists - this never overwrites an existing row, since doing so would
    defeat the entire point of versioning (see CarbonMethodology docstring)."""
    from models.db import CarbonMethodology
    from ml.data_formulas import EMISSION_FACTOR, PRICE_PER_UNIT
    if CarbonMethodology.query.first() is not None:
        return
    db.session.add(CarbonMethodology(
        version_label="v1.0",
        effective_date=utcnow().date(),
        emission_factors=json.dumps(EMISSION_FACTOR),
        price_per_unit=json.dumps(PRICE_PER_UNIT),
        notes="Initial methodology, seeded automatically from ml/data_formulas.py.",
        is_active=True,
    ))


def _warm_place_index(app):
    """Builds the pickup/destination autocomplete index (geo_search.py,
    ~605k rows) in a background thread right away, instead of lazily on
    whichever driver's keystroke happens to trigger it first - that first
    build takes a couple of seconds, which would otherwise show up as a
    one-off delay on someone's New Trip form."""
    if app.config.get("TESTING") or os.getenv("DISABLE_PLACE_INDEX_WARMUP", "false").lower() == "true":
        return
    import threading
    from geo_search import _get_index

    threading.Thread(target=_get_index, daemon=True).start()


def _start_scheduler(app):
    """Continuous Learning Pipeline (Section E) + AI Daily Report (Section H/I).
    Runs inside the same process as the Flask app - fine for a single-instance
    deployment; move to a proper task queue (Celery/RQ) if you scale to multiple
    workers, since APScheduler jobs would otherwise fire once per worker.

    Guard: Flask's debug reloader (active when DEV_MODE=true) spawns a child
    process and re-imports this module in both the parent monitor and the child.
    Werkzeug sets WERKZEUG_RUN_MAIN=true only in the child that actually serves
    requests, so we only start the scheduler there to avoid running it twice."""
    global _scheduler
    dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if dev_mode and not is_reloader_child:
        return
    if _scheduler is not None or os.getenv("DISABLE_SCHEDULER", "false").lower() == "true":
        return
    _scheduler = BackgroundScheduler(daemon=True)

    def scheduled_retrain():
        with app.app_context():
            from models.db import ModelRun
            from ml.pipeline import run_training_pipeline
            from notifications import notify
            import json as _json
            run = ModelRun(triggered_by="scheduled", status="running")
            db.session.add(run)
            db.session.commit()
            try:
                metrics, n_rows = run_training_pipeline()
                run.status, run.metrics_json, run.training_rows = "success", _json.dumps(metrics), n_rows
                notify(
                    audience="admin", notif_type="SYSTEM", priority="INFO",
                    title="Model training completed", category="ml_training",
                    message=f"Scheduled retraining completed on {n_rows} rows.",
                )
            except Exception as e:
                run.status, run.metrics_json = "failed", _json.dumps({"error": str(e)})
                notify(
                    audience="admin", notif_type="SYSTEM", priority="CRITICAL",
                    title="Model training failed", category="ml_training",
                    message=f"Scheduled retraining failed: {e}",
                )
            run.finished_at = utcnow()
            db.session.commit()

    def scheduled_daily_report():
        with app.app_context():
            from models.db import Trip
            from notifications import notify
            from datetime import timedelta
            start = (utcnow() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            trips = Trip.query.filter(Trip.created_at >= start, Trip.created_at < end, Trip.status == "Completed").all()
            total_co2 = sum(t.actual_co2_kg or 0 for t in trips)
            notify(
                audience="admin", notif_type="SYSTEM", priority="INFO",
                title="Daily fleet report", category="daily_report",
                message=f"Daily report for {start.strftime('%Y-%m-%d')}: {len(trips)} trips completed, {round(total_co2,1)} kg CO2 emitted.",
                dedup_key=f"daily_report:{start.strftime('%Y-%m-%d')}", cooldown_minutes=60 * 20,
            )
            db.session.commit()

    def scheduled_document_expiry_check():
        """Vehicle document expiry tracking: warns 30 days out, escalates once a
        document has actually lapsed. One notification per vehicle+document+day
        avoids re-alerting on every run within the same day."""
        with app.app_context():
            from models.db import Vehicle
            from notifications import notify
            from datetime import timedelta
            today = utcnow().date()
            soon = today + timedelta(days=30)
            docs = [
                ("insurance_expiry", "Insurance"),
                ("permit_expiry", "Permit"),
                ("pollution_cert_expiry", "Pollution certificate"),
            ]
            for v in Vehicle.query.all():
                for field, label in docs:
                    expiry = getattr(v, field)
                    if not expiry:
                        continue
                    if expiry < today:
                        msg = f"{label} for {v.vehicle_no} expired on {expiry.isoformat()}."
                        priority = "CRITICAL"
                    elif expiry <= soon:
                        msg = f"{label} for {v.vehicle_no} expires on {expiry.isoformat()} — renew soon."
                        priority = "WARNING"
                    else:
                        continue
                    notify(
                        audience="admin", notif_type="VEHICLE", priority=priority,
                        title=f"{label} expiry", category="document_expiry", message=msg,
                        vehicle_id=v.id, dedup_key=f"document_expiry:{v.id}:{field}:{expiry.isoformat()}",
                        cooldown_minutes=60 * 20,
                    )
            db.session.commit()

    def scheduled_carbon_budget_check():
        """Carbon budget caps: compares total (all-time) actual CO2 against the
        admin-configured target — same cumulative metric already shown on the
        Sustainability Dashboard — and alerts once usage crosses 90%/100%."""
        with app.app_context():
            from models.db import Trip, Settings
            from notifications import notify
            from sqlalchemy import func as _func
            row = Settings.query.filter_by(key="carbon_budget_target_kg").first()
            target = float(row.value) if row and row.value else 0
            if target <= 0:
                return
            used = db.session.query(_func.coalesce(_func.sum(Trip.actual_co2_kg), 0.0)).scalar()
            pct = (used / target) * 100
            if pct >= 100:
                msg = f"Carbon budget exceeded: {round(used)} kg used of {round(target)} kg target."
                priority, tier = "CRITICAL", "exceeded"
            elif pct >= 80:
                msg = f"Carbon budget at {round(pct)}%: {round(used)} kg used of {round(target)} kg target."
                priority, tier = "WARNING", "80pct"
            else:
                return
            notify(
                audience="admin", notif_type="CARBON", priority=priority,
                title="Carbon budget alert", category="carbon_budget", message=msg,
                dedup_key=f"carbon_budget:{tier}", cooldown_minutes=60 * 20,
            )
            db.session.commit()

    _scheduler.add_job(scheduled_retrain, "interval", hours=24, id="daily_retrain")
    _scheduler.add_job(scheduled_daily_report, "interval", hours=24, id="daily_report")
    _scheduler.add_job(scheduled_document_expiry_check, "interval", hours=24, id="document_expiry_check")
    _scheduler.add_job(scheduled_carbon_budget_check, "interval", hours=24, id="carbon_budget_check")
    _scheduler.start()


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEV_MODE", "true").lower() == "true")

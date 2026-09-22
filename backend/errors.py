"""Centralized error handling.

Gives every error path in the app (validation failures, missing records,
auth problems, DB errors, ML errors, uncaught bugs) one consistent JSON
shape on /api/* routes:

    {"success": false, "error": "<human message>", "code": "<MACHINE_CODE>"}

`error` is kept as a plain string (not a nested object) on purpose: the
existing frontend already reads `err.response.data.error` as a string
everywhere (Login, Register, NewTrip, AdminAdmins, AdminSettings, ...).
Nesting it would silently break every one of those error messages. `code`
is additive, so old and new code both keep working.

Existing routes that already do `return jsonify({"error": "..."}), 400`
keep working unchanged - this module doesn't require touching them. New/
updated routes can instead `raise ValidationError("...")` and get the same
shape for free, plus centralized logging.
"""
import logging
from flask import jsonify, request

logger = logging.getLogger("carbontrack")


class AppError(Exception):
    """Base class for application errors that should become a clean JSON
    response instead of a raw 500 with a traceback leaking to the client."""
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message, status_code=None, code=None, payload=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.payload = payload or {}

    def to_dict(self):
        body = {"success": False, "error": self.message, "code": self.code}
        body.update(self.payload)
        return body


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class DatabaseError(AppError):
    status_code = 500
    code = "DATABASE_ERROR"


class MLError(AppError):
    status_code = 500
    code = "ML_ERROR"


def register_error_handlers(app):
    from werkzeug.exceptions import HTTPException
    import jwt as pyjwt
    try:
        from sqlalchemy.exc import SQLAlchemyError, IntegrityError
    except ImportError:  # pragma: no cover
        SQLAlchemyError = IntegrityError = Exception

    def _json_error(message, status_code, code, extra=None):
        body = {"success": False, "error": message, "code": code}
        if extra:
            body.update(extra)
        return jsonify(body), status_code

    @app.errorhandler(AppError)
    def handle_app_error(e):
        if e.status_code >= 500:
            logger.exception("AppError: %s", e.message)
        return jsonify(e.to_dict()), e.status_code

    @app.errorhandler(pyjwt.ExpiredSignatureError)
    def handle_jwt_expired(e):
        return _json_error("Token expired", 401, "TOKEN_EXPIRED")

    @app.errorhandler(pyjwt.InvalidTokenError)
    def handle_jwt_invalid(e):
        return _json_error("Invalid token", 401, "TOKEN_INVALID")

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        try:
            from models.db import db
            db.session.rollback()
        except Exception:
            pass
        logger.warning("IntegrityError: %s", str(getattr(e, "orig", e)))
        return _json_error(
            "That value conflicts with an existing record (duplicate or invalid reference).",
            409, "INTEGRITY_ERROR",
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(e):
        try:
            from models.db import db
            db.session.rollback()
        except Exception:
            pass
        logger.exception("Database error")
        return _json_error("A database error occurred. Please try again.", 500, "DATABASE_ERROR")

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        if not request.path.startswith("/api/"):
            return e  # let the SPA catch-all / static handling behave as before
        code_map = {
            400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
            404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE",
            429: "RATE_LIMITED",
        }
        return _json_error(e.description or e.name, e.code, code_map.get(e.code, "HTTP_ERROR"))

    @app.errorhandler(Exception)
    def handle_uncaught_error(e):
        """Ensures /api/* routes always return JSON on a crash instead of Flask's
        default HTML error page, which the frontend can't parse for a useful
        message. Non-API routes (the SPA) keep default behavior.

        In DEV_MODE, the full traceback is included in the JSON response itself
        (and therefore shows up in the browser console) - convenient for local
        development, but DEV_MODE must be set to false before any real deploy."""
        import os
        import traceback
        if not request.path.startswith("/api/"):
            raise e
        tb_string = traceback.format_exc()
        logger.exception("Unhandled exception")
        dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
        body = {
            "success": False,
            "error": "Internal server error - check the backend console/log for the full traceback.",
            "code": "INTERNAL_ERROR",
        }
        if dev_mode:
            body["traceback"] = tb_string
        return jsonify(body), 500

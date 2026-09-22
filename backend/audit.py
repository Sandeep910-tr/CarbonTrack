"""Section 38 (Audit Logs) helper.

Call log_audit(...) from a route handler right before (or as part of) the
same db.session.commit() that performs the action being logged. This does
NOT commit on its own - it just adds the row to the session - so it
naturally becomes part of the same transaction as the action it's recording
(if the action rolls back, so does its audit entry).

NEVER pass passwords, JWTs, API keys, or other secrets in `details`.
"""
import json
from flask import request, g
from models.db import db, AuditLog


def log_audit(actor_type, actor_id, actor_name, action, resource_type=None, resource_id=None, details=None):
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details else None,
        request_id=getattr(g, "request_id", None),
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    db.session.add(entry)
    return entry


def log_admin_action(action, resource_type=None, resource_id=None, details=None):
    """Convenience wrapper for routes protected by @token_required(["admin"]) -
    reads the actor off request.user (set by the auth decorator)."""
    user = getattr(request, "user", {}) or {}
    return log_audit("admin", user.get("user_id"), user.get("name"), action, resource_type, resource_id, details)


def log_driver_action(action, resource_type=None, resource_id=None, details=None):
    """Convenience wrapper for routes protected by @token_required(["driver"])."""
    user = getattr(request, "user", {}) or {}
    return log_audit("driver", user.get("user_id"), user.get("name"), action, resource_type, resource_id, details)

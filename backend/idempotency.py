"""Section 23 (Duplicate Request Protection): opt-in idempotency for
Create/Start/End Trip.

A client sends an `Idempotency-Key` header (any client-generated unique
string - typically a UUID minted once per user action, e.g. once per
button-press, and reused across retries of that same action). The first
request for a given (key, scope, actor) triggers the real handler and its
response is cached; any retry with the same key - a double-click, the same
action open in two tabs, a mobile network layer retrying a timed-out
request - replays the ORIGINAL response instead of running the action again.

Requests without the header are unaffected (idempotency is opt-in, matching
the common REST convention used by Stripe/GitHub/etc., since not every
client can be assumed to send one).
"""
import json
from functools import wraps
from flask import request, jsonify
from models.db import db, IdempotencyRecord

MAX_KEY_LENGTH = 128


def idempotent(scope):
    """Decorate a Flask route (must run AFTER @token_required, so
    request.user is already populated) to make it safe to retry.

    `scope` may be a plain string ("trip.create") or a callable that
    receives the wrapped view's own (*args, **kwargs) and returns a scope
    string - use the latter for routes keyed by a resource id (e.g.
    /trips/<trip_id>/start) so the SAME idempotency key reused by a client
    across two different trips doesn't collide; scope becomes
    "trip.start:42" rather than a bare "trip.start".

    Concurrency note: the actual safety net against two SIMULTANEOUS
    duplicate requests for the same key is the database's unique constraint
    on (key, scope, actor_id) - see models/db.py:IdempotencyRecord. If two
    requests race, the loser's INSERT raises IntegrityError; we catch that
    and tell the client to retry rather than risk replaying a response that
    doesn't exist yet.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return fn(*args, **kwargs)
            key = key.strip()[:MAX_KEY_LENGTH]
            if not key:
                return fn(*args, **kwargs)

            resolved_scope = scope(*args, **kwargs) if callable(scope) else scope
            actor_id = (getattr(request, "user", None) or {}).get("user_id")
            existing = IdempotencyRecord.query.filter_by(key=key, scope=resolved_scope, actor_id=actor_id).first()
            if existing is not None:
                if existing.response_body is None:
                    # This key was claimed by another (still in-flight)
                    # request - status_code/response_body only get filled
                    # in AFTER that request's handler finishes (see below).
                    # Returning a synthesized response here would mean
                    # replaying a result that doesn't exist yet; tell the
                    # client to retry instead, same as the concurrent-INSERT
                    # race case just below.
                    return jsonify({
                        "success": False,
                        "error": "This request is already being processed. Please wait and check the result "
                                 "rather than resubmitting.",
                        "code": "IDEMPOTENT_REQUEST_IN_PROGRESS",
                    }), 409
                body = json.loads(existing.response_body)
                resp = jsonify(body)
                resp.status_code = existing.status_code or 200
                resp.headers["Idempotent-Replay"] = "true"
                return resp

            # Claim the key up front (before running the handler) so a
            # second request that arrives while the first is still in
            # flight fails fast on the unique constraint instead of also
            # running the action.
            placeholder = IdempotencyRecord(key=key, scope=resolved_scope, actor_id=actor_id, status_code=None, response_body=None)
            db.session.add(placeholder)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                return jsonify({
                    "success": False,
                    "error": "This request is already being processed. Please wait and check the result "
                             "rather than resubmitting.",
                    "code": "IDEMPOTENT_REQUEST_IN_PROGRESS",
                }), 409

            try:
                result = fn(*args, **kwargs)
                # Normalize into (body_dict, status_code) whether the route
                # returned a bare Response (implicit 200) or a
                # (Response, status) tuple - Flask only applies the tuple's
                # status to response.status_code once ITS dispatcher
                # unwraps the tuple, which hasn't happened yet at this
                # point since we called fn() directly ourselves.
                if isinstance(result, tuple):
                    resp_obj, status = result[0], result[1]
                else:
                    resp_obj, status = result, getattr(result, "status_code", 200)
                body = resp_obj.get_json() if hasattr(resp_obj, "get_json") else resp_obj

                placeholder.status_code = status
                placeholder.response_body = json.dumps(body)
                db.session.commit()
                return result
            except Exception:
                # The handler failed (validation error, etc.) - don't leave
                # a dangling claimed key that would block every future
                # legitimate retry with this same key forever.
                db.session.delete(placeholder)
                db.session.commit()
                raise
        return wrapper
    return decorator

"""Shared Flask extension instances.

Kept in their own module (rather than instantiated in app.py) so route
blueprints can `from extensions import limiter` and decorate individual
endpoints with `@limiter.limit(...)` without creating a circular import
between app.py and routes/*.py.
"""
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Storage backend: in-memory by default (fine for a single-process/single-
# worker deploy, which is what this app already assumes elsewhere - see
# app.py's APScheduler WERKZEUG_RUN_MAIN guard). Point RATELIMIT_STORAGE_URI
# at Redis (e.g. "redis://localhost:6379") for a multi-worker deployment,
# since in-memory limits are per-process and won't be shared across workers.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    default_limits=[],  # no blanket default - each sensitive route sets its own
    headers_enabled=True,  # adds X-RateLimit-* response headers
    swallow_errors=True,  # if the storage backend is briefly unavailable, fail OPEN (don't 500 every request)
)

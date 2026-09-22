import bcrypt
import jwt
import random
import string
from datetime import timedelta
from functools import wraps
from flask import request, jsonify, current_app
from models.db import utcnow


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def generate_token(user_id, role, extra=None):
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": utcnow() + timedelta(hours=12),
        "iat": utcnow(),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def decode_token(token):
    return jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])


def super_admin_required(f):
    """Restricts a route to admins whose JWT carries admin_role == SuperAdmin.
    Must be stacked under @token_required(["admin"])."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if request.user.get("admin_role") != "SuperAdmin":
            return jsonify({"error": "Forbidden - requires SuperAdmin role"}), 403
        return f(*args, **kwargs)
    return wrapped


def generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


def token_required(roles=None):
    """Decorator - validates the Bearer JWT and optionally restricts by role."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing or invalid Authorization header"}), 401
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            if roles and payload.get("role") not in roles:
                return jsonify({"error": "Forbidden - insufficient role"}), 403

            request.user = payload
            return f(*args, **kwargs)
        return wrapped
    return decorator

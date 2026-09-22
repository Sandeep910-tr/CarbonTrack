import os
import smtplib
from email.mime.text import MIMEText
from datetime import timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models.db import db, Admin, Driver, OTP, Notification, utcnow
from routes.auth_utils import hash_password, check_password, generate_token, generate_otp
from errors import ConflictError
from validators import validate_email, validate_phone, validate_username, validate_password
from notifications import notify
from extensions import limiter

auth_bp = Blueprint("auth", __name__)

# Section 4 (brute-force protection): PER-ACCOUNT lockout, layered on top of
# the IP-based rate limit on this endpoint. IP rate limiting alone doesn't
# stop a distributed attempt (many IPs, one target account) - this does,
# because it's keyed by the account, not the caller's address.
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _lockout_response(account):
    """Returns a (response, status) tuple if `account` is currently locked, else None."""
    if account.locked_until and account.locked_until > utcnow():
        remaining_min = max(1, int((account.locked_until - utcnow()).total_seconds() // 60) + 1)
        return jsonify({
            "error": f"Too many failed login attempts. Try again in about {remaining_min} minute(s).",
            "code": "ACCOUNT_LOCKED",
        }), 423
    return None


def _register_failed_attempt(account):
    account.failed_login_attempts = (account.failed_login_attempts or 0) + 1
    if account.failed_login_attempts >= LOCKOUT_THRESHOLD:
        account.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
    db.session.commit()


def _register_successful_login(account):
    if account.failed_login_attempts or account.locked_until:
        account.failed_login_attempts = 0
        account.locked_until = None
        db.session.commit()

# ---------------------------------------------------------- OTP tuning
# Email-only: no SMS provider is wired up in this build (no SMS API key was
# supplied), so phone-based OTP delivery is not offered - see README.
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_REQUEST_COOLDOWN_SECONDS = 60


def try_send_email(to_address, subject, body):
    """Sends via SMTP if SMTP_HOST/SMTP_USER/SMTP_PASSWORD are set in .env.
    Returns True if actually sent, False if it fell back to dev mode (no error raised)."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", 587))
    if not (host and user and password):
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_address
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_address], msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP] Failed to send email to {to_address}: {e}")
        return False


# ---------------------------------------------------------------- LOGIN
@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10/minute")  # Section 4: brute-force protection
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    admin = Admin.query.filter_by(username=username).first()
    if admin:
        locked = _lockout_response(admin)
        if locked:
            return locked
        if check_password(password, admin.password_hash):
            if admin.status != "Active":
                return jsonify({"error": "This admin account has been deactivated."}), 403
            _register_successful_login(admin)
            token = generate_token(admin.id, "admin", {"name": admin.name, "admin_role": admin.role})
            return jsonify({
                "token": token, "role": "admin",
                "user": {"id": admin.id, "name": admin.name, "username": admin.username, "admin_role": admin.role}
            })
        _register_failed_attempt(admin)
        return jsonify({"error": "Invalid credentials"}), 401

    driver = Driver.query.filter_by(username=username).first()
    if driver:
        locked = _lockout_response(driver)
        if locked:
            return locked
        if check_password(password, driver.password_hash):
            if driver.status == "Pending":
                return jsonify({"error": "Your account is awaiting admin approval."}), 403
            if driver.status == "Rejected":
                return jsonify({"error": f"Registration rejected: {driver.rejection_reason or 'contact admin'}"}), 403
            if driver.status == "Blocked":
                return jsonify({"error": "Your account has been blocked. Contact admin."}), 403
            _register_successful_login(driver)
            token = generate_token(driver.id, "driver", {"name": driver.name})
            return jsonify({"token": token, "role": "driver", "user": driver.to_dict()})
        _register_failed_attempt(driver)
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"error": "Invalid credentials"}), 401


# ---------------------------------------------------------- OTP REQUEST
@auth_bp.route("/otp/request", methods=["POST"])
@limiter.limit("5/minute")
def request_otp():
    """Email OTP only. Phone/SMS OTP was removed - this build has no SMS
    provider wired up, and silently accepting a phone number while never
    actually delivering a code would be worse than just not offering it."""
    data = request.get_json(force=True)
    identifier = (data.get("identifier") or "").strip()
    if not identifier:
        return jsonify({"error": "Email is required"}), 400
    if "@" not in identifier:
        return jsonify({"error": "Phone OTP isn't available in this build (no SMS provider configured) — please use email instead."}), 400
    identifier = validate_email(identifier)

    existing = Driver.query.filter(
        (Driver.email == identifier) | (Driver.phone == identifier)
    ).first()
    if existing:
        return jsonify({"error": "An account already exists with this email"}), 409

    # Cooldown: don't let the same identifier trigger unlimited OTP sends
    # (email-bombing / cost abuse), one request per OTP_REQUEST_COOLDOWN_SECONDS.
    recent = OTP.query.filter_by(identifier=identifier, purpose="registration") \
        .order_by(OTP.created_at.desc()).first()
    if recent:
        elapsed = (utcnow() - recent.created_at).total_seconds()
        if elapsed < OTP_REQUEST_COOLDOWN_SECONDS:
            wait = int(OTP_REQUEST_COOLDOWN_SECONDS - elapsed)
            return jsonify({"error": f"Please wait {wait}s before requesting another code."}), 429

    code = generate_otp()
    otp = OTP(identifier=identifier, code_hash=hash_password(code), purpose="registration",
              expires_at=utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES))
    db.session.add(otp)
    db.session.commit()

    dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
    sent_live = try_send_email(
        identifier, "Your CarbonTrack verification code",
        f"Your OTP is {code}. It expires in {OTP_EXPIRY_MINUTES} minutes.\n\nIf you didn't request this, ignore this email.",
    )

    print(f"[OTP] {identifier} -> {code} (expires in {OTP_EXPIRY_MINUTES} min) {'[sent via SMTP]' if sent_live else '[dev mode / no provider configured]'}")
    resp = {"message": "OTP sent successfully" if sent_live else "OTP generated (dev mode — no email provider configured)"}
    if dev_mode and not sent_live:
        resp["dev_otp"] = code  # exposed only when no real provider is wired
    return jsonify(resp)


@auth_bp.route("/otp/verify", methods=["POST"])
@limiter.limit("10/minute")
def verify_otp():
    data = request.get_json(force=True)
    identifier = (data.get("identifier") or "").strip()
    code = (data.get("code") or "").strip()
    if not identifier or not code:
        return jsonify({"error": "identifier and code are required"}), 400

    otp = OTP.query.filter_by(identifier=identifier, verified=False, purpose="registration") \
        .order_by(OTP.created_at.desc()).first()
    if not otp:
        return jsonify({"error": "Invalid OTP"}), 400
    if otp.expires_at < utcnow():
        return jsonify({"error": "OTP expired, please request a new one"}), 400
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        return jsonify({"error": "Too many incorrect attempts. Please request a new code."}), 429

    if not check_password(code, otp.code_hash):
        otp.attempts += 1
        db.session.commit()
        remaining = max(0, OTP_MAX_ATTEMPTS - otp.attempts)
        return jsonify({"error": f"Incorrect code. {remaining} attempt(s) remaining."}), 400

    otp.verified = True
    db.session.commit()
    return jsonify({"message": "OTP verified"})


@auth_bp.route("/status", methods=["GET"])
def check_registration_status():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    driver = Driver.query.filter_by(email=email).first()
    if not driver:
        return jsonify({"status": "NotFound", "message": "No registration found with this email."}), 404

    return jsonify({
        "status": driver.status,
        "rejection_reason": driver.rejection_reason,
        "driver_code": driver.driver_code
    })


# ---------------------------------------------------------- REGISTER
@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5/minute")
def register():
    """Full driver registration submitted after OTP verification.
    Accepts multipart/form-data so license / photo / address-proof files can be attached."""
    form = request.form
    identifier = (form.get("identifier") or "").strip()
    name = (form.get("name") or "").strip()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    email = form.get("email") or (identifier if "@" in identifier else None)
    phone = form.get("phone") or (identifier if "@" not in identifier else None)

    if not all([identifier, name, username, password]):
        return jsonify({"error": "Missing required fields"}), 400

    username = validate_username(username)
    validate_password(password)
    if email:
        email = validate_email(email)
    if phone:
        phone = validate_phone(phone)

    verified = OTP.query.filter_by(identifier=identifier, verified=True) \
        .order_by(OTP.created_at.desc()).first()
    if not verified:
        return jsonify({"error": "Please verify OTP before registering"}), 400

    if Driver.query.filter_by(username=username).first():
        raise ConflictError("Username already taken")
    if email and Driver.query.filter_by(email=email).first():
        raise ConflictError("An account already exists with this email")
    if phone and Driver.query.filter_by(phone=phone).first():
        raise ConflictError("An account already exists with this phone number")

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)

    def save_file(field):
        file = request.files.get(field)
        if not file:
            raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required")
        if file.filename == "":
            raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required")
        fname = secure_filename(f"{username}_{field}_{file.filename}")
        path = os.path.join(upload_dir, fname)
        file.save(path)
        return fname


    last = Driver.query.order_by(Driver.id.desc()).first()
    next_num = (last.id if last else 0) + 1
    driver_code = f"D{next_num:04d}"

    driver = Driver(
        driver_code=driver_code, name=name, username=username,
        password_hash=hash_password(password), email=email, phone=phone,
        dob=form.get("dob"), address=form.get("address"),
        license_no=form.get("license_no"),
        experience_years=int(form.get("experience_years") or 0),
        emergency_contact=form.get("emergency_contact"),
        license_doc_path=save_file("license_doc"),
        profile_photo_path=save_file("profile_photo"),
        address_proof_path=save_file("address_proof"),
        status="Pending",
    )
    db.session.add(driver)
    db.session.commit()

    notify(
        audience="admin", notif_type="SYSTEM", priority="ACTION",
        title="New driver registration", category="registration",
        message=f"New driver registration pending approval: {name} ({driver_code})",
        driver_id=driver.id,
    )
    db.session.commit()

    return jsonify({"message": "Registration submitted. Awaiting admin approval.",
                     "driver_code": driver_code}), 201


@auth_bp.route("/me", methods=["GET"])
def whoami():
    from routes.auth_utils import decode_token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing token"}), 401
    try:
        payload = decode_token(auth_header.split(" ", 1)[1])
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    if payload["role"] == "admin":
        u = db.session.get(Admin, payload["user_id"])
        return jsonify({"role": "admin", "user": u.to_dict()})
    else:
        u = db.session.get(Driver, payload["user_id"])
        return jsonify({"role": "driver", "user": u.to_dict()})

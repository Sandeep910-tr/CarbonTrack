"""Registration + OTP flow: request -> verify -> register."""
from models.db import OTP, Driver


def _get_otp_code(client, email):
    r = client.post("/api/v1/auth/otp/request", json={"identifier": email})
    assert r.status_code == 200
    return r.get_json()["dev_otp"]


class TestOtpRequest:
    def test_request_otp_email_ok(self, client):
        r = client.post("/api/v1/auth/otp/request", json={"identifier": "newdriver@example.com"})
        assert r.status_code == 200
        assert "dev_otp" in r.get_json()

    def test_request_otp_missing_identifier(self, client):
        r = client.post("/api/v1/auth/otp/request", json={})
        assert r.status_code == 400

    def test_request_otp_invalid_email(self, client):
        r = client.post("/api/v1/auth/otp/request", json={"identifier": "not-an-email"})
        assert r.status_code == 400

    def test_phone_otp_rejected(self, client):
        """Phone OTP is intentionally unsupported — no SMS provider is wired up."""
        r = client.post("/api/v1/auth/otp/request", json={"identifier": "9876543210"})
        assert r.status_code == 400
        assert "phone" in r.get_json()["error"].lower()

    def test_request_otp_existing_account_conflict(self, client, approved_driver, app):
        r = client.post("/api/v1/auth/otp/request", json={"identifier": "driver1@example.com"})
        assert r.status_code == 409

    def test_request_otp_cooldown(self, client):
        client.post("/api/v1/auth/otp/request", json={"identifier": "cooldown@example.com"})
        r = client.post("/api/v1/auth/otp/request", json={"identifier": "cooldown@example.com"})
        assert r.status_code == 429

    def test_otp_stored_hashed_not_plaintext(self, client, app):
        code = _get_otp_code(client, "hashcheck@example.com")
        with app.app_context():
            otp = OTP.query.filter_by(identifier="hashcheck@example.com").first()
            assert otp is not None
            assert otp.code_hash != code
            assert otp.code_hash.startswith("$2")  # bcrypt hash prefix


class TestOtpVerify:
    def test_verify_correct_code(self, client):
        code = _get_otp_code(client, "verify1@example.com")
        r = client.post("/api/v1/auth/otp/verify", json={"identifier": "verify1@example.com", "code": code})
        assert r.status_code == 200

    def test_verify_wrong_code(self, client):
        _get_otp_code(client, "verify2@example.com")
        r = client.post("/api/v1/auth/otp/verify", json={"identifier": "verify2@example.com", "code": "000000"})
        assert r.status_code == 400

    def test_verify_max_attempts_lockout(self, client):
        _get_otp_code(client, "verify3@example.com")
        for _ in range(5):
            client.post("/api/v1/auth/otp/verify", json={"identifier": "verify3@example.com", "code": "111111"})
        r = client.post("/api/v1/auth/otp/verify", json={"identifier": "verify3@example.com", "code": "111111"})
        assert r.status_code == 429

    def test_verify_missing_fields(self, client):
        r = client.post("/api/v1/auth/otp/verify", json={})
        assert r.status_code == 400


class TestRegistration:
    def _verified_identifier(self, client, email="regtest@example.com"):
        code = _get_otp_code(client, email)
        client.post("/api/v1/auth/otp/verify", json={"identifier": email, "code": code})
        return email

    def test_register_without_otp_verification_rejected(self, client):
        r = client.post("/api/v1/auth/register", data={
            "identifier": "noverify@example.com", "name": "No Verify", "username": "noverify",
            "password": "Pass@1234",
        })
        assert r.status_code == 400

    def test_register_success(self, client, app):
        email = self._verified_identifier(client, "regsuccess@example.com")
        r = client.post("/api/v1/auth/register", data={
            "identifier": email, "name": "Reg Success", "username": "regsuccessuser",
            "password": "Pass@1234",
        })
        assert r.status_code == 201
        with app.app_context():
            d = Driver.query.filter_by(username="regsuccessuser").first()
            assert d is not None
            assert d.status == "Pending"

    def test_register_duplicate_username(self, client, approved_driver):
        email = self._verified_identifier(client, "dupuser@example.com")
        r = client.post("/api/v1/auth/register", data={
            "identifier": email, "name": "Dup", "username": "driver1",  # already taken
            "password": "Pass@1234",
        })
        assert r.status_code == 409

    def test_register_invalid_username_format(self, client):
        email = self._verified_identifier(client, "badusername@example.com")
        r = client.post("/api/v1/auth/register", data={
            "identifier": email, "name": "Bad", "username": "a",  # too short
            "password": "Pass@1234",
        })
        assert r.status_code == 400

    def test_register_weak_password(self, client):
        email = self._verified_identifier(client, "weakpass@example.com")
        r = client.post("/api/v1/auth/register", data={
            "identifier": email, "name": "Weak", "username": "weakpassuser",
            "password": "123",
        })
        assert r.status_code == 400

    def test_register_missing_fields(self, client):
        r = client.post("/api/v1/auth/register", data={"name": "Missing"})
        assert r.status_code == 400

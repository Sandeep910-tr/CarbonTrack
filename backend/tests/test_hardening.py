"""Tests for the hardening pass: trip-safety guards, backend-authoritative
carbon calculation, audit logging, pagination, rate limiting, and security
headers."""
from models.db import db, Driver, Vehicle, AuditLog, utcnow
from routes.auth_utils import hash_password, generate_token


def _create_trip(client, driver_headers, **overrides):
    payload = {
        "source": "Bengaluru", "destination": "Mysuru", "distance_km": 150, "load_kg": 500,
        "dest_lat": 12.2958, "dest_lng": 76.6394,
    }
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


def _ping_at_dest(client, driver_headers, trip_id, lat=12.2958, lng=76.6394, accuracy=10):
    """Records a GPS fix within the destination arrival radius (spec
    sections 15-18) so End Trip is unlocked for tests that aren't
    specifically exercising the destination lock itself."""
    return client.post(f"/api/v1/driver/trips/{trip_id}/location",
                        json={"lat": lat, "lng": lng, "accuracy": accuracy}, headers=driver_headers)


class TestTripSafetyGuards:
    def test_create_trip_rejected_for_non_approved_driver(self, app, client, driver_headers, approved_driver):
        with app.app_context():
            d = db.session.get(Driver, approved_driver["id"])
            d.status = "Blocked"
            db.session.commit()
        r = _create_trip(client, driver_headers)
        assert r.status_code == 403
        assert r.get_json()["code"] == "DRIVER_NOT_ACTIVE"

    def test_create_trip_rejected_for_inactive_vehicle(self, app, client, driver_headers, vehicle):
        with app.app_context():
            v = db.session.get(Vehicle, vehicle["id"])
            v.status = "Maintenance"
            db.session.commit()
        r = _create_trip(client, driver_headers)
        assert r.status_code == 403
        assert r.get_json()["code"] == "VEHICLE_NOT_ACTIVE"

    def test_create_trip_rejects_identical_source_and_destination(self, client, driver_headers):
        r = _create_trip(client, driver_headers, source="Bengaluru", destination="bengaluru")
        assert r.status_code == 400

    def test_create_trip_rejects_second_trip_while_one_ongoing(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r = _create_trip(client, driver_headers)
        assert r.status_code == 409
        assert r.get_json()["code"] == "ACTIVE_TRIP_EXISTS"


class TestAuthoritativeCarbonCalculation:
    def test_end_trip_requires_fuel_and_price(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/end", json={}, headers=driver_headers)
        assert r.status_code == 400

    def test_end_trip_ignores_client_submitted_co2_and_computes_serverside(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        # A tampered request tries to inject a fabricated (implausibly low) CO2 figure.
        r = client.post(
            f"/api/v1/trips/{trip_id}/end",
            json={"actual_fuel_l": 20, "actual_fuel_price": 95, "actual_co2_kg": 0.01, "actual_cost": 0.01},
            headers=driver_headers,
        )
        assert r.status_code == 200
        body = r.get_json()
        # Diesel emission factor (2.68 kg CO2/L) * 20L, not the injected 0.01.
        assert body["actual_co2_kg"] == 53.6
        assert body["actual_cost"] == 20 * 95
        assert body["co2_methodology_version"] == "v1.0"

    def test_end_trip_rejects_unrealistic_fuel_value(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r = client.post(f"/api/v1/trips/{trip_id}/end",
                         json={"actual_fuel_l": 999999, "actual_fuel_price": 95},
                         headers=driver_headers)
        assert r.status_code == 400


class TestAuditLog:
    def test_driver_approval_writes_audit_entry(self, app, client, admin_headers, pending_driver):
        r = client.post(f"/api/v1/admin/drivers/{pending_driver['id']}/approve", headers=admin_headers)
        assert r.status_code == 200
        with app.app_context():
            entry = AuditLog.query.filter_by(action="driver.approve", resource_id=pending_driver["id"]).first()
            assert entry is not None
            assert entry.actor_type == "admin"

    def test_trip_end_writes_audit_entry(self, app, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        client.post(f"/api/v1/trips/{trip_id}/end", json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=driver_headers)
        with app.app_context():
            entry = AuditLog.query.filter_by(action="trip.end", resource_id=trip_id).first()
            assert entry is not None
            assert entry.actor_type == "driver"


class TestPagination:
    def test_drivers_list_unpaginated_by_default(self, client, admin_headers, approved_driver):
        r = client.get("/api/v1/admin/drivers", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_drivers_list_paginated_when_requested(self, client, admin_headers, approved_driver):
        r = client.get("/api/v1/admin/drivers?page=1&per_page=1", headers=admin_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert set(body.keys()) >= {"items", "page", "per_page", "total", "total_pages"}
        assert len(body["items"]) <= 1


class TestSecurityHeaders:
    def test_response_has_security_headers(self, client):
        r = client.get("/api/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "X-Request-ID" in r.headers

    def test_ready_endpoint(self, client):
        r = client.get("/api/ready")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ready"


class TestRateLimiting:
    def test_login_is_rate_limited(self, client):
        responses = [client.post("/api/v1/auth/login", json={"username": "nope", "password": "nope"}) for _ in range(15)]
        statuses = [r.status_code for r in responses]
        assert 429 in statuses, f"expected a 429 among {statuses} after 15 rapid login attempts"


class TestGetTripIdor:
    """Regression test for a real IDOR vulnerability found via a systematic
    route-by-route authorization audit: GET /trips/<id> is intentionally
    shared between drivers and admins, but had no ownership check at all -
    any authenticated driver could view any OTHER driver's trip (source,
    destination, fuel, cost, CO2 - everything) just by incrementing the ID
    in the URL. This is the exact scenario the spec names explicitly:
    "Driver A must not access Driver-B-trip by simply changing the ID."""

    def test_driver_cannot_view_another_drivers_trip(self, app, client, driver_headers, vehicle):
        # approved_driver (driver_headers) creates a trip.
        trip_id = _create_trip(client, driver_headers).get_json()["id"]

        # A second, unrelated driver is created and authenticated.
        with app.app_context():
            other = Driver(driver_code="D9999", name="Other Driver", username="other_driver_idor",
                            password_hash=hash_password("Other@12345"), email="other@example.com",
                            phone="9998887777", status="Approved", assigned_vehicle_id=vehicle["id"])
            db.session.add(other)
            db.session.commit()
            other_token = generate_token(other.id, "driver", {"name": other.name})
        other_headers = {"Authorization": f"Bearer {other_token}"}

        r = client.get(f"/api/v1/trips/{trip_id}", headers=other_headers)
        assert r.status_code == 403, (
            f"IDOR: driver B fetched driver A's trip! status={r.status_code}, body={r.get_json()}"
        )

    def test_driver_can_view_own_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.get(f"/api/v1/trips/{trip_id}", headers=driver_headers)
        assert r.status_code == 200
        assert r.get_json()["id"] == trip_id

    def test_admin_can_view_any_trip(self, client, driver_headers, admin_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        r = client.get(f"/api/v1/trips/{trip_id}", headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["id"] == trip_id


class TestScopeAudit:
    """Regression tests for two over-permissive-scope findings from a
    systematic route-by-route audit: endpoints correctly restricted by
    ROLE (driver vs admin) but not by what DATA they exposed to that role."""

    def test_carbon_trend_is_admin_only(self, client, driver_headers, admin_headers):
        # Was accessible to drivers and returned unfiltered fleet-wide daily
        # CO2/fuel totals - no driver-facing page ever used it, and it
        # violates "driver -> own analytics only". Now admin-only.
        r_driver = client.get("/api/v1/admin/analytics/carbon-trend", headers=driver_headers)
        assert r_driver.status_code == 403
        r_admin = client.get("/api/v1/admin/analytics/carbon-trend", headers=admin_headers)
        assert r_admin.status_code == 200

    def test_ai_chat_blocks_financial_and_admin_queue_topics_for_drivers(self, client, driver_headers, admin_headers):
        for msg in ["what's our fuel budget", "total spend this month", "how many pending approvals"]:
            r = client.post("/api/v1/admin/ai-chat", json={"message": msg}, headers=driver_headers)
            assert r.status_code == 200
            assert "admins only" in r.get_json()["reply"].lower()

        # The same questions work normally for an admin caller.
        r_admin = client.post("/api/v1/admin/ai-chat", json={"message": "total spend this month"}, headers=admin_headers)
        assert "admins only" not in r_admin.get_json()["reply"].lower()

    def test_ai_chat_still_answers_safe_topics_for_drivers(self, client, driver_headers):
        # CO2/fuel/top-driver/maintenance topics mirror data already exposed
        # via /sustainability and /analytics/leaderboard - these should keep
        # working for drivers, not get blanket-blocked.
        r = client.post("/api/v1/admin/ai-chat", json={"message": "what's our total co2"}, headers=driver_headers)
        assert r.status_code == 200
        assert "admins only" not in r.get_json()["reply"].lower()

    def test_route_deviation_cannot_reference_another_drivers_trip(self, app, client, driver_headers, vehicle):
        # Driver A's trip.
        trip_id = _create_trip(client, driver_headers).get_json()["id"]

        # Driver B tries to report a "deviation" tagging Driver A's trip_id.
        with app.app_context():
            other = Driver(driver_code="D9998", name="Other Driver 2", username="other_driver_dev",
                            password_hash=hash_password("Other@12345"), email="other2@example.com",
                            phone="9997776666", status="Approved", assigned_vehicle_id=vehicle["id"])
            db.session.add(other)
            db.session.commit()
            other_token = generate_token(other.id, "driver", {"name": other.name})
        other_headers = {"Authorization": f"Bearer {other_token}"}

        r = client.post("/api/v1/driver/route-deviation", json={"trip_id": trip_id, "note": "test"}, headers=other_headers)
        assert r.status_code == 201  # request still succeeds (it's a notification, not a data leak)

        from models.db import Notification, Trip
        real_trip = db.session.get(Trip, trip_id)
        note = Notification.query.filter_by(category="route_deviation").order_by(Notification.id.desc()).first()
        # Must NOT reference driver A's real trip_code - the spoofed trip_id was ignored.
        assert real_trip.trip_code not in note.message
        assert "current trip" in note.message


class TestApiVersioning:
    def test_versioned_routes_respond(self, client):
        r = client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
        assert r.status_code in (400, 401)

    def test_unversioned_legacy_path_is_gone(self, client):
        r = client.get("/api/admin/drivers")
        assert r.status_code == 404

    def test_health_and_ready_remain_unversioned(self, client):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200


class TestMlInputOutputValidation:
    def test_predict_rejects_infinite_temperature(self, client, driver_headers, vehicle):
        r = client.post(
            "/api/v1/trips/predict",
            data='{"distance_km": 100, "load_kg": 500, "temperature": Infinity}',
            content_type="application/json",
            headers=driver_headers,
        )
        assert r.status_code == 400

    def test_predict_rejects_out_of_range_humidity(self, client, driver_headers, vehicle):
        r = client.post("/api/v1/trips/predict",
                         json={"distance_km": 100, "load_kg": 500, "humidity": 150},
                         headers=driver_headers)
        assert r.status_code == 400

    def test_predict_rejects_unrealistic_distance(self, client, driver_headers, vehicle):
        r = client.post("/api/v1/trips/predict",
                         json={"distance_km": 999999, "load_kg": 500},
                         headers=driver_headers)
        assert r.status_code == 400

    def test_predict_succeeds_with_valid_input(self, client, driver_headers, vehicle):
        r = client.post("/api/v1/trips/predict",
                         json={"distance_km": 120, "load_kg": 500},
                         headers=driver_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert body["predicted_fuel_l"] >= 0
        assert body["predicted_co2_kg"] >= 0


class TestIdempotency:
    def test_create_trip_with_same_idempotency_key_returns_same_trip(self, client, driver_headers):
        headers = {**driver_headers, "Idempotency-Key": "test-key-abc-123"}
        r1 = _create_trip(client, headers)
        assert r1.status_code == 201
        trip_id_1 = r1.get_json()["id"]

        r2 = _create_trip(client, headers)  # same key, same payload - simulates a retried request
        assert r2.status_code == 201
        assert r2.get_json()["id"] == trip_id_1
        assert r2.headers.get("Idempotent-Replay") == "true"

        # Confirm only ONE trip was actually created, not two.
        from models.db import Trip
        assert Trip.query.filter_by(driver_id=r1.get_json()["driver_id"]).count() == 1

    def test_create_trip_without_idempotency_key_is_unaffected(self, client, driver_headers):
        # No header at all - each call is independent (existing behavior).
        r1 = _create_trip(client, driver_headers)
        assert r1.status_code == 201
        r2 = client.post(f"/api/v1/trips/{r1.get_json()['id']}/start", headers=driver_headers)
        assert r2.status_code == 200
        # A second create without a key should be blocked by the ACTIVE_TRIP_EXISTS
        # guard (unrelated to idempotency) since trip 1 is now Ongoing.
        r3 = _create_trip(client, driver_headers)
        assert r3.status_code == 409

    def test_end_trip_idempotency_key_replays_completion(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        headers = {**driver_headers, "Idempotency-Key": "end-key-xyz"}
        payload = {"actual_fuel_l": 10, "actual_fuel_price": 95}

        r1 = client.post(f"/api/v1/trips/{trip_id}/end", json=payload, headers=headers)
        assert r1.status_code == 200
        r2 = client.post(f"/api/v1/trips/{trip_id}/end", json=payload, headers=headers)
        assert r2.status_code == 200
        assert r2.get_json()["actual_fuel_l"] == r1.get_json()["actual_fuel_l"]
        assert r2.headers.get("Idempotent-Replay") == "true"

    def test_different_idempotency_keys_are_independent(self, client, driver_headers):
        r1 = _create_trip(client, {**driver_headers, "Idempotency-Key": "key-one"})
        assert r1.status_code == 201
        client.post(f"/api/v1/trips/{r1.get_json()['id']}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, r1.get_json()['id'])
        client.post(f"/api/v1/trips/{r1.get_json()['id']}/end",
                     json={"actual_fuel_l": 5, "actual_fuel_price": 95}, headers=driver_headers)
        # A genuinely new trip with a different key should NOT be treated as a replay.
        r2 = _create_trip(client, {**driver_headers, "Idempotency-Key": "key-two"})
        assert r2.status_code == 201
        assert r2.get_json()["id"] != r1.get_json()["id"]

    def test_in_progress_claim_never_returns_a_fabricated_response(self, app, client, driver_headers):
        """Regression test for a real concurrency bug found via manual load
        testing (see HARDENING_CHANGELOG.md 'Round 5'): a request arriving
        while an earlier request with the SAME idempotency key is still
        mid-flight used to see the claimed-but-not-yet-completed
        IdempotencyRecord row (response_body still NULL) and return a
        fabricated `200 {}` instead of either the real result or a proper
        'try again' signal. Simulates that exact in-flight window
        deterministically (rather than relying on real thread timing, which
        doesn't race reliably against this test suite's in-memory SQLite
        database) by inserting the claim row directly, the same way the
        decorator's first phase does, then calling the endpoint before ever
        "completing" it."""
        from models.db import IdempotencyRecord
        with app.app_context():
            claim = IdempotencyRecord(key="racing-key", scope="trip.create",
                                       actor_id=None, status_code=None, response_body=None)
            # actor_id must match the real driver's id for the lookup to hit this row.
            import jwt as pyjwt
            token = driver_headers["Authorization"].split(" ", 1)[1]
            decoded = pyjwt.decode(token, options={"verify_signature": False})
            claim.actor_id = decoded["user_id"]
            db.session.add(claim)
            db.session.commit()

        r = _create_trip(client, {**driver_headers, "Idempotency-Key": "racing-key"})
        assert r.status_code == 409
        assert r.get_json()["code"] == "IDEMPOTENT_REQUEST_IN_PROGRESS"
        # Critically: NOT a 200 with an empty/null body, which is what the
        # bug produced.
        assert r.status_code != 200


class TestAccountLockout:
    def test_account_locks_after_five_failed_attempts(self, client, approved_driver):
        for _ in range(5):
            r = client.post("/api/v1/auth/login", json={"username": approved_driver["username"], "password": "wrong"})
            assert r.status_code == 401
        # 6th attempt (even with the CORRECT password) should now be locked.
        r = client.post("/api/v1/auth/login",
                         json={"username": approved_driver["username"], "password": approved_driver["password"]})
        assert r.status_code == 423
        assert r.get_json()["code"] == "ACCOUNT_LOCKED"

    def test_successful_login_resets_failed_attempts(self, client, approved_driver):
        for _ in range(3):
            client.post("/api/v1/auth/login", json={"username": approved_driver["username"], "password": "wrong"})
        r = client.post("/api/v1/auth/login",
                         json={"username": approved_driver["username"], "password": approved_driver["password"]})
        assert r.status_code == 200
        from models.db import db, Driver
        d = db.session.get(Driver, approved_driver["id"])
        assert d.failed_login_attempts == 0
        assert d.locked_until is None

    def test_wrong_password_alone_does_not_lock(self, client, approved_driver):
        r1 = client.post("/api/v1/auth/login", json={"username": approved_driver["username"], "password": "wrong"})
        assert r1.status_code == 401
        r2 = client.post("/api/v1/auth/login",
                          json={"username": approved_driver["username"], "password": approved_driver["password"]})
        assert r2.status_code == 200  # not locked after just 1 bad attempt


class TestGpsImpossibleJump:
    def test_impossible_speed_jump_rejected(self, app, client, driver_headers):
        trip_id = _create_trip(client, driver_headers, source="Bengaluru", destination="Mysuru", distance_km=150).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r1 = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                          json={"lat": 12.9716, "lng": 77.5946}, headers=driver_headers)
        assert r1.status_code == 201
        # Back-date the first ping by 10 seconds so the elapsed-time floor
        # (MIN_ELAPSED_SECONDS_FOR_CHECK) doesn't skip the check - simulates
        # two real GPS fixes 10 seconds apart, not two requests fired back
        # to back within the same test.
        from datetime import timedelta
        from models.db import TripLocation, db
        with app.app_context():
            ping = TripLocation.query.filter_by(trip_id=trip_id).order_by(TripLocation.id.desc()).first()
            ping.recorded_at = utcnow() - timedelta(seconds=10)
            db.session.commit()
        # Same trip, ~200km away 10 seconds later (implies an impossible
        # speed for a road vehicle).
        r2 = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                          json={"lat": 15.3173, "lng": 75.7139}, headers=driver_headers)
        assert r2.status_code == 400
        assert r2.get_json()["code"] == "IMPOSSIBLE_GPS_JUMP"

    def test_plausible_movement_accepted(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers, source="Bengaluru", destination="Mysuru", distance_km=150).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        r1 = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                          json={"lat": 12.9716, "lng": 77.5946}, headers=driver_headers)
        assert r1.status_code == 201
        # A tiny, realistic nudge nearby.
        r2 = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                          json={"lat": 12.9720, "lng": 77.5950}, headers=driver_headers)
        assert r2.status_code == 201


class TestCarbonMethodologyVersioning:
    def test_trip_end_records_active_methodology(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        r = client.post(f"/api/v1/trips/{trip_id}/end",
                         json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=driver_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert body["co2_methodology_version"] == "v1.0"
        assert body["methodology_id"] is not None

    def test_admin_can_list_methodologies(self, client, admin_headers):
        r = client.get("/api/v1/admin/carbon-methodologies", headers=admin_headers)
        assert r.status_code == 200
        versions = r.get_json()
        assert any(m["version_label"] == "v1.0" and m["is_active"] for m in versions)

    def test_creating_new_methodology_requires_superadmin(self, client, admin_headers):
        r = client.post("/api/v1/admin/carbon-methodologies",
                         json={"version_label": "v1.1", "emission_factors": {"Diesel": 2.70}},
                         headers=admin_headers)
        assert r.status_code == 403

    def test_superadmin_can_create_and_activate_new_methodology(self, client, super_admin_headers, driver_headers):
        r = client.post("/api/v1/admin/carbon-methodologies",
                         json={"version_label": "v1.1", "emission_factors": {"Diesel": 2.70}, "notes": "Updated factor"},
                         headers=super_admin_headers)
        assert r.status_code == 201
        new_id = r.get_json()["id"]
        assert r.get_json()["is_active"] is False  # created inactive

        activate = client.post(f"/api/v1/admin/carbon-methodologies/{new_id}/activate", headers=super_admin_headers)
        assert activate.status_code == 200
        assert activate.get_json()["is_active"] is True

        # A trip ended now should be computed under v1.1, not v1.0.
        trip_id = _create_trip(client, driver_headers).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        end = client.post(f"/api/v1/trips/{trip_id}/end",
                           json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=driver_headers)
        assert end.get_json()["co2_methodology_version"] == "v1.1"
        assert end.get_json()["actual_co2_kg"] == 27.0  # 10L * 2.70

    def test_duplicate_version_label_rejected(self, client, super_admin_headers):
        r = client.post("/api/v1/admin/carbon-methodologies",
                         json={"version_label": "v1.0", "emission_factors": {"Diesel": 2.68}},
                         headers=super_admin_headers)
        assert r.status_code == 409


class TestExternalApiCaching:
    def test_weather_second_call_is_cached(self, client, driver_headers, monkeypatch):
        import routes.external as external_mod

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"weather": [{"main": "Clear", "description": "clear sky"}],
                        "main": {"temp": 28, "humidity": 55}, "wind": {"speed": 2}, "name": "Bengaluru", "dt": 123}

        call_count = {"n": 0}
        def fake_get(url, params=None, timeout=None):
            call_count["n"] += 1
            return FakeResponse()
        monkeypatch.setattr(external_mod.requests, "get", fake_get)
        monkeypatch.setattr(external_mod.current_app.config, "get", lambda k, d=None: "fake-key" if k == "OPENWEATHER_API_KEY" else d)

        r1 = client.get("/api/v1/external/weather?lat=12.97&lon=77.59", headers=driver_headers)
        r2 = client.get("/api/v1/external/weather?lat=12.97&lon=77.59", headers=driver_headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.get_json().get("cached") is True
        assert call_count["n"] == 1  # only ONE real HTTP call made across both requests


class TestAreaWeather:
    def _mock_openweather(self, monkeypatch, condition="Clear"):
        import routes.external as external_mod

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"weather": [{"main": condition, "description": condition.lower()}],
                        "main": {"temp": 28, "humidity": 55}, "wind": {"speed": 2}, "name": "Bengaluru", "dt": 123}

        call_count = {"n": 0}
        def fake_get(url, params=None, timeout=None):
            call_count["n"] += 1
            return FakeResponse()
        monkeypatch.setattr(external_mod.requests, "get", fake_get)
        monkeypatch.setattr(external_mod.current_app.config, "get", lambda k, d=None: "fake-key" if k == "OPENWEATHER_API_KEY" else d)
        return call_count

    def test_area_weather_returns_aggregated_shape(self, client, driver_headers, monkeypatch):
        self._mock_openweather(monkeypatch)
        r = client.get("/api/v1/external/weather/area?lat=12.9716&lon=77.5946&radius_km=5", headers=driver_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert body["radius_km"] == 5
        assert body["sample_count"] == 5  # center + N/S/E/W
        assert body["successful_samples"] == 5
        assert body["severe_weather"] is False
        assert body["temperature"] == 28

    def test_area_weather_flags_severe_condition_from_any_sample(self, client, driver_headers, monkeypatch):
        import routes.external as external_mod

        class FakeResponse:
            status_code = 200
            def __init__(self, condition): self._condition = condition
            def raise_for_status(self): pass
            def json(self):
                return {"weather": [{"main": self._condition, "description": self._condition.lower()}],
                        "main": {"temp": 24, "humidity": 70}, "wind": {"speed": 3}, "name": "Area", "dt": 1}

        # First point (center) is Clear, everything else is Rain — the area
        # result must not say "Clear" just because the center sample was dry.
        calls = {"n": 0}
        def fake_get(url, params=None, timeout=None):
            calls["n"] += 1
            return FakeResponse("Clear" if calls["n"] == 1 else "Rain")
        monkeypatch.setattr(external_mod.requests, "get", fake_get)
        monkeypatch.setattr(external_mod.current_app.config, "get", lambda k, d=None: "fake-key" if k == "OPENWEATHER_API_KEY" else d)

        # Distinct coordinates from other tests in this class so the module-level
        # per-point weather cache can't accidentally serve a cached "Clear" here.
        r = client.get("/api/v1/external/weather/area?lat=19.0760&lon=72.8777", headers=driver_headers)
        body = r.get_json()
        assert body["carbontrack_condition"] == "Rain"
        assert body["severe_weather"] is True
        assert "Rain" in body["area_alert"]

    def test_area_weather_radius_is_clamped(self, client, driver_headers, monkeypatch):
        self._mock_openweather(monkeypatch)
        too_big = client.get("/api/v1/external/weather/area?lat=12.97&lon=77.59&radius_km=50", headers=driver_headers)
        too_small = client.get("/api/v1/external/weather/area?lat=12.97&lon=77.59&radius_km=0.5", headers=driver_headers)
        assert too_big.get_json()["radius_km"] == 5
        assert too_small.get_json()["radius_km"] == 2

    def test_area_weather_second_call_is_cached(self, client, driver_headers, monkeypatch):
        call_count = self._mock_openweather(monkeypatch)
        r1 = client.get("/api/v1/external/weather/area?lat=13.05&lon=77.60&radius_km=3", headers=driver_headers)
        r2 = client.get("/api/v1/external/weather/area?lat=13.05&lon=77.60&radius_km=3", headers=driver_headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.get_json().get("cached") is True
        assert call_count["n"] == 5  # 5 samples fetched once, then served from the area cache


class TestPredictionErrorReporting:
    def test_completed_trip_includes_prediction_error(self, client, driver_headers):
        # Real usage: the frontend calls /predict first, then passes the
        # result as ai_prediction when creating the trip (see
        # NewTrip.jsx -> create_trip). Mirror that here rather than relying
        # on default None predictions.
        trip_id = _create_trip(client, driver_headers, ai_prediction={
            "predicted_fuel_l": 12.0, "predicted_co2_kg": 32.16, "predicted_cost": 1140,
            "predicted_eco_score": 75, "maintenance_risk": "Low", "recommended_route": "Eco",
            "ai_confidence": 80,
        }).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        _ping_at_dest(client, driver_headers, trip_id)
        r = client.post(f"/api/v1/trips/{trip_id}/end",
                         json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=driver_headers)
        body = r.get_json()
        assert body["prediction_error"] is not None
        pe = body["prediction_error"]
        assert pe["fuel_actual_l"] == 10
        assert pe["fuel_predicted_l"] == 12.0
        assert pe["fuel_error_pct"] == round(((10 - 12.0) / 12.0) * 100, 1)

    def test_planned_trip_has_no_prediction_error(self, client, driver_headers):
        create_body = _create_trip(client, driver_headers, source="X", destination="Y").get_json()
        assert create_body.get("prediction_error") is None


class TestVehicleTypeValidation:
    def test_invalid_fuel_type_rejected(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles",
                         json={"vehicle_no": "KA01ZZ9999", "fuel_type": "Nuclear", "vehicle_type": "Van"},
                         headers=admin_headers)
        assert r.status_code == 400

    def test_invalid_vehicle_type_rejected(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles",
                         json={"vehicle_no": "KA01ZZ9998", "fuel_type": "Diesel", "vehicle_type": "Spaceship"},
                         headers=admin_headers)
        assert r.status_code == 400

    def test_valid_fuel_and_vehicle_type_accepted(self, client, admin_headers):
        r = client.post("/api/v1/admin/vehicles",
                         json={"vehicle_no": "KA01ZZ9997", "fuel_type": "Electric", "vehicle_type": "Van"},
                         headers=admin_headers)
        assert r.status_code == 201
        assert r.get_json()["fuel_type"] == "Electric"


class TestAdminIdempotency:
    def test_duplicate_depot_creation_prevented_by_key(self, client, admin_headers):
        headers = {**admin_headers, "Idempotency-Key": "depot-create-key-1"}
        r1 = client.post("/api/v1/admin/depots", json={"name": "Central Warehouse"}, headers=headers)
        assert r1.status_code == 201
        r2 = client.post("/api/v1/admin/depots", json={"name": "Central Warehouse"}, headers=headers)
        assert r2.status_code == 201
        assert r2.get_json()["id"] == r1.get_json()["id"]
        assert r2.headers.get("Idempotent-Replay") == "true"
        from models.db import Depot
        assert Depot.query.filter_by(name="Central Warehouse").count() == 1

    def test_duplicate_service_record_prevented_by_key(self, client, admin_headers, vehicle):
        headers = {**admin_headers, "Idempotency-Key": "svc-record-key-1"}
        payload = {"service_date": "2026-01-15", "cost": 500}
        r1 = client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", json=payload, headers=headers)
        assert r1.status_code == 201
        r2 = client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", json=payload, headers=headers)
        assert r2.status_code == 201
        assert r2.get_json()["record"]["id"] == r1.get_json()["record"]["id"]
        from models.db import ServiceRecord
        assert ServiceRecord.query.filter_by(vehicle_id=vehicle["id"]).count() == 1

    def test_service_record_without_key_creates_two_on_double_submit(self, client, admin_headers, vehicle):
        # No Idempotency-Key -> unaffected, matches existing behavior.
        payload = {"service_date": "2026-01-15", "cost": 500}
        client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", json=payload, headers=admin_headers)
        client.post(f"/api/v1/admin/vehicles/{vehicle['id']}/service-records", json=payload, headers=admin_headers)
        from models.db import ServiceRecord
        assert ServiceRecord.query.filter_by(vehicle_id=vehicle["id"]).count() == 2

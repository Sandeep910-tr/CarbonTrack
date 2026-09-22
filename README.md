# Carbon Footprint Tracking in Logistics

A full-stack fleet management platform: React (Vite + Tailwind + Framer Motion) frontend,
Flask + SQLAlchemy backend, SQLite database, an AI Prediction Engine (Random Forest /
XGBoost) trained on your trip data, a continuous learning pipeline, and full Google
Maps/Routes/Places/Geocoding + OpenWeather integration.

## ⚠️ Before you do anything: rotate your API keys

The Google Maps/Routes/Places keys and both OpenWeather keys previously shared in chat were
pasted in plaintext and wired into `backend/.env` so the app would run out of the box. That
`.env` file has now been redacted in this delivered copy — see `backend/.env` for placeholders
— but **treat every key that was ever in a chat message or a document as compromised** and
rotate them regardless:

1. Go to Google Cloud Console → APIs & Services → Credentials → regenerate each key.
2. Restrict the new keys by **HTTP referrer** (for the Maps JS key used client-side) and by
   **API + IP** for the server-side Routes/Places/Geocoding keys.
3. Regenerate your OpenWeather key at openweathermap.org/api_keys.
4. Put the new values into `backend/.env` (or your deployment's secret manager) — never commit
   `.env` or paste live keys into a README/chat/ticket again; that's exactly how the previous
   key ended up exposed.

## What's implemented

This build went through two rounds: an initial core platform, then a full pass closing
every gap identified against the flowchart. Here's the complete feature set.

### Auth & registration
- JWT + bcrypt, single login endpoint for both admins and drivers.
- Full registration flow: email/phone → OTP → details → document upload → username/password
  → pending admin approval.
- **Real email OTP delivery**: if you set `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` in
  `backend/.env`, OTPs are sent via actual SMTP. If unset, it falls back to dev mode
  (OTP printed to console + returned in the API response) — there's no SMS provider
  wired in since none was supplied, so phone-based OTPs always use the dev-mode fallback.

### Admin dashboard
- Driver approval queue (approve/reject/block/reinstate), vehicle CRUD + assignment.
- **Admin account management** (`/admin/admins`, SuperAdmin-only): create/suspend/delete
  admin accounts, assign the `Admin` or `SuperAdmin` role. The first seeded admin
  (`admin1`) is SuperAdmin; the rest are regular Admins. This is real role-based access
  control enforced server-side (`@super_admin_required`), not just a hidden UI element —
  non-SuperAdmins get a 403 from the API if they call these endpoints directly.
- **Backup & restore** (SuperAdmin-only, in Settings): downloads a JSON dump of vehicles,
  trips, notifications and settings; restore overwrites those tables from an uploaded
  backup file. Admin and driver accounts are deliberately excluded from restore so you
  can't lock yourself out or wipe out newer registrations.
- **Live Fleet Monitoring** with an actual Google Map: every vehicle currently on a trip
  is plotted and its marker moves as time passes, refreshed every 15 seconds.
- **Dedicated reports**: Vehicle Report, Driver Report, and Fuel Report tabs (in addition
  to the CO2/fuel trend chart), each with **CSV, Excel (.xlsx), and PDF export**.
- **Anomaly detection**: flags completed trips whose CO2 output is a statistical outlier
  (>2 standard deviations above the mean) for their vehicle type — visible in the
  Anomalies report tab and pushed to the notification feed as trips complete.
- **Continuous Learning Pipeline** (ML Pipeline tab): a "Retrain Now" button that
  retrains all six models directly from whatever completed trips currently exist in the
  live database (not just the frozen workbook data), logs metrics + row count to a
  training-run history, and also **runs automatically every 24 hours** via APScheduler.
- **AI Insights panel**: rule-based recommendations computed live from the database —
  maintenance-risk flags, top/bottom driver coaching prompts, highest-emission trip
  callouts, pending-approval counts.
- **Sustainability dashboard**: carbon budget usage bar against an admin-configurable
  target, green-trip percentage, trees-equivalent.
- **Automated alerts**: weather alerts (Storm/Fog), traffic alerts (High traffic), and
  fuel/overload alerts (load >95% of vehicle capacity) are generated automatically when a
  driver creates a trip — no manual trigger needed. Maintenance alerts fire when a trip's
  predicted risk is High. All four alert categories can be toggled off in Settings.
- **Daily AI report**: `/api/v1/admin/reports/daily` computes yesterday's totals on demand,
  and the same logic runs automatically once a day, posting a summary to the notification
  feed.
- Settings page: carbon/fuel budget targets, per-category notification toggles, company name.

### Driver dashboard
- Profile + assigned vehicle, trip history, notifications.
- **New Trip wizard, now backed by real Google Routes**: enter source/destination/load →
  the app geocodes both addresses and calls the **Google Routes API** for actual route
  options (labeled Fastest / Eco / Shortest based on real distance & duration, not a
  static dropdown) → pick one → live weather auto-fetch via device geolocation → AI
  prediction → confirm → start trip.
- **Real turn-by-turn navigation**: the active-trip screen draws the route polyline and a
  numbered step-by-step instruction list, both sourced from the **Routes API** response
  fetched during route selection. This deliberately avoids `google.maps.DirectionsService`,
  which depends on Google's separate legacy Directions API — a different Cloud Console
  toggle from Routes API that isn't enabled by default on new projects, and caused exactly
  the "map won't load" symptom this design avoids.
- **Nearby services lookup** (fuel/repair/hospital/rest stops) via Google Places, using
  the browser's Geolocation API.
- **SOS button** and **route-deviation reporting** — both post directly to the admin
  notification feed with appropriate severity.

- **Route comparison map**: while choosing a route, all fetched Google Routes options are
  drawn simultaneously on one map, color-coded green/amber/red by a quick AI CO2 estimate
  per route (a lightweight prediction call per option, refined into the full prediction
  once you commit to one) — makes the tradeoff visual instead of just three numbers in a list.
- **Eco-Driving Certificate**: once a driver's eco score crosses an admin-configurable
  threshold (default 80), a "Download Certificate" button appears on their Overview page,
  generating a styled PDF certificate on the fly via fpdf2. Below the threshold, it shows
  a progress bar and how many points remain instead.

### AI Chat Assistant
A floating widget on every dashboard page that answers fleet questions (total CO2, top
driver, maintenance risk, pending approvals, costs, trip counts) by querying the live
database. This is **rule-based intent matching, not a generative LLM** — no LLM API key
was supplied for this project, so it's implemented as deterministic keyword→query mapping
rather than pretending to be something it isn't, and it's labeled "rule-based" in the UI.
Swapping in a real LLM later is a one-function change (`ai_chat()` in
`backend/routes/admin.py`).

### AI Prediction Engine (`backend/ml/`)
Trained on your 2,000 historical trips joined with weather/traffic/vehicle data:
- Fuel Consumption — RandomForestRegressor (MAE ≈ 5.4 L)
- CO2 Emission — XGBoost (MAE ≈ 15.4 kg)
- Fuel Cost — RandomForestRegressor
- Driver Eco Score — RandomForestRegressor
- Predictive Maintenance risk — RandomForestClassifier
- Recommended Route — RandomForestClassifier
- Derived: weather impact, carbon budget risk, fleet health score, overall composite score

**Honesty check, unchanged from the first pass**: the maintenance-risk and
route-recommendation classifiers score ~30% accuracy — close to chance. Those label
columns in the source workbook don't correlate strongly with the available features (they
look independently randomized in the sample data), so there's no real signal for the
classifiers to learn. Fuel, CO2, cost and eco-score are true regressions against real
physical relationships in the data and perform well. `backend/ml/pipeline.py` (the
continuous learning pipeline) retrains all six the same way from live DB data — if your
real-world data has actual causal structure behind maintenance risk and route choice, the
retrained models will reflect that as trip volume grows.

### External APIs — all live, all server-side except the Maps JS key
- **Google Geocoding API** — resolves addresses to lat/lng (used by the route step and
  the Live Fleet map simulation).
- **Google Routes API** — real route options with distance/duration.
- **Google Places API (New)** — nearby fuel/repair/hospital/rest-stop lookup. Uses the
  current `places:searchNearby` endpoint, not Google's older legacy Places endpoint (which
  is being phased out and requires separately enabling a deprecated API most new Cloud
  projects don't have on by default).
- **OpenWeather API** — live conditions for the auto-weather button and automated alerts.
- **Browser Geolocation API** — powers the "use live location" weather button and nearby
  places lookup.

Only the Maps JavaScript key reaches the browser (required to render a map) via
`/api/v1/external/config/maps-key` — restrict it by HTTP referrer in the Cloud Console.
Routes/Places/Geocoding calls happen server-side so those keys never leave the backend.

### Database
Seeded directly from your workbook — 5 admins (first one promoted to SuperAdmin), 500
drivers, 200 vehicles, 2,000 historical trips with their original AI-prediction/weather/
traffic records.

## What's still simplified

Being direct about what's a genuine limitation rather than glossing over it:

- **"Live" fleet position is simulated, not real GPS.** There's no telematics device or
  location-reporting hardware in this system, so the moving marker on the Live Fleet map
  is a linear interpolation between the trip's geocoded origin and destination, scaled by
  elapsed time vs. an estimated duration from Google Routes. It moves, updates every 15s,
  and is genuinely useful for demoing the concept — but it isn't tracking a real vehicle.
  Wiring in real GPS would mean adding a driver-side location-ping loop (e.g. a phone app
  posting coordinates every N seconds) — not something that can exist without real hardware
  in the loop.
- **Route deviation is driver-reported** (a button on the active trip), not automatically
  computed from GPS drift — for the same reason above, there's no continuous real location
  stream to compare against the planned route.
- **The AI Chat Assistant is rule-based**, not a generative LLM (see above) — this was a
  deliberate, disclosed choice given no LLM API key was available, not a corner cut silently.
- **The scheduler runs in-process** (APScheduler inside the Flask app), which is correct
  for a single-instance deployment but would double-fire jobs if you ever run multiple
  Gunicorn workers. Move to Celery/RQ with a proper broker if you scale beyond one process.
- **SMS OTP delivery isn't wired to a provider** (e.g. Twilio) — only email OTP has a real
  SMTP path. Phone-registration OTPs use the dev-mode console/response fallback.

## Project structure

```
backend/
  app.py              Flask entrypoint — serves API + React build, starts APScheduler
  config.py            Environment-driven config
  .env                 API keys & secrets (ROTATE THESE — see warning above)
  seed.py               Loads backend/data/*.csv (from your workbook) into SQLite
  requirements.txt
  models/db.py          SQLAlchemy models (Admin, Driver, Vehicle, Trip, OTP,
                          Notification, Settings, ModelRun)
  routes/
    auth.py               Login, OTP (SMTP-aware), registration
    auth_utils.py          JWT helpers, token_required, super_admin_required
    admin.py                Drivers/vehicles/trips CRUD, admin management, backup/restore,
                             dedicated reports, Excel/PDF export, anomaly detection,
                             ML pipeline trigger, AI insights, AI chat, sustainability
    driver.py               Profile, trip history, notifications, SOS, route deviation
    trips.py                 Predict/create/start/end trip, automated alerts, anomaly flagging
    external.py               Google Geocoding/Routes/Places + OpenWeather proxies
  ml/
    train.py             CLI script — trains all 6 models from backend/data/*.csv
    pipeline.py            Continuous learning pipeline — retrains from LIVE DB data,
                            called by /api/v1/admin/ml/retrain and the daily scheduled job
    predict.py              Inference used by /api/v1/trips/predict
    saved/                   Trained model .pkl files (already trained — no need to retrain)
  data/                  CSV exports of your workbook sheets (used for seeding + training)
  static/                 React production build (generated — see below)
frontend/
  src/
    pages/
      admin/                Overview, LiveFleet, Drivers, Vehicles, Trips, Reports
                             (Trend/Vehicles/Drivers/Fuel/Anomalies/ML Pipeline tabs),
                             Notifications, Admins (SuperAdmin), Settings
      driver/                Overview, NewTrip (routes→predict→navigate wizard),
                              TripHistory, Notifications
    components/            Shared UI kit, DashboardLayout, RouteVisual, ChatAssistant
    lib/
      api.js                 Axios client with JWT interceptor
      googleMaps.js            Shared Google Maps JS API loader
    context/AuthContext.jsx
```

## Running it

### Why you must train the AI models locally (read this first)

This project ships pre-trained AI model files (`backend/ml/saved/*.pkl`), but **pickled
scikit-learn/XGBoost models are tied to the exact library versions that created them**.
If pip installs a newer scikit-learn than the one used here, loading those files can fail
or behave unpredictably — this is a well-known cross-version pitfall with pickle-based ML
model files, not a bug specific to this project. The setup scripts below solve this
permanently by **retraining the models on your machine, with whatever versions actually
get installed there**, so the models and the code loading them are always in sync.

### Quickest path — one command (recommended)

**Windows (PowerShell):**
```powershell
cd backend
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser   # first time only
.\setup.ps1
```

**Mac/Linux:**
```bash
cd backend
bash setup.sh
```

This single command creates the virtual environment, installs dependencies, **retrains
all 6 AI models using your installed library versions**, seeds the database, and starts
the server — all in one go. Open **http://localhost:5000** when it finishes.

Demo logins:
- Admin: `admin1` / `Admin@123` (also admin2..admin5)
- Driver: `driver1` / `Driver@123` (also driver2..driver500 — all seeded as Approved)

### Manual step-by-step (if you'd rather run each step yourself)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ml && python3 train.py && cd ..   # retrains models for YOUR installed versions - don't skip this
python3 seed.py                      # first time only — populates the database
python3 app.py
```

Open **http://localhost:5000** — Flask serves the already-built React app plus the API.

### Every time after initial setup

You don't need to repeat training or seeding. Just:
```bash
cd backend
source venv/bin/activate    # Windows: venv\Scripts\Activate.ps1
python3 app.py               # Windows: py app.py
```

### Development mode (hot reload on the frontend)

```bash
# terminal 1
cd backend && python3 app.py

# terminal 2
cd frontend && npm install && npm run dev
```

Vite dev server runs on http://localhost:5173 and proxies `/api` to Flask on :5000
(see `frontend/vite.config.js`).

### Rebuilding the frontend for production

```bash
cd frontend
npm install
npm run build
rm -rf ../backend/static/*
cp -r dist/* ../backend/static/
```

### Retraining the AI models

Only needed if you add more trip data to `backend/data/Trips.csv` (and the matching
Weather/Traffic/AI_Predictions CSVs), or want to swap in a different dataset:

```bash
cd backend/ml
python3 train.py
```

## Troubleshooting

- **"Prediction failed" / 500 error on Get AI Prediction, on every route regardless of input**
  — almost always a scikit-learn/XGBoost version mismatch between what trained the model
  files and what's installed. Fix: `cd backend/ml && python3 train.py` to retrain against
  your actual installed versions, then restart the server. The setup scripts above do this
  automatically, so this should only come up if you skip them.
- **Geolocation / "Use live location" doesn't work** — browsers only allow this on `https://`
  pages or on `http://localhost`. If you're viewing the app via a LAN IP (e.g.
  `http://10.x.x.x:5000`), switch to `http://localhost:5000` on the same machine.
- **Map is blank or shows a red error banner** — log in as an admin and check the
  **API Diagnostics** page in the sidebar; it tests every external API with a real call and
  tells you exactly which Google Cloud API needs enabling, or if a key is invalid/inactive.
- **Buttons seem to be missing on a results screen** — try scrolling down or pressing
  `Ctrl + -` to zoom out; some screens have more content than fits a short browser window.

## Security notes for production

- Change `SECRET_KEY` and `JWT_SECRET_KEY` in `.env` to long random values.
- Put this behind HTTPS (e.g. via a reverse proxy) — JWTs are sent in the `Authorization`
  header, not cookies, so no CSRF concern, but tokens should never travel over plain HTTP.
- Run with a production WSGI server (gunicorn is in requirements.txt):
  `gunicorn -w 4 -b 0.0.0.0:5000 app:app`
- Restrict all four Google/OpenWeather keys as described above.
- Uploaded documents (`backend/uploads/`) are stored unencrypted on disk — move to
  object storage (S3-compatible) with signed URLs before handling real driver PII.
- Set `CORS_ORIGINS` (comma-separated) to your real frontend origin(s) — the API blocks all
  browser origins by default in production if this is unset, rather than allowing everything.
- Set `RATELIMIT_STORAGE_URI` to a Redis URL if running more than one worker/instance — the
  default in-memory rate-limit store is per-process and won't be shared across workers.
- Set `LOG_FORMAT=json` for structured, machine-parseable log lines (one JSON object per line)
  suited to log aggregation tools (CloudWatch/Datadog/ELK/etc). Defaults to human-readable text.
- Account lockout: 5 failed login attempts locks that account for 15 minutes, independent of
  the IP-based rate limit on `/auth/login` — tune `LOCKOUT_THRESHOLD`/`LOCKOUT_MINUTES` in
  `routes/auth.py` if needed.
- Carbon methodology: a new emission-factor version is created (never edits an existing one)
  via `POST /api/v1/admin/carbon-methodologies` and switched on with
  `POST /api/v1/admin/carbon-methodologies/<id>/activate` (SuperAdmin only) — see
  `HARDENING_CHANGELOG.md` for the full rationale.

## Priority 1 improvements (this pass)

A follow-up pass implementing the 10 "Priority 1" items against the existing app,
without touching UI theme, folder structure, existing endpoints, or the ML pipeline's
overall shape. Summary of what changed and how to use it:

### 1. Security
- `.gitignore` now actually excludes `.env`/`backend/.env` (it previously didn't).
- `backend/.env.example` lists every env var the backend reads — copy to `backend/.env`
  and fill in real values.
- `backend/errors.py`: centralized error handling. Every `/api/*` error now returns
  `{"success": false, "error": "...", "code": "..."}` — `error` stays a string (not a
  nested object) so it's backward compatible with the existing frontend, which reads
  `err.response.data.error` as a string everywhere.
- `backend/validators.py`: shared input validation (email, phone, username, password,
  vehicle number, lat/lng bounds, etc.), applied to vehicle CRUD, admin creation, trip
  creation, and GPS pings. Admin `role` is now locked to `Admin`/`SuperAdmin` (previously
  accepted any string — a privilege-escalation gap).

### 2. Automated testing
- `backend/tests/` — 114 pytest tests covering registration, OTP, login/JWT, driver
  approval, vehicle CRUD, trip CRUD, prediction API, reports, GPS tracking, route
  deviation, model registry, invalid/unauthorized/validation-error cases.
- Run: `cd backend && pip install -r requirements.txt --break-system-packages && pytest`
- Tests run against an isolated in-memory SQLite DB (`config.TestConfig`) — they never
  touch your real `carbon_logistics.db` or the real `ml/saved/*.pkl` model files.

### 3. Real GPS tracking
- Already implemented in the codebase you uploaded (`navigator.geolocation.watchPosition`
  → `POST /api/v1/driver/trips/:id/location` → `TripLocation` table → Admin Live Fleet).
  This pass added: `speed_kmph` to the ping payload/table/UI, stricter lat/lng validation,
  a same-driver/same-trip-status ownership check on pings, and a `driver_id` column on
  `TripLocation` (denormalized, matching the brief's field list) for querying without a join.

### 4. Route deviation detection
- Threshold lowered to the specified 400m (was 700m).
- New `RouteDeviation` table: Trip, Driver, Lat/Lng, Deviation Distance, Detected Time,
  Status (Active/Resolved) — `GET /api/v1/admin/route-deviations`,
  `POST /api/v1/admin/route-deviations/<id>/resolve`. Auto-resolves on reroute or trip end.
  Shown as a live panel on the Admin Live Fleet page.

### 5. OTP
- Phone OTP removed (no SMS provider configured) — email-only, enforced server-side and
  in the Register UI.
- Hashed storage (bcrypt, never plaintext), 5-minute expiry, max 5 verify attempts, 60s
  cooldown between requests per identifier.

### 6. Maintenance model
- New realistic features: vehicle age, total km, service count, days since service,
  previous breakdown, fuel efficiency drop %, maintenance cost — see
  `backend/ml/vehicle_features.py`.
- `Vehicle` gained real history columns (`purchase_date`, `total_km`, `last_service_date`,
  `service_count`, `breakdown_count`, `maintenance_cost_total`); new `ServiceRecord` table
  + `POST/GET /api/v1/admin/vehicles/<id>/service-records` for admins to log real service
  events, which roll straight into the next prediction for that vehicle.
- `backend/data/generate_maintenance_history.py` bootstraps realistic history onto the
  seeded CSV dataset (run once, then `python3 ml/train.py`).
- Retrained: **87.5% accuracy, 0.880 precision, 0.875 recall, 0.871 F1** (weighted;
  Low/Medium/High). Full confusion matrix + per-class report saved to
  `ml/saved/maintenance_model_metrics.json` on every train/retrain.

### 7. Route recommendation
- `GET /api/v1/external/routes` now also returns `traffic_delay_ratio` (live vs. free-flow
  duration for that specific route) and a `road_type` proxy (Highway/Mixed/Surface
  streets, from average speed). "Eco" route selection now weighs distance against
  current congestion, not raw distance alone.
- New Trip page shows an explanation banner: *"Eco Route saves X% fuel and Y% CO2 — only
  Z min extra vs. Fastest."* (computed from the existing per-route AI fuel/CO2 estimates).

### 8. Model versioning
- New `ModelVersion` table + `backend/ml/registry.py`: every retrain snapshots each of
  the 5 trained models to `ml/saved/versions/{model}_v{N}.pkl` and only activates it if
  its metric actually beats the currently active version (lower MAE for regressors,
  higher accuracy for the two classifiers) — a worse retrain never silently replaces a
  better live model.
- `GET /api/v1/admin/ml/models` — version history + active flag per model.
- `POST /api/v1/admin/ml/models/<model_name>/rollback/<version_id>` (SuperAdmin-only) —
  reactivates any past version on demand.

### 9 & 10. Input validation / global error handling
Covered above under Security — `backend/validators.py` and `backend/errors.py`.

### Database schema changes
New tables: `route_deviations`, `service_records`, `model_versions`.
New columns: `vehicles` (purchase_date, total_km, last_service_date, service_count,
breakdown_count, maintenance_cost_total), `trip_locations` (driver_id, speed_kmph),
`otps` (code_hash replacing the old plaintext `code`, attempts).
New indexes on most foreign-key columns. New CHECK constraints on `vehicles`, `trips`,
`trip_locations`, `route_deviations`, `service_records` (SQLite can't add CHECK
constraints to existing tables via ALTER TABLE, so on a database that already existed
before this pass, those same rules are enforced at the API layer via
`backend/validators.py` instead — the guarantee holds either way).

### Migration steps

**Local development**: nothing manual needed — starting the backend (`python3 app.py`)
with `DEV_MODE=true` (the default) runs `_auto_migrate()`, which adds any new
columns/indexes to your existing `carbon_logistics.db` automatically.

**Production**: schema changes are managed with Flask-Migrate/Alembic
(`backend/migrations/`), not by the dev-only auto-migrate shim above — set
`DEV_MODE=false` in production and the app will *not* touch the schema on startup.
Run migrations as an explicit release step instead:
```bash
cd backend
flask db upgrade          # apply any pending migrations to DATABASE_URL
```
When you change a model in `backend/models/db.py`, generate the migration that captures
the diff, review the generated file, then commit it alongside the model change:
```bash
flask db migrate -m "describe your schema change"
flask db upgrade           # apply it locally to verify it works before committing
```
`backend/migrations/versions/` currently has two migrations: `7b407f21957a_initial_schema.py`
(everything through the audit-log/pagination/fuel-price hardening pass) and
`2d0604717a0a_add_idempotency_records_table.py` (the idempotency-key table). Treat these as
the source of truth for production schema history going forward — don't hand-edit the
database and don't rely on `_auto_migrate()` outside local dev.

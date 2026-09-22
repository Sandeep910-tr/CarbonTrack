# CarbonTrack — Multilingual Support (i18n)

## Supported languages
English (`en`), Kannada (`kn`), Hindi (`hi`), Tamil (`ta`), Telugu (`te`), Malayalam (`ml`), Marathi (`mr`).

## How it works
- Built on `react-i18next` + `i18next-browser-languagedetector`.
- Bootstrap: `frontend/src/i18n/index.js` — registers all 7 languages, sets `fallbackLng: "en"`, and wires a custom `localStorage` detector (`carbontrack_language` key) so a saved choice survives refresh/logout and unsupported/missing values silently fall back to English (never a raw `namespace.key` string).
- Translation files: `frontend/src/i18n/locales/<code>/translation.json`, one per language, all with **identical key structures** (verified programmatically — 653 keys, zero drift).
- `LanguageSelector.jsx` is the switcher UI (glass dropdown matching the app's dark/amber theme). It's mounted in the sidebar footer, the mobile top bar, and both auth screens. Selecting a language calls `i18n.changeLanguage()` — no reload, no state reset, no logout.
- Every page/component that renders user-facing text imports `useTranslation()` and calls `t("namespace.key")`. Numbers, currency, IDs, coordinates, and API payload fields are never passed through `t()`.

## Adding a new language
1. Add the code to `SUPPORTED_LANGUAGES` in `i18n/index.js`.
2. Copy `locales/en/translation.json` to `locales/<code>/translation.json` and translate every value (keep keys identical).
3. Import and register the new resource in `i18n/index.js`.
4. No other code changes needed — every screen already reads through `t()`.

## Adding a new translation key
Add the key to `locales/en/translation.json` first, then add the same key (translated) to all 6 other files. A CI-friendly check for this already exists — see the key-diff script used during development (flattens every `translation.json` and diffs the key sets against `en`).

## What's covered
Auth (login/register/OTP), navigation, driver dashboard + trip lifecycle (new trip, live route/AI-prediction, ongoing trip, **end-trip confirmation**, notifications, history), the Fleet AI Assistant's UI chrome, and the full admin console (overview, drivers, vehicles, depots, trips, live fleet map, reports, EV planning, settings, admin accounts, diagnostics, notifications).

## Known follow-ups (not yet localized)
- **Backend-generated strings** — a few endpoints return English text directly (AI Assistant replies, admin insights, notification messages, diagnostics detail text). Each spot is marked in the code with a comment. The recommended fix per the brief (§20): switch these endpoints to return stable `code` fields, add a matching key under a `backend` namespace in each `translation.json`, and translate client-side — the same pattern used everywhere else in this app.
- Date/number locale formatting (e.g. `toLocaleDateString()`) currently always uses the browser default locale rather than the selected app language; wiring `i18n.language` into those calls is a small follow-up.

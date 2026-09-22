# CarbonTrack changes

## 1. Google Maps / navigation forced to English
- Google Maps JavaScript loader now requests `language=en` and `region=IN`.
- Google Routes API now sends `languageCode: "en"` so turn-by-turn instructions are returned in English.
- Google Places Nearby requests English place names.
- Google Geocoding requests English results.

## 2. Live OpenWeather replaces manual/runtime weather
- Trip planning now fetches current weather from the Flask `/external/weather` proxy using the selected pickup coordinates.
- The weather selector was removed from the trip workflow.
- Live temperature, humidity, wind, and normalized weather condition are shown in the UI.
- Route CO2 estimates and final AI prediction use the live OpenWeather values.
- Active-trip weather refresh continues to use the driver's current GPS position.
- `Weather_History.csv` remains available for ML training only; it is not used as the runtime source of current weather.
- The backend OpenWeather response now includes a normalized CarbonTrack weather class plus source metadata.

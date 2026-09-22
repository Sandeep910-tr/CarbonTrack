import time
import requests
from flask import Blueprint, request, jsonify, current_app
from extensions import limiter
from geo_search import search_places

external_bp = Blueprint("external", __name__)

# Section 12 (OpenWeather): tiny in-process TTL cache keyed by rounded
# lat/lon (or city) - repeated calls for the same spot within the window
# (e.g. a driver's dashboard polling weather every N seconds while planning
# a trip) hit this instead of OpenWeather every time. Per-process only (see
# extensions.py note on RATELIMIT_STORAGE_URI for the same caveat at scale);
# fine for a single-worker deploy, swap for Redis if you scale out.
_weather_cache = {}
WEATHER_CACHE_TTL_SECONDS = 300


def _weather_cache_get(key):
    entry = _weather_cache.get(key)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        _weather_cache.pop(key, None)
        return None
    return value


def _weather_cache_set(key, value):
    _weather_cache[key] = (value, time.time() + WEATHER_CACHE_TTL_SECONDS)
    if len(_weather_cache) > 500:  # crude bound so this never grows unbounded
        _weather_cache.pop(next(iter(_weather_cache)))


# Section 11 (Google Routes) / Section 9-ish (Places): generic small
# in-process TTL cache, same rationale as the weather cache above. Separate
# namespaces + TTLs per endpoint since they have very different freshness
# needs: geocoding an address is effectively static (a street address
# doesn't move), route computation is traffic-aware and should only be
# cached briefly, nearby-places results change slowly.
_generic_cache = {}
GEOCODE_CACHE_TTL_SECONDS = 24 * 60 * 60   # addresses don't move
ROUTES_CACHE_TTL_SECONDS = 45              # short - this is TRAFFIC_AWARE, don't serve stale traffic data
PLACES_CACHE_TTL_SECONDS = 10 * 60


def _cache_get(namespace, key):
    entry = _generic_cache.get((namespace, key))
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        _generic_cache.pop((namespace, key), None)
        return None
    return value


def _cache_set(namespace, key, value, ttl_seconds):
    _generic_cache[(namespace, key)] = (value, time.time() + ttl_seconds)
    if len(_generic_cache) > 2000:
        _generic_cache.pop(next(iter(_generic_cache)))


@external_bp.route("/config/maps-key", methods=["GET"])
def maps_key():
    """The Maps JavaScript API key must be usable client-side to render the map.
    It should be restricted to your domain via HTTP referrer restrictions in the
    Google Cloud Console - this endpoint does not expose the Routes/Places keys."""
    return jsonify({"key": current_app.config["GOOGLE_MAPS_API_KEY"]})


@external_bp.route("/weather", methods=["GET"])
@limiter.limit("60/minute")
def weather():
    """C3. OpenWeather API - server-side proxy so the key never reaches the browser."""
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    city = request.args.get("city")
    key = current_app.config["OPENWEATHER_API_KEY"]
    if not key:
        return jsonify({"error": "OpenWeather API key not configured"}), 500

    if lat and lon:
        try:
            cache_key = f"{round(float(lat), 2)},{round(float(lon), 2)}"
        except (TypeError, ValueError):
            return jsonify({"error": "lat/lon must be valid numbers"}), 400
    elif city:
        cache_key = f"city:{city.strip().lower()}"
    else:
        return jsonify({"error": "Provide lat/lon or city"}), 400

    cached = _weather_cache_get(cache_key)
    if cached is not None:
        return jsonify({**cached, "cached": True})

    params = {"appid": key, "units": "metric"}
    if lat and lon:
        params.update({"lat": lat, "lon": lon})
    else:
        params["q"] = city

    try:
        r = requests.get("https://api.openweathermap.org/data/2.5/weather", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        raw_condition = data.get("weather", [{}])[0].get("main", "Clear")
        normalized = {
            "Clear": "Clear",
            "Clouds": "Cloudy",
            "Rain": "Rain",
            "Drizzle": "Rain",
            "Fog": "Fog",
            "Mist": "Fog",
            "Haze": "Fog",
            "Smoke": "Fog",
            "Dust": "Fog",
            "Sand": "Fog",
            "Ash": "Fog",
            "Thunderstorm": "Storm",
            "Squall": "Storm",
            "Tornado": "Storm",
            "Snow": "Rain",
        }.get(raw_condition, "Cloudy")
        result = {
            "condition": raw_condition,
            "carbontrack_condition": normalized,
            "description": data.get("weather", [{}])[0].get("description", ""),
            "temperature": data.get("main", {}).get("temp"),
            "humidity": data.get("main", {}).get("humidity"),
            "wind_kmph": round((data.get("wind", {}).get("speed", 0)) * 3.6, 1),
            "city": data.get("name"),
            "source": "OpenWeather",
            "observed_at": data.get("dt"),
        }
        _weather_cache_set(cache_key, result)
        return jsonify(result)
    except requests.Timeout:
        return jsonify({"error": "Weather service timed out. Please try again."}), 504
    except requests.RequestException as e:
        return jsonify({"error": f"Weather service unavailable: {e}"}), 502


WEATHER_CONDITION_NORMALIZE = {
    "Clear": "Clear",
    "Clouds": "Cloudy",
    "Rain": "Rain",
    "Drizzle": "Rain",
    "Fog": "Fog",
    "Mist": "Fog",
    "Haze": "Fog",
    "Smoke": "Fog",
    "Dust": "Fog",
    "Sand": "Fog",
    "Ash": "Fog",
    "Thunderstorm": "Storm",
    "Squall": "Storm",
    "Tornado": "Storm",
    "Snow": "Rain",
}

# Severity ranking used to pick a single "representative" condition for an
# area out of several sample points, and to decide whether the driver should
# see a severe-weather warning. Higher = more severe.
WEATHER_SEVERITY_RANK = {
    "Storm": 5,
    "Rain": 4,
    "Fog": 3,
    "Cloudy": 2,
    "Clear": 1,
}
SEVERE_CONDITIONS = {"Storm", "Rain", "Fog"}

AREA_WEATHER_DEFAULT_RADIUS_KM = 5
AREA_WEATHER_MIN_RADIUS_KM = 2
AREA_WEATHER_MAX_RADIUS_KM = 5
AREA_WEATHER_CACHE_TTL_SECONDS = 300


def _offset_point(lat, lon, radius_km, bearing_deg):
    """Returns a (lat, lon) point `radius_km` away from (lat, lon) along
    `bearing_deg` (0=N, 90=E, 180=S, 270=W), using a simple equirectangular
    approximation - plenty accurate at a 2-5km scale for weather sampling."""
    import math
    R = 6371.0  # Earth radius km
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    ang_dist = radius_km / R
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(ang_dist) + math.cos(lat_rad) * math.sin(ang_dist) * math.cos(bearing_rad)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(ang_dist) * math.cos(lat_rad),
        math.cos(ang_dist) - math.sin(lat_rad) * math.sin(new_lat_rad),
    )
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)


def _fetch_openweather_point(lat, lon, key):
    """Single-point OpenWeather fetch, going through the same per-point cache
    used by /external/weather so area sampling doesn't multiply API usage
    when points overlap between nearby requests."""
    cache_key = f"{round(lat, 2)},{round(lon, 2)}"
    cached = _weather_cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"appid": key, "units": "metric", "lat": lat, "lon": lon},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        raw_condition = data.get("weather", [{}])[0].get("main", "Clear")
        result = {
            "condition": raw_condition,
            "carbontrack_condition": WEATHER_CONDITION_NORMALIZE.get(raw_condition, "Cloudy"),
            "description": data.get("weather", [{}])[0].get("description", ""),
            "temperature": data.get("main", {}).get("temp"),
            "humidity": data.get("main", {}).get("humidity"),
            "wind_kmph": round((data.get("wind", {}).get("speed", 0)) * 3.6, 1),
            "city": data.get("name"),
            "source": "OpenWeather",
            "observed_at": data.get("dt"),
        }
        _weather_cache_set(cache_key, result)
        return result
    except requests.RequestException:
        return None


@external_bp.route("/weather/area", methods=["GET"])
@limiter.limit("60/minute")
def weather_area():
    """Section 12/13/14 (area weather): weather CONDITIONS AROUND a point
    within a configurable 2-5km radius, not just the single exact coordinate.

    Samples the center plus North/South/East/West points at `radius_km`,
    fetches each (via the per-point cache so repeat/overlapping requests
    stay cheap), and aggregates them so a driver isn't told "Clear" just
    because the exact GPS pixel they're standing on happens to be dry while
    rain is bearing down from the next street over.
    """
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    radius_param = request.args.get("radius_km")
    key = current_app.config["OPENWEATHER_API_KEY"]
    if not key:
        return jsonify({"error": "OpenWeather API key not configured"}), 500
    if not lat or not lon:
        return jsonify({"error": "lat and lon are required"}), 400
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "lat/lon must be valid numbers"}), 400

    if radius_param is None or radius_param == "":
        radius_km = AREA_WEATHER_DEFAULT_RADIUS_KM
    else:
        try:
            radius_km = float(radius_param)
        except (TypeError, ValueError):
            return jsonify({"error": "radius_km must be a valid number"}), 400
    # Clamp rather than reject - a driver-supplied radius slightly outside
    # bounds shouldn't break trip planning, it should just be normalized.
    radius_km = max(AREA_WEATHER_MIN_RADIUS_KM, min(AREA_WEATHER_MAX_RADIUS_KM, radius_km))

    area_cache_key = (round(lat_f, 2), round(lon_f, 2), round(radius_km, 1))
    cached = _cache_get("area_weather", area_cache_key)
    if cached is not None:
        return jsonify({**cached, "cached": True})

    # Center + the 4 cardinal points. (Diagonal points are intentionally
    # omitted - 5 samples already gives a meaningful area picture without
    # over-spending API calls on every trip-planning/GPS-refresh tick.)
    sample_points = [("center", lat_f, lon_f)]
    for label, bearing in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        s_lat, s_lon = _offset_point(lat_f, lon_f, radius_km, bearing)
        sample_points.append((label, s_lat, s_lon))

    samples = []
    for label, s_lat, s_lon in sample_points:
        point = _fetch_openweather_point(s_lat, s_lon, key)
        if point:
            samples.append({**point, "_label": label})

    if not samples:
        return jsonify({"error": "Weather service unavailable for this area. Please try again shortly."}), 502

    # --- Aggregation (Section 14) ---
    temps = [s["temperature"] for s in samples if s.get("temperature") is not None]
    humidities = [s["humidity"] for s in samples if s.get("humidity") is not None]
    winds = [s["wind_kmph"] for s in samples if s.get("wind_kmph") is not None]
    avg_temp = round(sum(temps) / len(temps), 1) if temps else None
    avg_humidity = round(sum(humidities) / len(humidities)) if humidities else None
    avg_wind = round(sum(winds) / len(winds), 1) if winds else None

    # Representative condition = the most SEVERE condition seen anywhere in
    # the sampled area, not the center point or a majority vote - per
    # Section 14/15, a storm one sample away must not be hidden just
    # because the center is clear.
    center_sample = next((s for s in samples if s["_label"] == "center"), samples[0])
    most_severe = max(samples, key=lambda s: WEATHER_SEVERITY_RANK.get(s["carbontrack_condition"], 0))
    representative_condition = most_severe["carbontrack_condition"]
    severe_weather = representative_condition in SEVERE_CONDITIONS

    area_alert = None
    if severe_weather:
        if representative_condition == "Storm":
            area_alert = f"Storm conditions detected within {radius_km:.0f} km"
        elif representative_condition == "Rain":
            area_alert = f"Rain detected within {radius_km:.0f} km"
        elif representative_condition == "Fog":
            area_alert = f"Fog reported within {radius_km:.0f} km"

    result = {
        "radius_km": radius_km,
        "temperature": avg_temp,
        "humidity": avg_humidity,
        "wind_kmph": avg_wind,
        "condition": most_severe["condition"],
        "carbontrack_condition": representative_condition,
        "description": center_sample.get("description", ""),
        "city": center_sample.get("city"),
        "area_alert": area_alert,
        "severe_weather": severe_weather,
        "sample_count": len(sample_points),
        "successful_samples": len(samples),
        "source": "OpenWeather",
        "updated_at": center_sample.get("observed_at"),
    }
    _cache_set("area_weather", area_cache_key, result, AREA_WEATHER_CACHE_TTL_SECONDS)
    return jsonify(result)


@external_bp.route("/geocode", methods=["GET"])
@limiter.limit("60/minute")
def geocode():
    """Resolves a free-text address to lat/lng using Google Geocoding API.
    Used to plot simulated live positions and to anchor the Routes API call."""
    address = request.args.get("address")
    key = current_app.config["GOOGLE_MAPS_API_KEY"]
    if not key:
        return jsonify({"error": "Google Maps API key not configured"}), 500
    if not address:
        return jsonify({"error": "address is required"}), 400

    cache_key = address.strip().lower()
    cached = _cache_get("geocode", cache_key)
    if cached is not None:
        return jsonify({**cached, "cached": True})

    try:
        r = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                          params={"address": address, "key": key, "language": "en", "region": "in"}, timeout=10)
        r.raise_for_status()
        body = r.json()
        status = body.get("status")
        if status != "OK":
            # Google returns HTTP 200 even for key/permission errors - the real
            # failure reason is in this "status" field, not the HTTP code.
            hint = _google_status_hint(status, "Geocoding API")
            return jsonify({"error": f"Geocoding failed: {status}. {hint}",
                             "google_error_message": body.get("error_message")}), 502
        results = body.get("results", [])
        loc = results[0]["geometry"]["location"]
        result = {"lat": loc["lat"], "lng": loc["lng"], "formatted_address": results[0].get("formatted_address")}
        _cache_set("geocode", cache_key, result, GEOCODE_CACHE_TTL_SECONDS)
        return jsonify(result)
    except requests.RequestException as e:
        return jsonify({"error": f"Geocoding service unavailable: {e}"}), 502


def _google_status_hint(status, api_name):
    """Translates Google's opaque status codes into an actionable hint."""
    hints = {
        "REQUEST_DENIED": f'The key is missing permission for "{api_name}" — enable it in Google Cloud Console under APIs & Services > Library, or check the key\'s API restrictions list includes it.',
        "OVER_QUERY_LIMIT": "You've hit the API's quota or billing isn't enabled on this Google Cloud project.",
        "INVALID_REQUEST": "The request was malformed — check the address/parameters being sent.",
        "ZERO_RESULTS": "Google found no results for that input — try a more specific address.",
        "UNKNOWN_ERROR": "A transient error on Google's end — try again.",
    }
    return hints.get(status, "Check the key's restrictions and that billing is enabled on the Google Cloud project.")


@external_bp.route("/routes", methods=["GET"])
@limiter.limit("30/minute")
def routes():
    """C2. Google Routes API - computes route options (Eco/Shortest/Fastest) server-side.

    Accepts either address text (origin/destination) or raw coordinates
    (origin_lat/origin_lng, dest_lat/dest_lng). Coordinates take priority when
    both are given — used for automatic rerouting from the driver's live GPS
    position, where re-geocoding an address string would be slower and less
    precise than just using the fix we already have."""
    origin = request.args.get("origin")
    destination = request.args.get("destination")
    origin_lat, origin_lng = request.args.get("origin_lat"), request.args.get("origin_lng")
    dest_lat, dest_lng = request.args.get("dest_lat"), request.args.get("dest_lng")
    key = current_app.config["GOOGLE_ROUTES_API_KEY"]
    if not key:
        return jsonify({"error": "Google Routes API key not configured"}), 500
    if not ((origin_lat and origin_lng) or origin) or not ((dest_lat and dest_lng) or destination):
        return jsonify({"error": "origin and destination (address or lat/lng) are required"}), 400

    def _round(v):
        try:
            return round(float(v), 4)  # ~11m precision - close enough to dedupe repeat requests
        except (TypeError, ValueError):
            return v

    cache_key = (
        (origin or "").strip().lower(), (destination or "").strip().lower(),
        _round(origin_lat), _round(origin_lng), _round(dest_lat), _round(dest_lng),
    )
    cached = _cache_get("routes", cache_key)
    if cached is not None:
        return jsonify({**cached, "cached": True})

    def _location(addr, lat, lng):
        if lat and lng:
            return {"location": {"latLng": {"latitude": float(lat), "longitude": float(lng)}}}
        return {"address": addr}

    body = {
        "origin": _location(origin, origin_lat, origin_lng),
        "destination": _location(destination, dest_lat, dest_lng),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "units": "METRIC",
        # Force English route/navigation instructions regardless of the
        # driver's browser/device locale.
        "languageCode": "en",
    }
    current_app.logger.info(
        "Routes API request — origin: %s, destination: %s",
        body["origin"], body["destination"],
    )
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters,routes.polyline.encodedPolyline,"
                             "routes.legs.steps.navigationInstruction.instructions,"
                             "routes.legs.steps.distanceMeters,routes.legs.steps.staticDuration,"
                             "routes.legs.steps.startLocation,routes.legs.steps.endLocation",
    }
    try:
        r = requests.post("https://routes.googleapis.com/directions/v2:computeRoutes",
                           json=body, headers=headers, timeout=15)
        if not r.ok:
            try:
                err_body = r.json().get("error", {})
                msg = err_body.get("message", r.text[:200])
                err_status = err_body.get("status", str(r.status_code))
            except Exception:
                msg, err_status = r.text[:200], str(r.status_code)
            hint = _google_status_hint(err_status, "Routes API")
            return jsonify({"error": f"Routes API error ({err_status}): {msg}. {hint}"}), 502
        raw = r.json().get("routes", [])
        # Label routes by relative characteristics rather than assuming API order:
        # shortest distance = "Eco", shortest duration = "Fastest", the rest = "Shortest"/"Alt N"
        parsed = []
        for route in raw[:4]:
            duration_s = int(str(route.get("duration", "0s")).rstrip("s"))
            static_duration_s = int(str(route.get("staticDuration", duration_s)).rstrip("s")) or duration_s
            distance_km = round(route.get("distanceMeters", 0) / 1000, 2)
            # Traffic delay ratio: how much slower this route is right now vs.
            # its own free-flow time (>1.0 means real congestion on this
            # route specifically, not just "traffic is bad everywhere").
            traffic_delay_ratio = round(duration_s / static_duration_s, 2) if static_duration_s else 1.0
            # Road-type proxy: Google Routes v2 doesn't break routes down by
            # road classification in this field mask, but average speed is a
            # reasonable stand-in - a route averaging 70+ km/h is
            # highway-dominated, one averaging under 25 km/h is mostly
            # surface streets, which is exactly the kind of distinction
            # "road type" is meant to capture for fuel/CO2 purposes.
            avg_speed_kmph = round(distance_km / (duration_s / 3600), 1) if duration_s else 0
            road_type = "Highway" if avg_speed_kmph >= 55 else "Mixed" if avg_speed_kmph >= 30 else "Surface streets"
            # Turn-by-turn steps come straight from Routes API v2 (already confirmed
            # working) instead of the separate legacy Directions API that
            # google.maps.DirectionsService depends on - avoids needing yet another
            # API enabled in Cloud Console just for navigation instructions.
            steps = []
            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    instruction = step.get("navigationInstruction", {}).get("instructions")
                    if not instruction:
                        continue
                    step_duration_s = int(str(step.get("staticDuration", "0s")).rstrip("s"))
                    start_ll = step.get("startLocation", {}).get("latLng")
                    end_ll = step.get("endLocation", {}).get("latLng")
                    steps.append({
                        "instruction": instruction,
                        "distance_km": round(step.get("distanceMeters", 0) / 1000, 2),
                        "duration_min": round(step_duration_s / 60, 1),
                        "start_lat": start_ll.get("latitude") if start_ll else None,
                        "start_lng": start_ll.get("longitude") if start_ll else None,
                        "end_lat": end_ll.get("latitude") if end_ll else None,
                        "end_lng": end_ll.get("longitude") if end_ll else None,
                    })
            parsed.append({
                "distance_km": distance_km,
                "duration_min": round(duration_s / 60, 1),
                "polyline": route.get("polyline", {}).get("encodedPolyline"),
                "steps": steps,
                "traffic_delay_ratio": traffic_delay_ratio,
                "avg_speed_kmph": avg_speed_kmph,
                "road_type": road_type,
            })
        if parsed:
            fastest_idx = min(range(len(parsed)), key=lambda i: parsed[i]["duration_min"])
            # "Eco" = best distance once adjusted for how congested that route
            # currently is - congestion means idling/stop-start driving, which
            # burns noticeably more fuel per km than the same distance covered
            # at a steady speed, so picking on raw distance alone can miss that.
            eco_idx = min(range(len(parsed)),
                          key=lambda i: parsed[i]["distance_km"] * (1 + 0.15 * max(parsed[i]["traffic_delay_ratio"] - 1, 0)))
            for i, p in enumerate(parsed):
                if i == fastest_idx and i == eco_idx:
                    p["label"] = "Fastest & Eco"
                elif i == fastest_idx:
                    p["label"] = "Fastest"
                elif i == eco_idx:
                    p["label"] = "Eco"
                else:
                    p["label"] = "Shortest" if p["distance_km"] == min(x["distance_km"] for x in parsed) else f"Alternative {i+1}"
        else:
            return jsonify({"error": "Google Routes API returned no routes for that origin/destination. Double-check both addresses are valid and resolvable."}), 404
        result = {"routes": parsed}
        _cache_set("routes", cache_key, result, ROUTES_CACHE_TTL_SECONDS)
        return jsonify(result)
    except requests.RequestException as e:
        return jsonify({"error": f"Routes service unavailable: {e}"}), 502


@external_bp.route("/places/nearby", methods=["GET"])
@limiter.limit("30/minute")
def places_nearby():
    """C4. Google Places API - fuel stations, repair shops, hospitals, rest areas.
    Uses Places API (New) - Google's legacy Places endpoint requires separately
    enabling a deprecated API that new Cloud projects don't have by default and
    that Google is phasing out, so this calls the current one instead."""
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    place_type = request.args.get("type", "gas_station")
    key = current_app.config["GOOGLE_PLACES_API_KEY"]
    if not key:
        return jsonify({"error": "Google Places API key not configured"}), 500
    if not lat or not lon:
        return jsonify({"error": "lat and lon are required"}), 400
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon must be valid numbers"}), 400

    cache_key = (round(lat_f, 3), round(lon_f, 3), place_type)  # ~110m precision
    cached = _cache_get("places", cache_key)
    if cached is not None:
        return jsonify({**cached, "cached": True})

    try:
        r = requests.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            json={
                "includedTypes": [place_type],
                "maxResultCount": 10,
                "languageCode": "en",
                "locationRestriction": {
                    "circle": {"center": {"latitude": float(lat), "longitude": float(lon)}, "radius": 5000.0}
                },
            },
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.location",
            },
            timeout=10,
        )
        if not r.ok:
            try:
                err = r.json().get("error", {})
                msg, err_status = err.get("message", r.text[:150]), err.get("status", str(r.status_code))
            except ValueError:
                msg, err_status = r.text[:150], str(r.status_code)
            hint = _google_status_hint(err_status, "Places API (New)")
            return jsonify({"error": f"Places lookup failed ({err_status}): {msg}. {hint}"}), 502

        results = r.json().get("places", [])
        places = [{
            "name": p.get("displayName", {}).get("text"),
            "address": p.get("formattedAddress"),
            "rating": p.get("rating"),
            "lat": p.get("location", {}).get("latitude"),
            "lon": p.get("location", {}).get("longitude"),
        } for p in results[:10]]
        result = {"places": places}
        _cache_set("places", cache_key, result, PLACES_CACHE_TTL_SECONDS)
        return jsonify(result)
    except requests.RequestException as e:
        return jsonify({"error": f"Places service unavailable: {e}"}), 502


@external_bp.route("/places/suggest", methods=["GET"])
@limiter.limit("120/minute")
def places_suggest():
    """City/village name autocomplete for the pickup & destination fields on
    the driver's New Trip form (see PlaceAutocomplete.jsx).

    This does NOT call the Google Places API - it searches a bundled
    India state/district/village directory in-process (geo_search.py), so
    it costs nothing per keystroke and works even if the Places key isn't
    configured. Selecting a suggestion just fills in the text field; the
    address is still geocoded the normal way (via /external/geocode) when
    the driver submits the form."""
    q = request.args.get("q", "")
    try:
        limit = min(int(request.args.get("limit", 8)), 10)
    except (TypeError, ValueError):
        limit = 8
    return jsonify({"results": search_places(q, limit=limit)})

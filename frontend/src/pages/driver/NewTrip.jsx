import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Fuel, Leaf, DollarSign, Wrench, Gauge, CloudRain, CheckCircle2, Check, Navigation, MapPinned, Siren, AlertOctagon, LocateFixed, Milestone, Volume2, VolumeX, X, AlertTriangle, PartyPopper, Lock, LockOpen, MessageCircle, UserCog } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Select, Badge, StarRating, TextArea } from "../../components/ui";
import PlaceAutocomplete from "../../components/PlaceAutocomplete";
import { loadGoogleMaps } from "../../lib/googleMaps";
import { DARK_MAP_STYLE } from "../../lib/mapStyle";
import { enqueuePing, flushQueue, queueSize } from "../../lib/offlineQueue";
import useOnlineStatus from "../../hooks/useOnlineStatus";
import api from "../../lib/api";
import ReassignmentModal from "../../components/ReassignmentModal";
import ChatPanel from "../../components/ChatPanel";
import IsoTruckBadge from "../../components/IsoTruckBadge";

const TRAFFICS = ["Low", "Medium", "High"];

function normalizeWeather(data) {
  const condition = data?.carbontrack_condition || data?.condition || "Cloudy";
  return {
    condition,
    rawCondition: data?.condition || condition,
    description: data?.description || "",
    temperature: data?.temperature ?? null,
    humidity: data?.humidity ?? null,
    wind_kmph: data?.wind_kmph ?? null,
    city: data?.city || "Selected location",
    source: data?.source || "OpenWeather",
    observed_at: data?.observed_at || data?.updated_at || null,
    // Area-weather fields (Section 12-16): present when this came from
    // /external/weather/area, undefined for any older single-point response.
    radiusKm: data?.radius_km ?? null,
    areaAlert: data?.area_alert ?? null,
    severeWeather: !!data?.severe_weather,
    sampleCount: data?.sample_count ?? null,
    successfulSamples: data?.successful_samples ?? null,
  };
}

const AREA_WEATHER_DEFAULT_RADIUS_KM = 5; // Section 12 default; allowed range is 2-5km
const AREA_WEATHER_RADIUS_OPTIONS_KM = [2, 3, 4, 5];

function PredictionLoadingScreen({ t }) {
  const items = [
    t("newTrip.predictCheckVehicle", { defaultValue: "Vehicle efficiency" }),
    t("newTrip.predictCheckDistance", { defaultValue: "Route distance" }),
    t("newTrip.predictCheckWeather", { defaultValue: "Weather conditions" }),
    t("newTrip.predictCheckTraffic", { defaultValue: "Traffic conditions" }),
    t("newTrip.predictCheckHistory", { defaultValue: "Historical fleet data" }),
  ];
  return (
    <GlassCard strong className="p-10 text-center">
      <motion.div
        className="mx-auto mb-5 h-12 w-12 rounded-full border-2 border-amber/30 border-t-amber"
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, ease: "linear", duration: 1.1 }}
      />
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber">{t("newTrip.aiEngineName", { defaultValue: "CarbonTrack AI" })}</p>
      <p className="mt-1 font-display text-lg font-semibold text-ink">{t("newTrip.analyzingJourney", { defaultValue: "Analyzing your journey..." })}</p>
      <ul className="mx-auto mt-6 max-w-xs space-y-2.5 text-left text-sm">
        {items.map((label, i) => (
          <motion.li
            key={label}
            className="flex items-center gap-2.5 text-ink-dim"
            initial={{ opacity: 0.35 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.45, duration: 0.3 }}
          >
            <motion.span
              className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-success/40 text-success"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: i * 0.45 + 0.15, duration: 0.25 }}
            >
              <Check size={11} strokeWidth={3} />
            </motion.span>
            <span className="text-ink">{label}</span>
          </motion.li>
        ))}
      </ul>
    </GlassCard>
  );
}

const DEVIATION_THRESHOLD_M = 700; // how far off-route before we auto-recalculate
const STEP_ARRIVAL_RADIUS_M = 40;  // how close to a step's end point counts as "reached it"
const MAX_AUTO_REROUTES = 3;       // safety cap so noisy GPS can't loop-reroute forever

function stripTags(html) {
  return (html || "").replace(/<[^>]+>/g, "");
}

// Compares the route flagged "Eco" (or "Fastest & Eco") against whichever
// route is "Fastest", using the per-route AI fuel/CO2 estimates already
// fetched in fetchRouteEstimates. Returns null (rather than a 0%-savings
// banner) when there's nothing meaningfully different to report — e.g. only
// one route came back, or the "Eco" route IS the fastest one.
function computeEcoExplanation(routeOptions, routeEstimates) {
  const ecoIdx = routeOptions.findIndex((r) => r.label?.includes("Eco"));
  const fastestIdx = routeOptions.findIndex((r) => r.label?.includes("Fastest"));
  if (ecoIdx === -1 || fastestIdx === -1 || ecoIdx === fastestIdx) return null;
  const eco = routeEstimates[ecoIdx];
  const fastest = routeEstimates[fastestIdx];
  if (!eco || !fastest || !fastest.predicted_fuel_l || !fastest.predicted_co2_kg) return null;

  const fuelSavingsPct = Math.round(((fastest.predicted_fuel_l - eco.predicted_fuel_l) / fastest.predicted_fuel_l) * 100);
  const co2SavingsPct = Math.round(((fastest.predicted_co2_kg - eco.predicted_co2_kg) / fastest.predicted_co2_kg) * 100);
  const extraMin = Math.round((routeOptions[ecoIdx].duration_min - routeOptions[fastestIdx].duration_min) * 10) / 10;
  if (fuelSavingsPct <= 0 && co2SavingsPct <= 0) return null;

  return { fuelSavingsPct, co2SavingsPct, extraMin };
}

// Section 5: identifies which route is Fastest (lowest duration), Shortest
// (lowest distance), and Recommended (the "Eco" labeled route, or whichever
// has the lowest predicted CO2 if estimates are in) so the route list can
// tag each option instead of leaving the driver to compare numbers by eye.
function computeRouteBadges(routeOptions, routeEstimates) {
  if (!routeOptions.length) return {};
  const fastestIdx = routeOptions.reduce((best, r, i) => (r.duration_min < routeOptions[best].duration_min ? i : best), 0);
  const shortestIdx = routeOptions.reduce((best, r, i) => (r.distance_km < routeOptions[best].distance_km ? i : best), 0);
  let recommendedIdx = routeOptions.findIndex((r) => r.label?.includes("Eco"));
  if (recommendedIdx === -1) {
    const co2 = routeEstimates.map((e) => e?.predicted_co2_kg ?? Infinity);
    if (co2.some((v) => v !== Infinity)) {
      recommendedIdx = co2.reduce((best, v, i) => (v < co2[best] ? i : best), 0);
    }
  }
  return { fastestIdx, shortestIdx, recommendedIdx };
}

const PLACE_TYPES = [
  { type: "gas_station", labelKey: "newTrip.fuelStations" },
  { type: "car_repair", labelKey: "newTrip.repairShops" },
  { type: "hospital", labelKey: "newTrip.hospitals" },
  { type: "restaurant", labelKey: "newTrip.restAreas" },
];
const STEPS = [
  { key: "details", labelKey: "newTrip.stepDetails" },
  { key: "routes", labelKey: "newTrip.stepRoute" },
  { key: "review", labelKey: "newTrip.stepAiPrediction" },
  { key: "ongoing", labelKey: "newTrip.stepTrip" },
  { key: "summary", labelKey: "newTrip.stepSummary" },
];

export default function NewTrip() {
  const { t } = useTranslation();
  // stages: details -> routes -> predicting -> review -> ongoing -> summary
  const [stage, setStage] = useState("details");
  const [error, setError] = useState("");
  const [errorTraceback, setErrorTraceback] = useState(null);
  const [mapsKey, setMapsKey] = useState("");
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [liveWeather, setLiveWeather] = useState(null);
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routeOptions, setRouteOptions] = useState([]);
  const [routeEstimates, setRouteEstimates] = useState([]);
  const [estimatesLoading, setEstimatesLoading] = useState(false);
  const [chosenRouteIdx, setChosenRouteIdx] = useState(null);
  const [sosSent, setSosSent] = useState(false);
  const [deviationSent, setDeviationSent] = useState(false);
  const [places, setPlaces] = useState([]);
  const [placesType, setPlacesType] = useState("gas_station");
  const [placesLoading, setPlacesLoading] = useState(false);
  // Plain useRef doesn't work here: AnimatePresence's exit/enter animation
  // means the div for the new stage mounts on a later render than the one
  // where this effect's dependencies change, so navMapRef.current /
  // routeMapRef.current is still null when the effect body runs and the
  // effect never gets another chance to run (no state change to re-trigger
  // it). Storing the node in state via a callback ref fixes this: the
  // setState call fires exactly when the div mounts, which reruns the
  // effect with a non-null node.
  const [routeMapNode, setRouteMapNode] = useState(null);
  const [navMapNode, setNavMapNode] = useState(null);

  useEffect(() => {
    api.get("/external/config/maps-key").then((r) => setMapsKey(r.data.key)).catch(() => {});
  }, []);

  // Section 12: driver-configurable area-weather radius, 2-5km, default 5.
  // Kept in one place and threaded into every /external/weather/area call
  // (pickup weather, ongoing-trip refresh, and the GPS-fix-catchup fetch)
  // so there's a single source of truth for "how wide an area am I seeing".
  const [weatherRadiusKm, setWeatherRadiusKm] = useState(AREA_WEATHER_DEFAULT_RADIUS_KM);

  // Section 4: "See assigned vehicle information" on the New Trip screen.
  // Read-only display only — reuses the same /driver/profile endpoint the
  // Overview page already relies on, no new backend surface needed.
  const [driverVehicle, setDriverVehicle] = useState(null);
  useEffect(() => {
    api.get("/driver/profile").then((r) => setDriverVehicle(r.data?.vehicle || null)).catch(() => {});
  }, []);

  const [form, setForm] = useState({
    source: "", destination: "", load_kg: "", purpose: "Delivery", traffic: "Medium",
  });
  const [prediction, setPrediction] = useState(null);
  const [trip, setTrip] = useState(null);

  // ---- Active-trip restoration ----------------------------------------
  // The backend/database is the single source of truth for whether this
  // driver currently has a trip in progress — never React state, never
  // localStorage. On every mount (fresh load, refresh, or navigating back
  // to this page after leaving it) we ask the backend directly. If it
  // returns an Ongoing trip, we restore straight into the "ongoing" stage
  // so the driver always sees (and can end) their real active trip. If it
  // returns nothing, we start clean at "details" — we never assume an
  // empty local state means "no active trip" without checking first.
  const [restoringTrip, setRestoringTrip] = useState(true);
  // Section 15/16 (5km Destination Lock): the backend's authoritative view
  // of how far the driver is from the destination and whether End Trip is
  // currently allowed - refreshed from every location ping while ongoing,
  // and restored from GET /driver/active-trip on page load/reload so the
  // lock state is never just frontend-guessed.
  const [destStatus, setDestStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get("/driver/active-trip");
        if (cancelled) return;
        const active = res.data?.trip;
        if (active && active.status === "Ongoing") {
          setTrip(active);
          setStage("ongoing");
          if (res.data?.destination_status) setDestStatus(res.data.destination_status);
        }
      } catch (err) {
        console.error("Couldn't check for an active trip:", err);
      } finally {
        if (!cancelled) setRestoringTrip(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fallback view of the AI prediction for a restored trip, where the full
  // `prediction` object (only ever populated live, during the planning
  // flow) doesn't exist. Built from the persisted fields on the trip
  // itself so the ongoing/summary UI and End Trip flow never depend on
  // in-memory state that a page refresh would wipe out.
  const predictionView = prediction || (trip ? {
    predicted_fuel_l: trip.predicted_fuel_l,
    predicted_co2_kg: trip.predicted_co2_kg,
    predicted_cost: trip.predicted_cost,
    predicted_eco_score: trip.predicted_eco_score,
    maintenance_risk: trip.maintenance_risk,
    recommended_route: trip.recommended_route,
    ai_confidence: trip.ai_confidence,
    overall_score: trip.predicted_eco_score,
    weather_impact: null,
  } : null);

  // Source of truth for routing coordinates. Pickup/destination are typed
  // by the driver as plain text (form.source / form.destination) — these
  // two only get populated once, inside fetchRoutes, by silently resolving
  // that typed text through the backend geocoder right when "Get Route
  // Options" is clicked. Nothing before that point makes any network call.
  // The one exception is "current location" for pickup: that's a real GPS
  // fix, set immediately when the driver taps the button, not typed text.
  const [pickupPlace, setPickupPlace] = useState(null); // { placeId, formattedAddress, latitude, longitude } | null
  const [destinationPlace, setDestinationPlace] = useState(null);
  const [geocoding, setGeocoding] = useState(false);

  // Resolves free-typed address text to coordinates via the backend's
  // GET /external/geocode (server-side Google key). Returns
  // { formattedAddress, latitude, longitude } or null on failure — never
  // throws, so callers can just check the return value.
  async function geocodeAddress(address) {
    const trimmed = (address || "").trim();
    if (!trimmed) return null;
    try {
      const res = await api.get("/external/geocode", { params: { address: trimmed } });
      const { lat, lng, formatted_address } = res.data || {};
      if (lat == null || lng == null) return null;
      return { placeId: null, formattedAddress: formatted_address || trimmed, latitude: lat, longitude: lng };
    } catch {
      return null;
    }
  }
  const [pickupMode, setPickupMode] = useState("selected"); // "selected" | "current"
  const [locatingPickup, setLocatingPickup] = useState(false);

  function update(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function useCurrentLocationForPickup() {
    setLocatingPickup(true);
    setError("");
    try {
      const pos = await getPosition();
      const place = {
        placeId: null,
        formattedAddress: t("newTrip.currentLocation"),
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
      };
      setPickupMode("current");
      setPickupPlace(place);
      update("source", t("newTrip.currentLocation"));
    } catch (err) {
      setError(err.message || t("newTrip.couldNotReadLocation"));
    } finally {
      setLocatingPickup(false);
    }
  }

  function getPosition() {
    return new Promise((resolve, reject) => {
      if (!window.isSecureContext) {
        reject(new Error("Your device location only works on HTTPS pages or on http://localhost — you're viewing this over a plain IP address. Open this app via http://localhost:5000 on this machine, or set up HTTPS to use location on other devices."));
        return;
      }
      if (!navigator.geolocation) { reject(new Error("Geolocation isn't supported by this browser.")); return; }
      navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 8000 });
    });
  }

  async function fetchLiveWeather(lat, lon, { silent = false } = {}) {
    if (lat == null || lon == null) return null;
    if (!silent) {
      setWeatherLoading(true);
      setError("");
    }
    try {
      const res = await api.get("/external/weather/area", { params: { lat, lon, radius_km: weatherRadiusKm } });
      const weather = normalizeWeather(res.data);
      setLiveWeather(weather);
      setForm((f) => ({
        ...f,
        _live_temp: weather.temperature,
        _live_humidity: weather.humidity,
        _live_wind: weather.wind_kmph,
        _live_city: weather.city,
        _live_weather: weather.condition,
        _live_radius_km: weather.radiusKm,
        _live_area_alert: weather.areaAlert,
        _live_severe_weather: weather.severeWeather,
      }));
      return weather;
    } catch (err) {
      if (!silent) {
        setError(err.response?.data?.error || t("newTrip.couldNotFetchWeather"));
      }
      return null;
    } finally {
      if (!silent) setWeatherLoading(false);
    }
  }

  // Weather for trip planning comes from OpenWeather at the selected pickup
  // coordinates. The historical Weather_History.csv is never used as the
  // runtime source of current conditions.
  useEffect(() => {
    if (pickupPlace?.latitude == null || pickupPlace?.longitude == null) {
      // Keep existing weather when no pickup has been selected yet.
      return;
    }
    fetchLiveWeather(pickupPlace.latitude, pickupPlace.longitude);
  }, [pickupPlace?.latitude, pickupPlace?.longitude]);

  // --- Step: driver has typed source/destination as plain text (or used
  // "current location" for pickup). Clicking "Get Route Options" is the
  // single moment any of that gets resolved to coordinates — silently, via
  // the backend geocoder — before calling Google Routes. Nothing fires
  // while the driver is still typing. ---
  async function fetchRoutes(e) {
    e.preventDefault();
    setError("");

    if (!form.source.trim()) {
      setError(t("newTrip.selectPickupError"));
      return;
    }
    if (!form.destination.trim()) {
      setError(t("newTrip.selectDestinationError"));
      return;
    }

    setGeocoding(true);
    // "Current location" pickup already has a real GPS fix — reuse it
    // instead of re-geocoding the placeholder text. Everything else
    // (typed pickup text, and destination, which has no GPS option) gets
    // resolved here.
    const resolvedPickup = pickupMode === "current" && pickupPlace?.latitude != null
      ? pickupPlace
      : await geocodeAddress(form.source);
    const resolvedDestination = await geocodeAddress(form.destination);
    setGeocoding(false);

    if (!resolvedPickup) {
      setError("Couldn't find that pickup address. Try adding more detail (city, area, landmark).");
      return;
    }
    if (!resolvedDestination) {
      setError("Couldn't find that destination address. Try adding more detail (city, area, landmark).");
      return;
    }
    setPickupPlace(resolvedPickup);
    setDestinationPlace(resolvedDestination);

    setRoutesLoading(true);
    try {
      // Always obtain current weather for the resolved pickup before route
      // estimation. This is live OpenWeather data, not Weather_History.csv.
      const weather = await fetchLiveWeather(resolvedPickup.latitude, resolvedPickup.longitude);
      if (!weather) {
        setRoutesLoading(false);
        return;
      }
      setForm((f) => ({
        ...f,
        _origin_lat: resolvedPickup.latitude, _origin_lng: resolvedPickup.longitude,
        _dest_lat: resolvedDestination.latitude, _dest_lng: resolvedDestination.longitude,
      }));
      const routesRes = await api.get("/external/routes", {
        params: {
          origin_lat: resolvedPickup.latitude, origin_lng: resolvedPickup.longitude,
          dest_lat: resolvedDestination.latitude, dest_lng: resolvedDestination.longitude,
        },
      });
      if (!routesRes.data.routes || routesRes.data.routes.length === 0) {
        setError("Google Routes returned no options for that origin/destination — check the addresses and try again.");
        setRoutesLoading(false);
        return;
      }
      setRouteOptions(routesRes.data.routes);
      setChosenRouteIdx(0);
      setStage("routes");
      fetchRouteEstimates(routesRes.data.routes, weather);
    } catch (err) {
      setError(err.response?.data?.error || t("newTrip.couldNotFetchRoutes"));
    } finally {
      setRoutesLoading(false);
    }
  }

  // --- Quick CO2 estimate per route option, so the comparison map can color-code
  // them before the driver commits to one. Uses default weather/traffic; the full
  // AI prediction (with whatever weather/traffic the driver actually selects) still
  // runs separately once a route is chosen. ---
  async function fetchRouteEstimates(routes, weatherOverride = liveWeather) {
    setEstimatesLoading(true);
    try {
      const results = await Promise.all(routes.map((r) =>
        api.post("/trips/predict", {
          distance_km: r.distance_km, load_kg: parseFloat(form.load_kg) || 0,
          route: r.label, weather: weatherOverride?.condition || "Cloudy", traffic: form.traffic,
          temperature: weatherOverride?.temperature, humidity: weatherOverride?.humidity, wind_kmph: weatherOverride?.wind_kmph,
        }).then((res) => res.data).catch(() => null)
      ));
      setRouteEstimates(results);
    } finally {
      setEstimatesLoading(false);
    }
  }

  async function loadNearbyPlaces(type) {
    setPlacesType(type);
    setPlacesLoading(true);
    try {
      const pos = await getPosition();
      const res = await api.get("/external/places/nearby", { params: { lat: pos.coords.latitude, lon: pos.coords.longitude, type } });
      setPlaces(res.data.places || []);
    } catch {
      setPlaces([]);
    } finally {
      setPlacesLoading(false);
    }
  }

  async function runPrediction() {
    setError("");
    setStage("predicting");
    const chosen = routeOptions[chosenRouteIdx];
    try {
      const res = await api.post("/trips/predict", {
        distance_km: chosen.distance_km, load_kg: parseFloat(form.load_kg),
        route: chosen.label, weather: liveWeather?.condition || "Cloudy", traffic: form.traffic,
        temperature: liveWeather?.temperature, humidity: liveWeather?.humidity, wind_kmph: liveWeather?.wind_kmph,
        origin_lat: pickupPlace?.latitude, origin_lng: pickupPlace?.longitude,
        dest_lat: destinationPlace?.latitude, dest_lng: destinationPlace?.longitude,
      });
      setPrediction(res.data);
      setStage("review");
    } catch (err) {
      console.error("Prediction request failed:", err);
      let msg;
      let traceback = null;
      if (err.response) {
        // Server responded with an error status - show its body if we can read it.
        const body = err.response.data;
        msg = (typeof body === "object" && body?.error) ? body.error
          : `Server returned ${err.response.status}${typeof body === "string" && body ? `: ${body.slice(0, 200)}` : ""}`;
        traceback = (typeof body === "object" && body?.traceback) ? body.traceback : null;
        if (traceback) console.error("Backend traceback:\n" + traceback);
      } else if (err.request) {
        msg = "No response from the server — check that the Flask backend is still running and reachable.";
      } else {
        msg = `Request setup failed: ${err.message}`;
      }
      setError(`Prediction failed. ${msg}${traceback ? "" : " (full details logged to the browser console — press F12 to view)"}`);
      setErrorTraceback(traceback);
      setStage("routes");
    }
  }

  async function confirmAndStart() {
    setError("");
    const chosen = routeOptions[chosenRouteIdx];
    try {
      const created = await api.post("/trips", {
        source: pickupPlace?.formattedAddress || form.source,
        destination: destinationPlace?.formattedAddress || form.destination,
        distance_km: chosen.distance_km, load_kg: parseFloat(form.load_kg),
        purpose: form.purpose, preferred_route: chosen.label, route_chosen: chosen.label,
        weather: liveWeather?.condition || "Cloudy", traffic: form.traffic, ai_prediction: prediction,
        origin_lat: form._origin_lat, origin_lng: form._origin_lng,
        dest_lat: form._dest_lat, dest_lng: form._dest_lng,
        pickup_place_id: pickupPlace?.placeId || null,
        destination_place_id: destinationPlace?.placeId || null,
        estimated_duration_min: chosen.duration_min,
        route_polyline: chosen.polyline,
      });
      const started = await api.post(`/trips/${created.data.id}/start`);
      setTrip(started.data);
      setStage("ongoing");
    } catch (err) {
      setError(err.response?.data?.error || t("newTrip.couldNotStartTrip"));
    }
  }

  const [navError, setNavError] = useState("");
  const [navSteps, setNavSteps] = useState([]);

  // --- Live GPS tracking state (the "blue dot" and camera-follow behaviour,
  // same idea as Google Maps' own turn-by-turn view). Kept separate from the
  // map-creation effect below so a GPS fix arriving doesn't tear down and
  // recreate the whole map — it just moves a marker on the existing one. ---
  const [livePos, setLivePos] = useState(null);
  const [liveHeading, setLiveHeading] = useState(null);
  const [liveAccuracy, setLiveAccuracy] = useState(null);
  const [following, setFollowing] = useState(true);
  const [remainingKm, setRemainingKm] = useState(null);
  const [etaMin, setEtaMin] = useState(null);
  const [liveSpeedKmph, setLiveSpeedKmph] = useState(null);
  const [gpsWarning, setGpsWarning] = useState("");
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [rerouting, setRerouting] = useState(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [queuedPings, setQueuedPings] = useState(0);
  const [liveConditions, setLiveConditions] = useState(null);
  const isOnline = useOnlineStatus();
  const livePosRef = useRef(null); // mirrors livePos for the weather-refresh timer, which shouldn't re-run on every GPS tick
  const stepCumDistRef = useRef([]); // cumulative meters at the end of each turn-by-turn step (fallback path)
  const lastSpokenIdxRef = useRef(-1);
  const announced200Ref = useRef(new Set()); // step indices already given the "in 200m" countdown cue
  const polylineObjRef = useRef(null); // the drawn route polyline — updated in place on reroute
  const reroutingRef = useRef(false);
  const rerouteCountRef = useRef(0);
  const mapObjRef = useRef(null);
  const liveMarkerRef = useRef(null);
  const accuracyCircleRef = useRef(null);
  const pathInfoRef = useRef(null); // { path, cumulative[], totalMeters }
  const gpsWeatherRefreshedRef = useRef(false); // has Live Conditions already been re-fetched against a real GPS fix (see effect below)?

  function speak(text) {
    if (!voiceEnabled || !("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  // Watch the device's real position for the whole time the trip is ongoing.
  const lastPingRef = useRef(0);
  useEffect(() => {
    if (stage !== "ongoing") { setLivePos(null); return; }
    if (!window.isSecureContext || !navigator.geolocation) {
      setGpsWarning("Live location isn't available (needs HTTPS or localhost) — showing the planned route only.");
      return;
    }
    setGpsWarning("");
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setLivePos({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        livePosRef.current = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setLiveHeading(Number.isFinite(pos.coords.heading) ? pos.coords.heading : null);
        setLiveAccuracy(pos.coords.accuracy ?? null);
        // Geolocation API reports speed in m/s - convert to km/h to match
        // how speed is shown everywhere else in this app (Section 8: "current speed").
        setLiveSpeedKmph(Number.isFinite(pos.coords.speed) ? Math.max(0, Math.round(pos.coords.speed * 3.6)) : null);

        // Push to the backend so admins can see this on Live Fleet too —
        // throttled to once every 15s (within the 10-20s window a fast GPS
        // fix shouldn't flood the server, but Live Fleet still stays fresh).
        const now = Date.now();
        if (trip?.id && now - lastPingRef.current > 15000) {
          lastPingRef.current = now;
          const payload = {
            lat: pos.coords.latitude, lng: pos.coords.longitude,
            heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
            accuracy: pos.coords.accuracy ?? null,
            // Geolocation API reports speed in m/s - convert to km/h to match
            // how speed is shown everywhere else in this app.
            speed: Number.isFinite(pos.coords.speed) ? Math.max(0, pos.coords.speed * 3.6) : null,
          };
          api.post(`/driver/trips/${trip.id}/location`, payload).then((res) => {
            if (res.data?.destination_status) setDestStatus(res.data.destination_status);
          }).catch((err) => {
            // No signal or a dropped connection — log it (dev console only,
            // never surfaced to the driver as a crash) and don't lose the
            // fix: queue it for automatic retry the moment we're back online.
            console.error("GPS ping failed, queued for retry:", err?.message || err);
            enqueuePing(trip.id, payload);
            setQueuedPings(queueSize());
          });
        }
      },
      (err) => {
        const code = err.code;
        console.error(`Geolocation watchPosition error (code ${code}):`, err.message);
        setGpsWarning(
          code === 1 ? "Location permission denied — allow it to see your live position on the map."
          : code === 2 ? "Location signal unavailable right now — showing the planned route only."
          : "Location request timed out — showing the planned route only."
        );
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, [stage, trip?.id]);

  // The "Live Conditions" card must actually track the driver's current
  // location as a long trip moves through different weather, not just show
  // whatever the weather was at the origin when the trip was planned. Fetches
  // immediately on entering the ongoing stage, then every 5 minutes — reading
  // livePosRef (not the livePos state) so this doesn't re-fetch on every GPS
  // tick, since weather doesn't change that fast and OpenWeather shouldn't be
  // hit every 5 seconds.
  useEffect(() => {
    if (stage !== "ongoing") { setLiveConditions(null); return; }
    gpsWeatherRefreshedRef.current = false;
    let cancelled = false;

    async function fetchWeatherFor(pos) {
      if (!pos) return;
      try {
        const res = await api.get("/external/weather/area", { params: { lat: pos.lat, lon: pos.lng, radius_km: weatherRadiusKm } });
        if (!cancelled) {
          setLiveConditions({
            temp: res.data.temperature, humidity: res.data.humidity,
            wind: res.data.wind_kmph, city: res.data.city, condition: res.data.carbontrack_condition || res.data.condition,
            radiusKm: res.data.radius_km, areaAlert: res.data.area_alert, severeWeather: !!res.data.severe_weather,
          });
        }
      } catch {
        // best-effort — keep showing the last known conditions rather than blanking the card
        // (Section 20: weather failure must never break navigation/GPS/trip lifecycle)
      }
    }

    async function fetchLiveWeather() {
      const pos = livePosRef.current
        || (trip?.origin_lat != null ? { lat: trip.origin_lat, lng: trip.origin_lng } : null);
      await fetchWeatherFor(pos);
    }

    fetchLiveWeather();
    const interval = setInterval(fetchLiveWeather, 5 * 60 * 1000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [stage, trip?.id, weatherRadiusKm]);
  // callback — by the time the browser has a real fix, the weather card is
  // already showing the trip's origin coordinates and won't refresh again
  // until the 5-minute timer ticks. Catch that gap: the moment a real fix
  // shows up, refresh Live Conditions against it once (not on every GPS
  // tick — that's what gpsWeatherRefreshedRef guards against).
  useEffect(() => {
    if (stage !== "ongoing" || !livePos || gpsWeatherRefreshedRef.current) return;
    gpsWeatherRefreshedRef.current = true;
    (async () => {
      try {
        const res = await api.get("/external/weather/area", { params: { lat: livePos.lat, lon: livePos.lng, radius_km: weatherRadiusKm } });
        setLiveConditions({
          temp: res.data.temperature, humidity: res.data.humidity,
          wind: res.data.wind_kmph, city: res.data.city, condition: res.data.carbontrack_condition || res.data.condition,
          radiusKm: res.data.radius_km, areaAlert: res.data.area_alert, severeWeather: !!res.data.severe_weather,
        });
      } catch {
        // best-effort — leave the origin-based reading showing rather than blank the card
      }
    })();
  }, [stage, livePos, weatherRadiusKm]);

  // Retry any GPS pings that failed while offline the moment the browser
  // reports connectivity again (and once on mount, in case pings queued up
  // during a previous offline stretch of this same trip).
  useEffect(() => {
    setQueuedPings(queueSize());
    if (!isOnline) return;
    flushQueue(api, ({ remaining }) => setQueuedPings(remaining));
  }, [isOnline]);

  // --- Turn-by-turn navigation, built entirely from Routes API data (fetched
  // back when routes were listed) - deliberately does NOT use
  // google.maps.DirectionsService, which depends on Google's separate legacy
  // Directions API. That's a different toggle in Cloud Console from Routes
  // API, and requiring it just for a nav panel caused exactly the kind of
  // "map won't load" failure this avoids. ---
  useEffect(() => {
    if (stage !== "ongoing" || !mapsKey || !trip || !navMapNode) return;
    let cancelled = false;
    setNavError("");
    setMapLoading(true);
    const stallTimer = setTimeout(() => {
      if (!cancelled && !mapObjRef.current) {
        setNavError("Map is taking longer than expected to load — check your connection, or that nothing (like an ad blocker) is silently blocking Google Maps.");
      }
    }, 12000);
    const chosen = routeOptions[chosenRouteIdx];
    setNavSteps(chosen?.steps || []);
    let cum = 0;
    stepCumDistRef.current = (chosen?.steps || []).map((s) => (cum += (s.distance_km || 0) * 1000));
    setCurrentStepIdx(0);
    lastSpokenIdxRef.current = -1;
    announced200Ref.current = new Set();
    rerouteCountRef.current = 0;
    reroutingRef.current = false;
    setRerouting(false);

    (async () => {
      const google = await loadGoogleMaps(mapsKey).catch(() => null);
      if (cancelled) return;
      if (!google) {
        setNavError("Google Maps failed to load. Check that the Maps JavaScript API is enabled for this key in Google Cloud Console, and that localhost is allowed under the key's HTTP referrer restrictions.");
        setMapLoading(false);
        return;
      }
      if (!navMapNode) return;
      if (!chosen?.polyline) {
        setNavError("No route polyline available for this trip — try planning a new trip so a fresh route can be fetched.");
        setMapLoading(false);
        return;
      }

      try {
        const map = new google.maps.Map(navMapNode, {
          zoom: 7, center: { lat: 20.5937, lng: 78.9629 }, disableDefaultUI: true, styles: DARK_MAP_STYLE,
        });
        const path = google.maps.geometry.encoding.decodePath(chosen.polyline);
        polylineObjRef.current = new google.maps.Polyline({ path, map, strokeColor: "#22D3EE", strokeWeight: 5 });

        const bounds = new google.maps.LatLngBounds();
        path.forEach((p) => bounds.extend(p));
        map.fitBounds(bounds, 30);

        new google.maps.Marker({ position: path[0], map, label: "A" });
        new google.maps.Marker({ position: path[path.length - 1], map, label: "B" });

        // Precompute cumulative distance along the route so live GPS fixes can be
        // snapped to the nearest point and turned into a "remaining distance".
        let cumulative = [0];
        for (let i = 1; i < path.length; i++) {
          cumulative.push(cumulative[i - 1] + google.maps.geometry.spherical.computeDistanceBetween(path[i - 1], path[i]));
        }
        pathInfoRef.current = { path, cumulative, totalMeters: cumulative[cumulative.length - 1] };
        mapObjRef.current = map;
        setMapLoading(false);

        // Manually panning the map means the driver wants to look around —
        // stop auto-following until they tap "Recenter", same as Google Maps.
        map.addListener("dragstart", () => setFollowing(false));
      } catch (err) {
        console.error("Nav map drawing failed:", err);
        setNavError("The map couldn't be drawn — this usually clears up on a retry. Check your connection and reopen this trip.");
        setMapLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(stallTimer);
      mapObjRef.current = null;
      liveMarkerRef.current = null;
      accuracyCircleRef.current = null;
      pathInfoRef.current = null;
      polylineObjRef.current = null;
    };
  }, [stage, mapsKey, trip, routeOptions, chosenRouteIdx, navMapNode]);

  // --- Live "blue dot": moves/rotates an existing marker on GPS updates
  // instead of recreating the map, and keeps the camera centered on it while
  // "following" is on. Also derives a live remaining-distance/ETA readout by
  // snapping the fix to the nearest point on the precomputed route path. ---
  useEffect(() => {
    const map = mapObjRef.current;
    const google = window.google;
    if (!map || !google || !livePos) return;

    const icon = liveHeading != null
      ? { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 6, rotation: liveHeading, fillColor: "#4285F4", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2 }
      : { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: "#4285F4", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2 };

    if (!liveMarkerRef.current) {
      liveMarkerRef.current = new google.maps.Marker({ map, position: livePos, icon, zIndex: 999, title: "Your location" });
    } else {
      liveMarkerRef.current.setPosition(livePos);
      liveMarkerRef.current.setIcon(icon);
    }

    if (liveAccuracy) {
      if (!accuracyCircleRef.current) {
        accuracyCircleRef.current = new google.maps.Circle({
          map, center: livePos, radius: liveAccuracy,
          fillColor: "#4285F4", fillOpacity: 0.12, strokeColor: "#4285F4", strokeOpacity: 0.3, strokeWeight: 1,
        });
      } else {
        accuracyCircleRef.current.setCenter(livePos);
        accuracyCircleRef.current.setRadius(liveAccuracy);
      }
    }

    if (following) {
      map.panTo(livePos);
      if (map.getZoom() < 15) map.setZoom(16);
    }

    // Snap to nearest path point to compute remaining distance / ETA.
    const info = pathInfoRef.current;
    if (info?.path?.length) {
      const here = new google.maps.LatLng(livePos.lat, livePos.lng);
      let bestIdx = 0, bestDist = Infinity;
      info.path.forEach((p, i) => {
        const d = google.maps.geometry.spherical.computeDistanceBetween(here, p);
        if (d < bestDist) { bestDist = d; bestIdx = i; }
      });
      const remainingMeters = Math.max(info.totalMeters - info.cumulative[bestIdx], 0);
      setRemainingKm(remainingMeters / 1000);
      const chosen = routeOptions[chosenRouteIdx];
      if (chosen?.duration_min && info.totalMeters > 0) {
        setEtaMin(Math.round((remainingMeters / info.totalMeters) * chosen.duration_min));
      }

      // Figure out which turn-by-turn step the driver is currently on. When the
      // route came with real per-step end coordinates (Routes API v2 returns
      // these), advance step-by-step based on actual proximity to each step's
      // endpoint — a real waypoint Google computed, not a guess. Only falls
      // back to the coarser cumulative-distance estimate for routes fetched
      // before this existed (e.g. a route object cached from an older session).
      const steps = navSteps;
      if (steps.length > 0 && steps[0].end_lat != null) {
        let idx = currentStepIdx;
        while (idx < steps.length - 1) {
          const end = steps[idx];
          const d = google.maps.geometry.spherical.computeDistanceBetween(here, { lat: end.end_lat, lng: end.end_lng });
          if (d < STEP_ARRIVAL_RADIUS_M) idx += 1; else break;
        }
        if (idx !== currentStepIdx) setCurrentStepIdx(idx);

        // Countdown preview of the upcoming maneuver, the way Google Maps warns
        // "in 200 meters" before actually announcing the turn.
        const curEnd = steps[idx];
        const next = steps[idx + 1];
        if (curEnd?.end_lat != null && next && !announced200Ref.current.has(idx)) {
          const distToEnd = google.maps.geometry.spherical.computeDistanceBetween(here, { lat: curEnd.end_lat, lng: curEnd.end_lng });
          if (distToEnd <= 200) {
            announced200Ref.current.add(idx);
            speak(`In 200 meters, ${stripTags(next.instruction)}`);
          }
        }
      } else {
        // Fallback: match distance traveled so far against each step's
        // cumulative distance along the whole route.
        const traveledMeters = info.totalMeters - remainingMeters;
        const cumDist = stepCumDistRef.current;
        if (cumDist.length > 0) {
          let idx = cumDist.findIndex((d) => d >= traveledMeters);
          if (idx === -1) idx = cumDist.length - 1;
          setCurrentStepIdx(idx);
        }
      }

      // Automatic rerouting: if we're consistently far from the planned path,
      // recalculate from here instead of just flagging it and leaving the
      // driver to follow a route they're no longer on.
      if (bestDist > DEVIATION_THRESHOLD_M) {
        triggerReroute(livePos);
      }
    }
  }, [livePos, liveHeading, liveAccuracy, following, routeOptions, chosenRouteIdx, navSteps, currentStepIdx]);

  // Recalculates the route from the driver's current position to the original
  // destination and swaps it in place (same map, same markers for trip
  // start/end — only the polyline and turn-by-turn steps change).
  async function triggerReroute(pos) {
    if (reroutingRef.current || rerouteCountRef.current >= MAX_AUTO_REROUTES || !trip) return;
    reroutingRef.current = true;
    rerouteCountRef.current += 1;
    setRerouting(true);
    speak("Recalculating route.");
    try {
      const res = await api.get("/external/routes", {
        params: {
          origin_lat: pos.lat, origin_lng: pos.lng,
          dest_lat: trip.dest_lat, dest_lng: trip.dest_lng,
        },
      });
      const options = res.data.routes || [];
      if (options.length === 0) throw new Error("no routes");
      const best = options.reduce((a, b) => (b.duration_min < a.duration_min ? b : a));

      const google = window.google;
      const path = google.maps.geometry.encoding.decodePath(best.polyline);
      if (polylineObjRef.current) polylineObjRef.current.setPath(path);

      let cumulative = [0];
      for (let i = 1; i < path.length; i++) {
        cumulative.push(cumulative[i - 1] + google.maps.geometry.spherical.computeDistanceBetween(path[i - 1], path[i]));
      }
      pathInfoRef.current = { path, cumulative, totalMeters: cumulative[cumulative.length - 1] };

      setNavSteps(best.steps || []);
      let cum = 0;
      stepCumDistRef.current = (best.steps || []).map((s) => (cum += (s.distance_km || 0) * 1000));
      setCurrentStepIdx(0);
      lastSpokenIdxRef.current = -1;
      announced200Ref.current = new Set();

      await api.patch(`/driver/trips/${trip.id}/route`, { route_polyline: best.polyline }).catch(() => {});
    } catch {
      // Best-effort — if recalculation fails (offline, API hiccup), just keep
      // following the original planned route rather than breaking navigation.
    } finally {
      reroutingRef.current = false;
      setRerouting(false);
    }
  }

  // --- Voice guidance: speaks each turn-by-turn instruction aloud the moment
  // the driver's live position reaches it, so eyes can stay on the road. ---
  useEffect(() => {
    if (!voiceEnabled || stage !== "ongoing") return;
    if (lastSpokenIdxRef.current === currentStepIdx) return;
    const step = navSteps[currentStepIdx];
    if (!step?.instruction) return;
    lastSpokenIdxRef.current = currentStepIdx;
    speak(stripTags(step.instruction));
  }, [currentStepIdx, voiceEnabled, stage, navSteps]);

  // Stop talking if the driver mutes, navigates away, or the trip ends.
  useEffect(() => {
    if (!voiceEnabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
  }, [voiceEnabled]);
  useEffect(() => () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }, []);

  // --- Route comparison map: draws all fetched route polylines simultaneously,
  // color-coded by predicted CO2 (green = lowest, amber = mid, red = highest). ---
  useEffect(() => {
    if (stage !== "routes" || !mapsKey || routeOptions.length === 0 || !routeMapNode) return;
    let cancelled = false;
    (async () => {
      const google = await loadGoogleMaps(mapsKey).catch(() => null);
      if (!google || cancelled || !routeMapNode) return;

      try {
        const map = new google.maps.Map(routeMapNode, {
          zoom: 7, center: { lat: 20.5937, lng: 78.9629 }, disableDefaultUI: true,
          styles: DARK_MAP_STYLE,
        });

        // Rank routes by CO2 (if estimates are in yet) to assign colors low->high.
        const co2Values = routeEstimates.map((e) => e?.predicted_co2_kg ?? null);
        const validValues = co2Values.filter((v) => v !== null);
        const sorted = [...new Set(validValues)].sort((a, b) => a - b);
        const colorFor = (co2) => {
          if (co2 == null || sorted.length < 2) return "#6E6BFF"; // indigo fallback while estimates load
          if (co2 === sorted[0]) return "#4ADE80"; // lowest CO2 = green
          if (co2 === sorted[sorted.length - 1]) return "#FF6B6B"; // highest CO2 = red
          return "#F0B429"; // middle = amber
        };

        const bounds = new google.maps.LatLngBounds();
        routeOptions.forEach((route, i) => {
          if (!route.polyline) return;
          const path = google.maps.geometry.encoding.decodePath(route.polyline);
          path.forEach((p) => bounds.extend(p));
          const isChosen = i === chosenRouteIdx;
          new google.maps.Polyline({
            path, map,
            strokeColor: colorFor(co2Values[i]),
            strokeOpacity: isChosen ? 0.95 : 0.55,
            strokeWeight: isChosen ? 6 : 4,
            zIndex: isChosen ? 10 : 1,
          });
        });
        if (!bounds.isEmpty()) map.fitBounds(bounds, 40);
      } catch (err) {
        console.error("Route comparison map drawing failed:", err);
      }
    })();
    return () => { cancelled = true; };
  }, [stage, mapsKey, routeOptions, routeEstimates, chosenRouteIdx, routeMapNode]);

  // ---- End Trip ----------------------------------------------------------
  // The driver never ends a trip with a single click: clicking "End Trip"
  // only opens a confirmation modal (state below); performEndTrip() is the
  // function that actually calls the backend, and only confirmEndTrip()
  // (wired to the modal's "Confirm End Trip" button) invokes it. The
  // backend is the sole authority on completion — this never marks the
  // trip completed in frontend state alone.
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [endingTrip, setEndingTrip] = useState(false);
  const [endTripError, setEndTripError] = useState("");
  // Section 19-21 (Emergency Reassignment) + Section 22-26 (Chat with Admin) —
  // both are lightweight modals over the ongoing-trip screen, not separate pages,
  // since a driver needs them without losing their place in the live trip view.
  const [showReassignModal, setShowReassignModal] = useState(false);
  const [showChatPanel, setShowChatPanel] = useState(false);
  // Sections 18/19: the driver enters the REAL fuel consumed and REAL fuel
  // price paid — this is never fabricated/estimated client-side. The
  // backend independently computes actual_co2_kg/actual_cost from these
  // two numbers (see routes/trips.py:end_trip) and ignores any co2/cost
  // the frontend might send, so there's nothing to fake here even by accident.
  const [actualFuelL, setActualFuelL] = useState("");
  const [actualFuelPrice, setActualFuelPrice] = useState("");

  const fuelValid = actualFuelL !== "" && Number(actualFuelL) > 0 && Number(actualFuelL) < 2000;
  const fuelPriceValid = actualFuelPrice !== "" && Number(actualFuelPrice) > 0 && Number(actualFuelPrice) < 500;

  async function performEndTrip() {
    const payload = {
      actual_fuel_l: Number(actualFuelL),
      actual_fuel_price: Number(actualFuelPrice),
    };
    const res = await api.post(`/trips/${trip.id}/end`, payload);
    setTrip(res.data);
    // Trip Completed -> Feedback Form -> Trip Summary (the driver reaches
    // "summary" either by submitting feedback or tapping "Skip for now" —
    // see the feedback stage below).
    setStage("feedback");
    resetFeedbackForm();
    setLivePos(null);
    setDestStatus(null);
    setRemainingKm(null);
    setEtaMin(null);
    setLiveSpeedKmph(null);
    setFollowing(true);
    setCurrentStepIdx(0);
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    reroutingRef.current = false;
    rerouteCountRef.current = 0;
    setRerouting(false);
  }

  function openEndConfirm() {
    if (!destStatus?.end_trip_allowed) return; // defense in depth — the button is disabled anyway
    setEndTripError("");
    setActualFuelL("");
    setActualFuelPrice("");
    setShowEndConfirm(true);
  }

  function cancelEndConfirm() {
    // Cancel does nothing to the trip — it stays exactly as it was, still Ongoing.
    if (endingTrip) return; // don't let a stray Escape/outside-click interrupt an in-flight request
    setShowEndConfirm(false);
    setEndTripError("");
  }

  async function confirmEndTrip() {
    if (endingTrip) return; // guards against double-clicks / duplicate submissions
    if (!fuelValid || !fuelPriceValid) {
      setEndTripError(t("newTrip.fuelInputRequired"));
      return;
    }
    setEndingTrip(true);
    setEndTripError("");
    try {
      await performEndTrip();
      setShowEndConfirm(false);
    } catch (err) {
      console.error("Failed to end trip:", err);
      // Never mark the trip completed in frontend state on failure — leave
      // it Ongoing, keep the modal open, and let the driver retry.
      setEndTripError(err.response?.data?.error || t("newTrip.unableToEndTrip"));
    } finally {
      setEndingTrip(false);
    }
  }

  // ESC closes the confirmation modal (same as clicking outside/Cancel).
  useEffect(() => {
    if (!showEndConfirm) return;
    function onKeyDown(e) {
      if (e.key === "Escape") cancelEndConfirm();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showEndConfirm, endingTrip]);

  // ---- Post-Trip Feedback --------------------------------------------
  // Shown automatically once a trip reaches "feedback" (right after End
  // Trip succeeds). The driver can rate the trip and submit, or tap
  // "Skip for now" — either way, the trip itself is untouched; this only
  // ever creates/skips a separate feedback record.
  const EXPERIENCE_OPTIONS = ["Excellent", "Good", "Average", "Poor", "Very Poor"];
  const [overallRating, setOverallRating] = useState(0);
  const [navigationRating, setNavigationRating] = useState(0);
  const [ecoRouteRating, setEcoRouteRating] = useState(0);
  const [experience, setExperience] = useState("");
  const [feedbackComments, setFeedbackComments] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const [feedbackTouched, setFeedbackTouched] = useState(false);

  function resetFeedbackForm() {
    setOverallRating(0);
    setNavigationRating(0);
    setEcoRouteRating(0);
    setExperience("");
    setFeedbackComments("");
    setFeedbackError("");
    setFeedbackTouched(false);
  }

  const feedbackValid = overallRating > 0 && navigationRating > 0 && ecoRouteRating > 0 && experience !== "";

  async function submitFeedback() {
    if (submittingFeedback) return; // guard against double-clicks / duplicate submissions
    setFeedbackTouched(true);
    if (!feedbackValid) {
      setFeedbackError(t("newTrip.feedbackRequiredError"));
      return;
    }
    setSubmittingFeedback(true);
    setFeedbackError("");
    try {
      await api.post(`/trips/${trip.id}/feedback`, {
        overall_rating: overallRating,
        navigation_rating: navigationRating,
        eco_route_rating: ecoRouteRating,
        experience,
        comments: feedbackComments.trim() || undefined,
      });
      setStage("summary");
    } catch (err) {
      console.error("Failed to submit feedback:", err);
      setFeedbackError(err.response?.data?.error || t("newTrip.feedbackSubmitError"));
    } finally {
      setSubmittingFeedback(false);
    }
  }

  function skipFeedback() {
    if (submittingFeedback) return;
    setStage("summary");
  }

  async function sendSos() {
    await api.post("/driver/sos", { note: `Trip ${trip?.trip_code || ""} — driver requested emergency assistance.` });
    setSosSent(true);
    setTimeout(() => setSosSent(false), 4000);
  }

  async function reportDeviation() {
    await api.post("/driver/route-deviation", { trip_id: trip?.id });
    setDeviationSent(true);
    setTimeout(() => setDeviationSent(false), 4000);
  }

  function resetFlow() {
    setForm({ source: "", destination: "", load_kg: "", purpose: "Delivery", traffic: "Medium" });
    setPrediction(null);
    setLiveWeather(null);
    setTrip(null);
    setPlaces([]);
    setRouteOptions([]);
    setChosenRouteIdx(null);
    setPickupPlace(null);
    setDestinationPlace(null);
    setPickupMode("selected");
    resetFeedbackForm();
    setStage("details");
  }

  if (restoringTrip) {
    return (
      <div className="mx-auto max-w-6xl">
        <GlassCard strong className="flex flex-col items-center justify-center gap-3 p-12">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-white/15 border-t-amber" />
          <p className="text-sm text-ink-dim">Checking for an active trip…</p>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <TripStepper stage={stage} />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="mx-auto w-full max-w-2xl lg:mx-0">
      <AnimatePresence mode="wait">

        {stage === "details" && (
          <motion.div key="details" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <GlassCard strong className="p-6">
              <h2 className="font-display text-lg font-semibold text-ink">{t("newTrip.enterTripDetails")}</h2>
              <p className="mt-1 text-sm text-ink-dim">{t("newTrip.detailsSubtitle")}</p>
              {driverVehicle && (
                <div className="mt-3 flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <Wrench size={15} className="text-accent" />
                    <div>
                      <p className="text-sm font-medium text-ink">{driverVehicle.vehicle_no}</p>
                      <p className="text-[11px] text-ink-faint">{driverVehicle.vehicle_type} · {driverVehicle.fuel_type} · {driverVehicle.mileage} km/l</p>
                    </div>
                  </div>
                  {driverVehicle.health_score != null && (
                    <Badge tone={driverVehicle.health_score > 75 ? "success" : "warning"}>
                      {t("driverOverview.health", { defaultValue: "Health" })} {driverVehicle.health_score}%
                    </Badge>
                  )}
                </div>
              )}
              <form onSubmit={fetchRoutes} className="mt-5 space-y-4">
                <PlaceAutocomplete
                  label={t("newTrip.pickupLocation")}
                  placeholder={t("newTrip.searchPickup")}
                  value={form.source}
                  onChange={(text) => {
                    update("source", text);
                    // Typing over a previous "current location" GPS pickup
                    // invalidates it — fetchRoutes should geocode the new
                    // typed text instead of silently reusing the old fix.
                    setPickupMode("selected");
                    setPickupPlace(null);
                  }}
                  showCurrentLocation
                  onUseCurrentLocation={useCurrentLocationForPickup}
                  locating={locatingPickup}
                />
                <PlaceAutocomplete
                  label={t("trip.destination")}
                  placeholder={t("newTrip.searchDestination")}
                  value={form.destination}
                  onChange={(text) => { update("destination", text); setDestinationPlace(null); }}
                />
                <Input label={t("newTrip.loadKg")} type="number" value={form.load_kg} onChange={(e) => update("load_kg", e.target.value)} required />
                <Input label={t("newTrip.tripPurpose")} value={form.purpose} onChange={(e) => update("purpose", e.target.value)} />

                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CloudRain size={17} className="text-accent" />
                      <div>
                        <span className="text-sm font-semibold text-ink">{t("newTrip.weatherAroundPickup", { defaultValue: "Weather around pickup" })}</span>
                        <p className="text-[11px] text-ink-faint">
                          {t("newTrip.withinRadius", { radius: `${weatherRadiusKm} km`, defaultValue: `Within ${weatherRadiusKm} km` })}
                        </p>
                      </div>
                    </div>
                    <span className="text-[10px] uppercase tracking-wider text-ink-faint">OpenWeather</span>
                  </div>
                  <div className="mt-2 flex items-center gap-1.5">
                    <span className="text-[10px] uppercase tracking-wide text-ink-faint">{t("newTrip.radius", { defaultValue: "Radius" })}</span>
                    {AREA_WEATHER_RADIUS_OPTIONS_KM.map((km) => (
                      <button
                        key={km}
                        type="button"
                        onClick={() => {
                          setWeatherRadiusKm(km);
                          if (pickupPlace?.latitude != null) fetchLiveWeather(pickupPlace.latitude, pickupPlace.longitude);
                        }}
                        className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${weatherRadiusKm === km ? "border-amber/50 bg-amber/15 text-amber-soft" : "border-white/10 text-ink-faint hover:border-white/20"}`}
                      >
                        {km} km
                      </button>
                    ))}
                  </div>
                  {weatherLoading ? (
                    <p className="mt-3 text-xs text-ink-dim">{t("newTrip.fetchingWeather")}</p>
                  ) : liveWeather ? (
                    <>
                      <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                        <div>
                          <p className="text-ink-faint">{t("newTrip.condition")}</p>
                          <p className="mt-1 font-medium text-ink">{liveWeather.condition}</p>
                        </div>
                        <div>
                          <p className="text-ink-faint">{t("newTrip.temperature")}</p>
                          <p className="mt-1 font-medium text-ink">{liveWeather.temperature != null ? `${liveWeather.temperature}°C` : "—"}</p>
                        </div>
                        <div>
                          <p className="text-ink-faint">{t("newTrip.humidity")}</p>
                          <p className="mt-1 font-medium text-ink">{liveWeather.humidity != null ? `${liveWeather.humidity}%` : "—"}</p>
                        </div>
                        <div>
                          <p className="text-ink-faint">{t("newTrip.wind")}</p>
                          <p className="mt-1 font-medium text-ink">{liveWeather.wind_kmph != null ? `${liveWeather.wind_kmph} km/h` : "—"}</p>
                        </div>
                      </div>
                      <div className="mt-3">
                        {liveWeather.severeWeather && liveWeather.areaAlert ? (
                          <Badge tone="warning">{liveWeather.areaAlert}</Badge>
                        ) : (
                          <Badge tone="success">{t("newTrip.noSevereWeather", { defaultValue: "No severe weather nearby" })}</Badge>
                        )}
                      </div>
                      {liveWeather.successfulSamples != null && liveWeather.sampleCount != null && liveWeather.successfulSamples < liveWeather.sampleCount && (
                        <p className="mt-2 text-[10px] text-ink-faint">
                          {t("newTrip.partialWeatherData", {
                            successful: liveWeather.successfulSamples, total: liveWeather.sampleCount,
                            defaultValue: `Partial data — ${liveWeather.successfulSamples}/${liveWeather.sampleCount} area samples available`,
                          })}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="mt-3 text-xs text-ink-dim">{t("newTrip.selectPickupForWeather")}</p>
                  )}
                  {liveWeather?.city && (
                    <p className="mt-3 text-[11px] text-ink-faint">{t("newTrip.locationLiveConditions", { city: liveWeather.city })}</p>
                  )}
                </div>
                {error && <p className="text-xs text-danger">{error}</p>}
                <Button type="submit" variant="primary" className="w-full" disabled={routesLoading || geocoding || !form.source.trim() || !form.destination.trim()}>
                  <Milestone size={16} /> {geocoding ? "Locating addresses…" : routesLoading ? t("newTrip.fetchingRouteOptions") : t("newTrip.getRouteOptions")}
                </Button>
              </form>
            </GlassCard>
          </motion.div>
        )}

        {stage === "routes" && (
          <motion.div key="routes" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <GlassCard strong className="overflow-hidden p-0">
              <div ref={setRouteMapNode} className="h-56 w-full" />
              <div className="flex flex-wrap items-center gap-4 border-b border-white/10 bg-white/[0.02] px-4 py-2 text-[11px] text-ink-faint">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-success" /> Lowest CO2</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber" /> Medium</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-danger" /> Highest CO2</span>
                {estimatesLoading && <span className="ml-auto">{t("newTrip.estimatingCo2")}</span>}
              </div>

              <div className="p-6">
                <h2 className="font-display text-lg font-semibold text-ink">{t("newTrip.chooseRoute")}</h2>
                <p className="mt-1 text-sm text-ink-dim">{form.source} → {form.destination}</p>

                {(() => {
                  const explain = computeEcoExplanation(routeOptions, routeEstimates);
                  if (!explain) return null;
                  const { fuelSavingsPct, co2SavingsPct, extraMin } = explain;
                  return (
                    <div className="mt-3 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
                      Eco Route saves {fuelSavingsPct}% fuel and {co2SavingsPct}% CO2
                      {extraMin > 0 ? ` — only ${extraMin} min extra vs. Fastest.` : " with no meaningful time cost vs. Fastest."}
                    </div>
                  );
                })()}

                <div className="mt-4 space-y-2">
                  {(() => {
                    const { fastestIdx, shortestIdx, recommendedIdx } = computeRouteBadges(routeOptions, routeEstimates);
                    return routeOptions.map((r, i) => (
                      <button key={i} onClick={() => setChosenRouteIdx(i)}
                              className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${chosenRouteIdx === i ? "border-amber/50 bg-amber/5" : "border-white/10 bg-white/[0.02] hover:border-white/20"}`}>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <p className="text-sm font-medium text-ink">{r.label}</p>
                            {i === recommendedIdx && <Badge tone="warning">{t("newTrip.recommended", { defaultValue: "Recommended" })}</Badge>}
                            {i === fastestIdx && <Badge tone="neutral">{t("newTrip.fastest", { defaultValue: "Fastest" })}</Badge>}
                            {i === shortestIdx && i !== fastestIdx && <Badge tone="neutral">{t("newTrip.shortest", { defaultValue: "Shortest" })}</Badge>}
                          </div>
                          <p className="mt-1 text-xs text-ink-dim">
                            {r.distance_km} km · {r.duration_min} min · {r.road_type}
                            {r.traffic_delay_ratio > 1.1 && <span className="text-amber"> · +{Math.round((r.traffic_delay_ratio - 1) * 100)}% traffic</span>}
                          </p>
                          {routeEstimates[i] && (
                            <p className="mt-1 text-xs text-ink-faint">
                              ~{routeEstimates[i].predicted_fuel_l} L · ~{routeEstimates[i].predicted_co2_kg} kg CO2
                              {routeEstimates[i].predicted_eco_score != null && ` · Eco score ${routeEstimates[i].predicted_eco_score}`}
                            </p>
                          )}
                        </div>
                        {chosenRouteIdx === i && <CheckCircle2 size={18} className="shrink-0 text-amber" />}
                      </button>
                    ));
                  })()}
                </div>

                <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CloudRain size={16} className="text-accent" />
                      <span className="text-xs font-medium uppercase tracking-wide text-ink-dim">Live Weather</span>
                    </div>
                    <span className="text-[10px] uppercase tracking-wider text-ink-faint">OpenWeather</span>
                  </div>
                  {weatherLoading && <p className="mt-2 text-xs text-ink-dim">Refreshing current conditions...</p>}
                  {liveWeather && (
                    <>
                      <p className="mt-2 text-xs text-ink">
                        {liveWeather.condition} · {liveWeather.temperature != null ? `${liveWeather.temperature}°C` : "—"} ·
                        Humidity {liveWeather.humidity != null ? `${liveWeather.humidity}%` : "—"} ·
                        Wind {liveWeather.wind_kmph != null ? `${liveWeather.wind_kmph} km/h` : "—"}
                        {liveWeather.city ? ` · ${liveWeather.city}` : ""}
                      </p>
                      {liveWeather.severeWeather && liveWeather.areaAlert && (
                        <div className="mt-2"><Badge tone="warning">{liveWeather.areaAlert}</Badge></div>
                      )}
                    </>
                  )}
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3">
                  <Select label={t("newTrip.traffic")} value={form.traffic} onChange={(e) => update("traffic", e.target.value)}>
                    {TRAFFICS.map((t) => <option key={t}>{t}</option>)}
                  </Select>
                </div>

                {error && <p className="mt-3 text-xs text-danger">{error}</p>}
                {errorTraceback && (
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-black/40 p-3 text-[10px] leading-relaxed text-danger">
                    {errorTraceback}
                  </pre>
                )}
                <div className="mt-6 flex gap-3">
                  <Button variant="ghost" className="flex-1" onClick={() => setStage("details")}>Back</Button>
                  <Button variant="primary" className="flex-1" onClick={runPrediction} disabled={chosenRouteIdx === null}>
                    Get AI Prediction
                  </Button>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {stage === "predicting" && (
          <motion.div key="predicting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <PredictionLoadingScreen t={t} />
          </motion.div>
        )}

        {stage === "review" && prediction && (
          <motion.div key="review" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">
            <GlassCard strong className="p-6">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-lg font-semibold text-ink">{t("newTrip.aiPredictionTitle")}</h2>
                <Badge tone="indigo">{prediction.ai_confidence}% {t("newTrip.confidence")}</Badge>
              </div>
              <p className="mt-1 text-sm text-ink-dim">{form.source} → {form.destination} · {routeOptions[chosenRouteIdx]?.distance_km} km {t("newTrip.via")} {routeOptions[chosenRouteIdx]?.label}</p>

              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric icon={Fuel} label={t("trip.fuel")} value={`${prediction.predicted_fuel_l} L`} />
                <Metric icon={Leaf} label="CO2" value={`${prediction.predicted_co2_kg} kg`} />
                <Metric icon={DollarSign} label={t("trip.cost")} value={`₹${prediction.predicted_cost}`} />
                <Metric icon={Gauge} label={t("driverOverview.ecoScore")} value={prediction.predicted_eco_score} />
                <Metric icon={Wrench} label={t("newTrip.maintenanceRisk")} value={prediction.maintenance_risk} />
                <Metric icon={CloudRain} label={t("newTrip.weatherImpact")} value={`${prediction.weather_impact}/100`} />
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-xs sm:grid-cols-4">
                <div>
                  <p className="text-ink-faint">{t("newTrip.estimatedDuration", { defaultValue: "Est. duration" })}</p>
                  <p className="mt-1 font-medium text-ink">{routeOptions[chosenRouteIdx]?.duration_min} min</p>
                </div>
                <div>
                  <p className="text-ink-faint">{t("newTrip.condition")}</p>
                  <p className="mt-1 font-medium text-ink">{liveWeather?.condition || "—"}</p>
                </div>
                <div>
                  <p className="text-ink-faint">{t("newTrip.traffic")}</p>
                  <p className="mt-1 font-medium text-ink">{form.traffic || "—"}</p>
                </div>
                <div>
                  <p className="text-ink-faint">{t("newTrip.load", { defaultValue: "Load" })}</p>
                  <p className="mt-1 font-medium text-ink">{form.load_kg} kg</p>
                </div>
              </div>
              {liveWeather?.severeWeather && liveWeather?.areaAlert && (
                <div className="mt-3"><Badge tone="warning">{liveWeather.areaAlert}</Badge></div>
              )}

              <div className="mt-5 flex items-center justify-between rounded-xl border border-amber/30 bg-amber/5 px-4 py-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-dim">{t("newTrip.aiRecommendedRoute")}</p>
                  <p className="font-display text-lg font-semibold text-amber">{prediction.recommended_route}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs uppercase tracking-wide text-ink-dim">{t("newTrip.overallScore")}</p>
                  <p className="font-display text-lg font-semibold text-ink">{prediction.overall_score}/100</p>
                </div>
              </div>

              <div className="mt-6 flex gap-3">
                <Button variant="ghost" className="flex-1" onClick={() => setStage("routes")}>{t("common.back")}</Button>
                <Button variant="primary" className="flex-1" onClick={confirmAndStart}>
                  <Navigation size={16} /> {t("trip.start")}
                </Button>
              </div>
              {error && <p className="mt-2 text-xs text-danger">{error}</p>}
            </GlassCard>
          </motion.div>
        )}

        {stage === "ongoing" && trip && (
          <motion.div key="ongoing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">
            <GlassCard strong className="trip-console-trim overflow-hidden p-0">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                <div className="flex items-center gap-3">
                  <span className="glow-chip-cyan flex h-9 w-9 items-center justify-center rounded-xl">
                    <IsoTruckBadge size={22} />
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-cyan shadow-[0_0_8px_2px_rgba(34,211,238,0.6)]" />
                    <span className="text-sm font-medium text-ink">{t("newTrip.tripInProgress")}</span>
                  </div>
                </div>
                <span className="flex items-center gap-3">
                  <button
                    onClick={() => setVoiceEnabled((v) => !v)}
                    title={voiceEnabled ? t("newTrip.muteVoice") : t("newTrip.enableVoice")}
                    className="text-ink-dim hover:text-amber"
                  >
                    {voiceEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
                  </button>
                  <span className="font-mono text-xs text-ink-dim">{trip.trip_code}</span>
                </span>
              </div>

              <div className="relative">
                <div ref={setNavMapNode} className="h-64 w-full" />
                {mapLoading && !navError && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[#0A0D16]">
                    <span className="h-6 w-6 animate-spin rounded-full border-2 border-white/15 border-t-amber" />
                    <p className="text-xs text-ink-faint">Loading map…</p>
                  </div>
                )}
                {!mapLoading && !navError && !livePos && !gpsWarning && (
                  <div className="hud-pill pointer-events-none absolute left-3 top-3 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-white">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber" /> Waiting for GPS…
                  </div>
                )}
                {livePos && (remainingKm != null) && (
                  <div className="hud-pill pointer-events-none absolute left-3 top-3 rounded-lg px-3 py-1.5 text-xs text-white">
                    <span className="font-semibold text-cyan-soft">{remainingKm.toFixed(1)} km</span> remaining
                    {etaMin != null && <span className="text-white/70"> · ~{etaMin} min</span>}
                  </div>
                )}
                {livePos && liveSpeedKmph != null && (
                  <div className="hud-pill pointer-events-none absolute right-3 top-3 rounded-lg px-3 py-1.5 text-center text-xs text-white">
                    <span className="font-semibold text-cyan-soft">{liveSpeedKmph}</span>
                    <span className="text-white/70"> km/h</span>
                  </div>
                )}
                {rerouting && (
                  <div className="hud-pill absolute left-1/2 top-3 -translate-x-1/2 rounded-lg px-3 py-1.5 text-xs text-white">
                    Recalculating route…
                  </div>
                )}
                {!following && (
                  <button
                    onClick={() => setFollowing(true)}
                    className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-full bg-amber px-3 py-1.5 text-xs font-medium text-black shadow-lg"
                  >
                    <LocateFixed size={14} /> Recenter
                  </button>
                )}
              </div>
              {gpsWarning && (
                <div className="border-t border-white/10 bg-white/[0.02] px-4 py-2 text-[11px] text-ink-faint">
                  {gpsWarning}
                </div>
              )}
              {!isOnline && (
                <div className="border-t border-amber/30 bg-amber/5 px-4 py-2 text-[11px] text-amber">
                  You're offline — navigation keeps working from the downloaded route, and GPS pings are being saved to send automatically once you're back online{queuedPings > 0 ? ` (${queuedPings} queued)` : ""}.
                </div>
              )}
              {isOnline && queuedPings > 0 && (
                <div className="border-t border-white/10 bg-white/[0.02] px-4 py-2 text-[11px] text-ink-faint">
                  Sending {queuedPings} queued location update{queuedPings === 1 ? "" : "s"} from earlier…
                </div>
              )}
              {navError && (
                <div className="border-t border-danger/30 bg-danger/5 px-4 py-3 text-xs text-danger">
                  {navError}
                </div>
              )}
              {navSteps.length > 0 && (
                <ol className="max-h-40 overflow-y-auto border-t border-white/10 bg-white/[0.02] p-3 text-xs text-ink-dim">
                  {navSteps.map((s, i) => (
                    <li key={i} className={`flex items-start gap-2 border-b border-white/5 py-1.5 last:border-0 ${i === currentStepIdx ? "-mx-3 rounded-lg bg-amber/10 px-3" : ""}`}>
                      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] ${i === currentStepIdx ? "bg-amber text-black" : "bg-white/[0.06] text-ink-faint"}`}>{i + 1}</span>
                      <span className={`flex-1 ${i === currentStepIdx ? "text-ink" : ""}`} dangerouslySetInnerHTML={{ __html: s.instruction }} />
                      <span className="shrink-0 text-ink-faint">{s.distance_km} km</span>
                    </li>
                  ))}
                </ol>
              )}

              {/* Weather + traffic strip — visible on mobile too (the sidebar weather
                  card is desktop-only), so this is the driver's only view of area
                  weather while the trip is underway on a phone. */}
              {(liveConditions || trip.traffic_condition) && (
                <div className="flex flex-wrap items-center gap-2 border-t border-white/10 bg-white/[0.02] px-4 py-2.5 text-xs">
                  {liveConditions && (
                    <span className="flex items-center gap-1.5 text-ink-dim">
                      <CloudRain size={13} className="text-accent" />
                      {liveConditions.condition}
                      {liveConditions.temp != null ? `, ${liveConditions.temp}°C` : ""}
                      {liveConditions.city ? ` · ${liveConditions.city}` : ""}
                      {liveConditions.radiusKm ? ` (within ${Math.round(liveConditions.radiusKm)} km)` : ""}
                    </span>
                  )}
                  {liveConditions?.severeWeather && liveConditions?.areaAlert && (
                    <Badge tone="warning">{liveConditions.areaAlert}</Badge>
                  )}
                  {trip.traffic_condition && (
                    <Badge tone={trip.traffic_condition === "High" ? "danger" : trip.traffic_condition === "Medium" ? "warning" : "neutral"}>
                      {trip.traffic_condition} {t("newTrip.traffic")}
                    </Badge>
                  )}
                  <span className="ml-auto flex items-center gap-1">
                    {AREA_WEATHER_RADIUS_OPTIONS_KM.map((km) => (
                      <button
                        key={km}
                        type="button"
                        onClick={() => setWeatherRadiusKm(km)}
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${weatherRadiusKm === km ? "border-amber/50 bg-amber/15 text-amber-soft" : "border-white/10 text-ink-faint hover:border-white/20"}`}
                      >
                        {km}km
                      </button>
                    ))}
                  </span>
                </div>
              )}

              <div className="grid grid-cols-3 divide-x divide-white/10 border-t border-white/10 text-center">
                <div className="p-4"><p className="text-xs text-ink-dim">{t("newTrip.distance")}</p><p className="font-mono text-ink">{trip.distance_km} km</p></div>
                <div className="p-4"><p className="text-xs text-ink-dim">{t("newTrip.predictedCo2")}</p><p className="font-mono text-amber">{predictionView?.predicted_co2_kg ?? "—"} kg</p></div>
                <div className="p-4"><p className="text-xs text-ink-dim">{t("newTrip.route")}</p><p className="font-mono text-ink">{trip.route_chosen}</p></div>
              </div>

              <div className="flex flex-wrap items-center gap-2 border-t border-white/10 bg-white/[0.02] px-4 py-2.5 text-xs">
                {destStatus?.destination_known === false ? (
                  <Badge tone="warning"><Lock size={11} className="mr-1 inline" />{t("newTrip.destinationUnknown")}</Badge>
                ) : destStatus?.destination_reached ? (
                  <span className="glow-chip-green inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium text-success">
                    <LockOpen size={11} />{t("newTrip.destinationReached")}
                  </span>
                ) : (
                  <span className="glow-chip-cyan inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium text-cyan-soft">
                    <Lock size={11} />
                    {destStatus?.distance_to_destination_m != null
                      ? t("newTrip.destinationLockedDistance", { distance: destStatus.distance_to_destination_m })
                      : t("newTrip.destinationLockedWaiting")}
                  </span>
                )}
                {destStatus && !destStatus.gps_accuracy_ok && destStatus.gps_available && (
                  <Badge tone="warning">{t("newTrip.gpsAccuracyLow")}</Badge>
                )}
              </div>

              <div className="flex flex-wrap gap-3 border-t border-white/10 p-6">
                <Button variant="danger" onClick={sendSos}><Siren size={15} /> {sosSent ? t("newTrip.sosSent") : t("newTrip.sos")}</Button>
                <Button variant="ghost" onClick={reportDeviation}><AlertOctagon size={15} /> {deviationSent ? t("newTrip.deviationLogged") : t("newTrip.reportDeviation")}</Button>
                <Button variant="ghost" onClick={() => setShowChatPanel(true)}><MessageCircle size={15} /> {t("newTrip.chatWithAdmin")}</Button>
                <Button variant="ghost" onClick={() => setShowReassignModal(true)}><UserCog size={15} /> {t("newTrip.requestReassignment")}</Button>
                <Button
                  variant="primary"
                  className={`flex-1 ${destStatus?.end_trip_allowed ? "!shadow-[0_0_0_1px_rgba(74,222,128,0.5),0_0_24px_-4px_rgba(74,222,128,0.55)]" : ""}`}
                  onClick={openEndConfirm}
                  disabled={!destStatus?.end_trip_allowed}
                  title={!destStatus?.end_trip_allowed ? (destStatus?.reason || t("newTrip.destinationLockedWaiting")) : undefined}
                >
                  {destStatus?.end_trip_allowed ? <CheckCircle2 size={16} /> : <Lock size={16} />} {t("trip.end")}
                </Button>
              </div>
            </GlassCard>

            <GlassCard className="p-5">
              <div className="flex items-center gap-2">
                <MapPinned size={16} className="text-amber" />
                <h3 className="font-display text-sm font-semibold text-ink">{t("newTrip.nearbyServices")}</h3>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {PLACE_TYPES.map((p) => (
                  <button key={p.type} onClick={() => loadNearbyPlaces(p.type)}
                          className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${placesType === p.type && places.length ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}>
                    {t(p.labelKey)}
                  </button>
                ))}
              </div>
              <div className="mt-3 space-y-2">
                {placesLoading && <p className="text-xs text-ink-faint">{t("newTrip.locatingNearby")}</p>}
                {!placesLoading && places.length === 0 && <p className="text-xs text-ink-faint">{t("newTrip.tapCategory")}</p>}
                {places.map((p, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-2 text-xs">
                    <div>
                      <p className="text-ink">{p.name}</p>
                      <p className="text-ink-faint">{p.address}</p>
                    </div>
                    {p.rating && <Badge tone="neutral">★ {p.rating}</Badge>}
                  </div>
                ))}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {stage === "feedback" && trip && (
          <motion.div key="feedback" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <GlassCard strong className="p-6">
              <div className="text-center">
                <PartyPopper className="mx-auto text-amber" size={32} />
                <h2 className="mt-3 font-display text-lg font-semibold text-ink">{t("newTrip.tripCompleted")}</h2>
                <p className="mt-1 text-sm text-ink-dim">{t("newTrip.feedbackSubtitle")}</p>
              </div>

              <div className="mt-6 space-y-5">
                <StarRating
                  label={t("newTrip.overallRatingLabel")}
                  value={overallRating}
                  onChange={setOverallRating}
                  required
                  error={feedbackTouched && overallRating === 0}
                />
                <StarRating
                  label={t("newTrip.navigationRatingLabel")}
                  value={navigationRating}
                  onChange={setNavigationRating}
                  required
                  error={feedbackTouched && navigationRating === 0}
                />
                <StarRating
                  label={t("newTrip.ecoRouteRatingLabel")}
                  value={ecoRouteRating}
                  onChange={setEcoRouteRating}
                  required
                  error={feedbackTouched && ecoRouteRating === 0}
                />

                <Select
                  label={t("newTrip.experienceLabel")}
                  value={experience}
                  onChange={(e) => setExperience(e.target.value)}
                  aria-required="true"
                  aria-invalid={feedbackTouched && experience === ""}
                >
                  <option value="" disabled>{t("newTrip.experiencePlaceholder")}</option>
                  {EXPERIENCE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </Select>

                <TextArea
                  label={t("newTrip.commentsLabel")}
                  value={feedbackComments}
                  onChange={(e) => setFeedbackComments(e.target.value)}
                  placeholder={t("newTrip.commentsPlaceholder")}
                  maxLength={1000}
                  rows={3}
                />

                {feedbackError && (
                  <div role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    <span>{feedbackError}</span>
                  </div>
                )}

                <Button
                  variant="primary"
                  className="w-full"
                  onClick={submitFeedback}
                  disabled={submittingFeedback || (feedbackTouched && !feedbackValid)}
                >
                  {submittingFeedback ? (
                    <>
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                      {t("newTrip.submittingFeedback")}
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={16} /> {t("newTrip.submitFeedback")}
                    </>
                  )}
                </Button>

                <button
                  type="button"
                  onClick={skipFeedback}
                  disabled={submittingFeedback}
                  className="block w-full text-center text-xs text-ink-dim underline-offset-2 hover:text-ink hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {t("newTrip.skipForNow")}
                </button>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {stage === "summary" && trip && (
          <motion.div key="summary" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <GlassCard strong className="p-6 text-center">
              <CheckCircle2 className="mx-auto text-success" size={40} />
              <h2 className="mt-4 font-display text-lg font-semibold text-ink">{t("newTrip.tripCompleted")}</h2>
              <p className="mt-1 text-sm text-ink-dim">{trip.source} → {trip.destination}</p>

              <div className="mt-6 grid grid-cols-3 gap-3">
                <Metric icon={Fuel} label={t("newTrip.fuelUsed")} value={`${trip.actual_fuel_l} L`} />
                <Metric icon={Leaf} label={t("newTrip.co2Emitted")} value={`${trip.actual_co2_kg} kg`} />
                <Metric icon={DollarSign} label={t("trip.cost")} value={`₹${trip.actual_cost}`} />
              </div>

              {trip.prediction_error && (
                <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-4 text-left text-xs">
                  <p className="mb-2 font-medium text-ink-dim">{t("newTrip.predictedVsActual")}</p>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-ink-faint">{t("newTrip.fuelPredictionAccuracy")}</span>
                      <span className={`font-mono ${Math.abs(trip.prediction_error.fuel_error_pct ?? 0) <= 15 ? "text-success" : "text-amber"}`}>
                        {trip.prediction_error.fuel_predicted_l}L → {trip.prediction_error.fuel_actual_l}L
                        {trip.prediction_error.fuel_error_pct != null && (
                          <> ({trip.prediction_error.fuel_error_pct > 0 ? "+" : ""}{trip.prediction_error.fuel_error_pct}%)</>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-ink-faint">{t("newTrip.co2PredictionAccuracy")}</span>
                      <span className={`font-mono ${Math.abs(trip.prediction_error.co2_error_pct ?? 0) <= 15 ? "text-success" : "text-amber"}`}>
                        {trip.prediction_error.co2_predicted_kg}kg → {trip.prediction_error.co2_actual_kg}kg
                        {trip.prediction_error.co2_error_pct != null && (
                          <> ({trip.prediction_error.co2_error_pct > 0 ? "+" : ""}{trip.prediction_error.co2_error_pct}%)</>
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <Button variant="primary" className="mt-6 w-full" onClick={resetFlow}>{t("newTrip.planAnotherTrip")}</Button>
            </GlassCard>
          </motion.div>
        )}

      </AnimatePresence>
        </div>

        <TripSidebar form={form} stage={stage} prediction={predictionView} liveConditions={liveConditions} weatherRadiusKm={weatherRadiusKm} />
      </div>

      {/* ---- End Trip confirmation modal ------------------------------- */}
      {/* Backend is the only thing that can actually complete a trip — this
          modal just gates the request behind an explicit confirmation.
          Cancel (button, Escape, or clicking outside) does nothing to the
          trip; it stays Ongoing either way. */}
      <AnimatePresence>
        {showEndConfirm && trip && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
            onClick={cancelEndConfirm}
            role="presentation"
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.97 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-sm"
              role="dialog"
              aria-modal="true"
              aria-labelledby="end-trip-dialog-title"
            >
              <GlassCard strong className="overflow-hidden">
                <div className="flex items-center justify-between border-b border-white/10 p-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={16} className="text-amber" />
                    <h3 id="end-trip-dialog-title" className="font-display text-sm font-semibold text-ink">{t("newTrip.endTripQuestion")}</h3>
                  </div>
                  <button onClick={cancelEndConfirm} disabled={endingTrip} aria-label={t("common.cancel", "Cancel")} className="text-ink-dim hover:text-ink disabled:opacity-40">
                    <X size={18} />
                  </button>
                </div>

                <div className="space-y-4 p-5">
                  <p className="text-sm text-ink-dim">
                    {t("newTrip.endTripBody")}
                  </p>

                  <div className="space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm">
                    <div className="flex justify-between">
                      <span className="text-ink-dim">{t("newTrip.tripLabel")}</span>
                      <span className="text-ink">{trip.source} → {trip.destination}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink-dim">{t("newTrip.distanceLabel")}</span>
                      <span className="font-mono text-ink">{trip.distance_km} km</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink-dim">{t("newTrip.predictedCo2Label")}</span>
                      <span className="font-mono text-amber">{predictionView?.predicted_co2_kg ?? "—"} kg</span>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label htmlFor="actual-fuel-l" className="mb-1 block text-xs font-medium text-ink-dim">
                        {t("newTrip.actualFuelLabel")}
                      </label>
                      <input
                        id="actual-fuel-l"
                        type="number"
                        inputMode="decimal"
                        min="0.01"
                        max="1999"
                        step="0.01"
                        value={actualFuelL}
                        onChange={(e) => setActualFuelL(e.target.value)}
                        placeholder={t("newTrip.actualFuelPlaceholder")}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-ink outline-none focus:border-amber/50"
                        aria-invalid={actualFuelL !== "" && !fuelValid}
                      />
                    </div>
                    <div>
                      <label htmlFor="actual-fuel-price" className="mb-1 block text-xs font-medium text-ink-dim">
                        {t("newTrip.actualFuelPriceLabel")}
                      </label>
                      <input
                        id="actual-fuel-price"
                        type="number"
                        inputMode="decimal"
                        min="0.01"
                        max="499"
                        step="0.01"
                        value={actualFuelPrice}
                        onChange={(e) => setActualFuelPrice(e.target.value)}
                        placeholder={t("newTrip.actualFuelPricePlaceholder")}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-ink outline-none focus:border-amber/50"
                        aria-invalid={actualFuelPrice !== "" && !fuelPriceValid}
                      />
                    </div>
                  </div>

                  {endTripError && (
                    <div role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                      <span>{endTripError}</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-3 border-t border-white/10 p-4">
                  <Button variant="ghost" className="flex-1" onClick={cancelEndConfirm} disabled={endingTrip}>
                    {t("newTrip.cancel")}
                  </Button>
                  <Button variant="primary" className="flex-1" onClick={confirmEndTrip} disabled={endingTrip || !fuelValid || !fuelPriceValid}>
                    {endingTrip ? (
                      <>
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                        {t("newTrip.endingTripEllipsis")}
                      </>
                    ) : (
                      <>
                        <CheckCircle2 size={16} /> {t("newTrip.confirmEndTrip")}
                      </>
                    )}
                  </Button>
                </div>
              </GlassCard>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {trip && (
        <>
          <ReassignmentModal open={showReassignModal} onClose={() => setShowReassignModal(false)} tripId={trip.id} />
          <ChatPanel open={showChatPanel} onClose={() => setShowChatPanel(false)} role="driver" tripId={trip.id} />
        </>
      )}
    </div>
  );
}

function TripStepper({ stage }) {
  const { t } = useTranslation();
  const idx = STEPS.findIndex((s) => s.key === stage || (stage === "predicting" && s.key === "review") || (stage === "feedback" && s.key === "summary"));
  return (
    <div className="mb-6 flex items-center justify-between">
      {STEPS.map((s, i) => (
        <div key={s.key} className="flex flex-1 items-center">
          <div className="flex flex-col items-center gap-1">
            <div className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors
              ${i < idx ? "border-amber bg-amber text-[#12100a]" : i === idx ? "border-amber text-amber" : "border-white/15 text-ink-faint"}`}>
              {i < idx ? "✓" : i + 1}
            </div>
            <span className={`hidden text-[10px] sm:block ${i <= idx ? "text-ink-dim" : "text-ink-faint"}`}>{t(s.labelKey)}</span>
          </div>
          {i < STEPS.length - 1 && <div className={`mx-1 h-px flex-1 ${i < idx ? "bg-amber" : "bg-white/10"}`} />}
        </div>
      ))}
    </div>
  );
}

function TripSidebar({ form, stage, prediction, liveConditions, weatherRadiusKm }) {
  const { t } = useTranslation();
  const ecoTips = t("newTrip.ecoTips", { returnObjects: true });
  const tip = ecoTips[new Date().getDate() % ecoTips.length];
  const isOngoing = stage === "ongoing";
  const weather = isOngoing
    ? (liveConditions || (form._live_city ? {
        city: form._live_city, temp: form._live_temp, humidity: form._live_humidity, wind: form._live_wind,
        radiusKm: form._live_radius_km, areaAlert: form._live_area_alert, severeWeather: form._live_severe_weather,
      } : null))
    : (form._live_city ? {
        city: form._live_city, temp: form._live_temp, humidity: form._live_humidity, wind: form._live_wind,
        radiusKm: form._live_radius_km, areaAlert: form._live_area_alert, severeWeather: form._live_severe_weather,
      } : null);
  const radiusLabel = `${weather?.radiusKm ? Math.round(weather.radiusKm) : weatherRadiusKm} km`;

  return (
    <div className="hidden lg:block">
      <div className="sticky top-8 space-y-4">
        {weather && (
          <GlassCard className="p-4">
            <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-dim">
              {isOngoing && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />}
              {isOngoing ? t("newTrip.weatherAroundYou", { defaultValue: "Weather around you" })
                         : t("newTrip.weatherAroundPickup", { defaultValue: "Weather around pickup" })}
            </p>
            <p className="text-[11px] text-ink-faint">{t("newTrip.withinRadius", { radius: radiusLabel, defaultValue: `Within ${radiusLabel}` })}</p>
            <p className="mt-2 font-display text-2xl font-semibold text-ink">{weather.temp}°C</p>
            <p className="text-xs text-ink-dim">{weather.city} · {weather.humidity}% {t("newTrip.humidityWord")} · {weather.wind} km/h {t("newTrip.windWord")}</p>
            <div className="mt-2">
              {weather.severeWeather && weather.areaAlert ? (
                <Badge tone="warning">{weather.areaAlert}</Badge>
              ) : (
                <Badge tone="success">{t("newTrip.noSevereWeather", { defaultValue: "No severe weather nearby" })}</Badge>
              )}
            </div>
            {isOngoing && <p className="mt-2 text-[10px] text-ink-faint">{t("newTrip.updatesWhileDriving")}</p>}
          </GlassCard>
        )}

        {prediction && (stage === "review" || stage === "ongoing" || stage === "feedback" || stage === "summary") && (
          <GlassCard className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">Trip at a Glance</p>
            <div className="mt-3 space-y-2 text-xs">
              <div className="flex justify-between"><span className="text-ink-dim">Fuel</span><span className="text-ink">{prediction.predicted_fuel_l} L</span></div>
              <div className="flex justify-between"><span className="text-ink-dim">CO2</span><span className="text-ink">{prediction.predicted_co2_kg} kg</span></div>
              <div className="flex justify-between"><span className="text-ink-dim">Cost</span><span className="text-ink">₹{prediction.predicted_cost}</span></div>
              <div className="flex justify-between"><span className="text-ink-dim">Eco Score</span><span className="text-ink">{prediction.predicted_eco_score}/100</span></div>
              {prediction.overall_score != null && (
                <div className="flex justify-between"><span className="text-ink-dim">Overall AI Score</span><span className="text-amber">{prediction.overall_score}/100</span></div>
              )}
            </div>
          </GlassCard>
        )}

        <GlassCard className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">Eco Driving Tip</p>
          <p className="mt-2 text-sm leading-relaxed text-ink-dim">{tip}</p>
        </GlassCard>

        <GlassCard className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">How This Trip Is Scored</p>
          <ul className="mt-2 space-y-1.5 text-xs text-ink-dim">
            <li>• 6 AI models trained on 2,000 real fleet trips</li>
            <li>• Route options come from live Google Routes data</li>
            <li>• Weather pulled from OpenWeather in real time</li>
            <li>• Score blends eco impact, cost, and vehicle health</li>
          </ul>
        </GlassCard>
      </div>
    </div>
  );
}

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-3 text-center">
      <Icon className="mx-auto text-ink-dim" size={16} />
      <p className="mt-1 font-mono text-sm text-ink">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</p>
    </div>
  );
}

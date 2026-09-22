import { useEffect, useState, useRef } from "react";
import { Radio, MapPin, Truck, LocateFixed, AlertTriangle, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import IsoTruckBadge from "../../components/IsoTruckBadge";
import { loadGoogleMaps } from "../../lib/googleMaps";
import { DARK_MAP_STYLE } from "../../lib/mapStyle";
import api from "../../lib/api";

export default function AdminLiveFleet() {
  const { t } = useTranslation();
  const [trips, setTrips] = useState([]);
  const [depots, setDepots] = useState([]);
  const [depotFilter, setDepotFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [mapError, setMapError] = useState("");
  const [deviations, setDeviations] = useState([]);
  const mapRef = useRef(null);
  const mapObjRef = useRef(null);
  const markersRef = useRef({});
  const hasFitBoundsRef = useRef(false);

  async function loadDeviations() {
    try {
      const res = await api.get("/admin/route-deviations", { params: { status: "Active" } });
      setDeviations(res.data);
    } catch {
      // non-critical panel — a failed fetch here shouldn't block the live map
    }
  }

  async function resolveDeviation(id) {
    try {
      await api.post(`/admin/route-deviations/${id}/resolve`);
      setDeviations((prev) => prev.filter((d) => d.id !== id));
    } catch {
      // leave it in the list — admin can retry
    }
  }

  async function load() {
    const res = await api.get("/admin/live-fleet", { params: depotFilter ? { depot_id: depotFilter } : {} });
    setTrips(res.data);
    setLoading(false);
    return res.data;
  }

  useEffect(() => { api.get("/admin/depots").then((r) => setDepots(r.data)); }, []);

  useEffect(() => {
    loadDeviations();
    const interval = setInterval(loadDeviations, 8000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let interval;
    hasFitBoundsRef.current = false;
    (async () => {
      const [keyRes, tripData] = await Promise.all([api.get("/external/config/maps-key"), load()]);
      const google = await loadGoogleMaps(keyRes.data.key).catch(() => null);
      if (!google) {
        setMapError(t("adminLiveFleet.mapLoadError"));
        return;
      }
      if (!mapRef.current) return;

      try {
        if (!mapObjRef.current) {
          mapObjRef.current = new google.maps.Map(mapRef.current, {
            center: { lat: 20.5937, lng: 78.9629 }, // placeholder only — immediately replaced below by fitting to live vehicle positions
            zoom: 5,
            disableDefaultUI: true,
            styles: DARK_MAP_STYLE,
          });
        }
        renderMarkers(google, tripData);
        fitToFleet(google, tripData);
      } catch (err) {
        console.error("Live Fleet map drawing failed:", err);
        setMapError(t("adminLiveFleet.mapDrawError"));
      }
    })();

    interval = setInterval(async () => {
      const data = await load();
      if (window.google && mapObjRef.current) {
        try {
          renderMarkers(window.google, data);
          fitToFleet(window.google, data); // no-op after the first successful fit — see fitToFleet
        } catch (err) {
          console.error("Live Fleet marker refresh failed:", err);
        }
      }
    }, 8000);

    return () => clearInterval(interval);
  }, [depotFilter]);

  // Frames the map around wherever the fleet actually is — real positions,
  // not a hardcoded city — the same way Google Maps zooms to fit search
  // results instead of always opening on one fixed coordinate. Only runs
  // once per filter selection so it doesn't fight an admin who's manually
  // panned/zoomed to look at something specific.
  function fitToFleet(google, tripData) {
    if (hasFitBoundsRef.current) return;
    const positioned = tripData.filter((t) => t.current_lat != null);
    if (positioned.length === 0) return;
    const bounds = new google.maps.LatLngBounds();
    positioned.forEach((t) => bounds.extend({ lat: t.current_lat, lng: t.current_lng }));
    mapObjRef.current.fitBounds(bounds, 60);
    if (positioned.length === 1) mapObjRef.current.setZoom(11); // fitBounds over-zooms for a single point
    hasFitBoundsRef.current = true;
  }

  function renderMarkers(google, tripData) {
    const seen = new Set();
    tripData.forEach((t) => {
      if (t.current_lat == null) return;
      seen.add(t.trip_id);
      const pos = { lat: t.current_lat, lng: t.current_lng };
      const icon = t.live && Number.isFinite(t.heading)
        ? { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 6, rotation: t.heading, fillColor: "#4285F4", fillOpacity: 1, strokeColor: "#12100a", strokeWeight: 1.5 }
        : { path: google.maps.SymbolPath.CIRCLE, scale: 7, fillColor: t.live ? "#4285F4" : "#F0B429", fillOpacity: 1, strokeColor: "#12100a", strokeWeight: 1.5 };
      if (markersRef.current[t.trip_id]) {
        markersRef.current[t.trip_id].setPosition(pos);
        markersRef.current[t.trip_id].setIcon(icon);
      } else {
        markersRef.current[t.trip_id] = new google.maps.Marker({
          position: pos, map: mapObjRef.current,
          title: `${t.vehicle_no} — ${t.driver_name}${t.live ? " (live GPS)" : " (estimated)"}`,
          icon,
        });
      }
    });
    Object.keys(markersRef.current).forEach((id) => {
      if (!seen.has(Number(id))) { markersRef.current[id].setMap(null); delete markersRef.current[id]; }
    });
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="glow-chip-cyan flex h-8 w-8 items-center justify-center rounded-lg">
            <IsoTruckBadge size={18} />
          </span>
          <div className="flex items-center gap-2 text-sm text-ink-dim">
            <span className="flex h-2 w-2 animate-pulse rounded-full bg-cyan shadow-[0_0_8px_2px_rgba(34,211,238,0.6)]" />
            {t("adminLiveFleet.liveAutoRefresh")}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { hasFitBoundsRef.current = false; if (window.google && mapObjRef.current) fitToFleet(window.google, trips); }}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-ink-dim hover:border-cyan/40 hover:text-cyan-soft"
          >
            <LocateFixed size={13} /> {t("adminLiveFleet.recenterToFleet")}
          </button>
          {depots.length > 0 && (
            <select
              value={depotFilter}
              onChange={(e) => setDepotFilter(e.target.value)}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-ink-dim"
            >
              <option value="">{t("adminLiveFleet.allDepots")}</option>
              {depots.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
        </div>
      </div>

      {deviations.length > 0 && (
        <GlassCard className="mb-4 border-danger/30 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-danger">
            <AlertTriangle size={15} /> {t("adminLiveFleet.activeDeviationAlerts", { count: deviations.length })}
          </div>
          <div className="space-y-2">
            {deviations.map((dv) => (
              <div key={dv.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs">
                <div>
                  <span className="font-medium text-ink">{dv.trip_code}</span>
                  <span className="text-ink-dim"> · {dv.driver_name} {t("adminLiveFleet.offRouteBy", { meters: dv.deviation_m })}</span>
                  <span className="ml-2 text-ink-faint">{new Date(dv.detected_at).toLocaleTimeString()}</span>
                </div>
                <button
                  onClick={() => resolveDeviation(dv.id)}
                  className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-ink-dim hover:border-success/40 hover:text-success"
                >
                  <Check size={12} /> {t("adminLiveFleet.resolve")}
                </button>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      <GlassCard className="trip-console-trim mb-6 overflow-hidden p-0">
        {mapError ? (
          <div className="p-4 text-xs text-danger">{mapError}</div>
        ) : (
          <div ref={mapRef} className="h-80 w-full" />
        )}
        <p className="border-t border-white/10 px-4 py-2 text-[11px] text-ink-faint">
          <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#4285F4] align-middle" /> {t("adminLiveFleet.liveGpsLegend")}
          <span className="ml-3 mr-1 inline-block h-2 w-2 rounded-full bg-amber align-middle" /> {t("adminLiveFleet.estimatedLegend")}
        </p>
      </GlassCard>

      {loading ? (
        <p className="text-ink-dim">{t("adminLiveFleet.loadingLiveFleet")}</p>
      ) : trips.length === 0 ? (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <Truck size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminLiveFleet.noVehiclesActive")}</p>
          <p className="max-w-sm text-xs text-ink-faint">
            {t("adminLiveFleet.liveFleetDesc")}
          </p>
        </GlassCard>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {trips.map((t2) => (
            <GlassCard key={t2.trip_id} className="p-5">
              <div className="flex items-center justify-between">
                <div className={`flex items-center gap-2 text-xs ${t2.live ? "text-[#4285F4]" : "text-success"}`}>
                  <Radio size={14} className="animate-pulse" /> {t2.live ? t("adminLiveFleet.liveGps") : t("adminLiveFleet.movingEstimated")}
                </div>
                <Badge tone={t2.maintenance_risk === "High" ? "danger" : t2.maintenance_risk === "Medium" ? "warning" : "success"}>
                  {t2.maintenance_risk === "High" ? t("adminLiveFleet.riskHigh") : t2.maintenance_risk === "Medium" ? t("adminLiveFleet.riskMedium") : t("adminLiveFleet.riskLow")} {t("adminLiveFleet.riskSuffix")}
                </Badge>
              </div>
              <p className="mt-3 font-medium text-ink">{t2.driver_name}</p>
              <p className="text-xs text-ink-dim">{t2.vehicle_no} · {t2.trip_code}</p>
              {t2.live && t2.speed_kmph != null && (
                <p className="mt-1 text-[11px] text-ink-faint">{t("adminLiveFleet.speedLabel", { speed: Math.round(t2.speed_kmph) })}</p>
              )}
              <div className="mt-3 flex items-center gap-1.5 text-xs text-ink-dim">
                <MapPin size={13} /> {t2.source} → {t2.destination}
              </div>
              {t2.progress_pct != null && (
                <div className="mt-3">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                    <div className="h-full rounded-full bg-amber" style={{ width: `${t2.progress_pct}%` }} />
                  </div>
                  <p className="mt-1 text-[10px] text-ink-faint">{t("adminLiveFleet.ofEstimatedRoute", { pct: t2.progress_pct })}</p>
                </div>
              )}
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-white/10 pt-3 text-center">
                <div><p className="font-mono text-sm text-ink">{t2.distance_km} km</p><p className="text-[10px] text-ink-faint">{t("adminLiveFleet.distance")}</p></div>
                <div><p className="font-mono text-sm text-amber">{t2.predicted_co2_kg} kg</p><p className="text-[10px] text-ink-faint">{t("adminLiveFleet.predictedCo2")}</p></div>
                <div><p className="font-mono text-sm text-ink">{t2.elapsed_min}m</p><p className="text-[10px] text-ink-faint">{t("adminLiveFleet.elapsed")}</p></div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}

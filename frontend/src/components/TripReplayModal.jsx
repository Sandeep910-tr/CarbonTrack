import { useEffect, useRef, useState } from "react";
import { X, Play, Pause, MapPin, Navigation } from "lucide-react";
import { GlassCard, Badge } from "./ui";
import { loadGoogleMaps } from "../lib/googleMaps";
import { DARK_MAP_STYLE } from "../lib/mapStyle";
import api from "../lib/api";

const SPEEDS = [
  { label: "10x", rate: 10 },
  { label: "60x", rate: 60 },
  { label: "300x", rate: 300 },
];

function fmtClock(sec) {
  if (sec == null || !Number.isFinite(sec)) return "--:--";
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

// Linear-interpolate a lat/lng position at a given elapsed time, either along
// the real GPS ping history or (when no pings were recorded) along a straight
// line between origin and destination — same idea as the Live Fleet fallback.
function positionAt(elapsed, points, fallbackFrom, fallbackTo, totalSec) {
  if (points.length > 0) {
    if (elapsed <= points[0].elapsed_sec) return points[0];
    if (elapsed >= points[points.length - 1].elapsed_sec) return points[points.length - 1];
    for (let i = 1; i < points.length; i++) {
      if (points[i].elapsed_sec >= elapsed) {
        const a = points[i - 1], b = points[i];
        const span = b.elapsed_sec - a.elapsed_sec || 1;
        const f = (elapsed - a.elapsed_sec) / span;
        return { lat: a.lat + (b.lat - a.lat) * f, lng: a.lng + (b.lng - a.lng) * f };
      }
    }
    return points[points.length - 1];
  }
  if (fallbackFrom && fallbackTo && totalSec > 0) {
    const f = Math.min(elapsed / totalSec, 1);
    return { lat: fallbackFrom.lat + (fallbackTo.lat - fallbackFrom.lat) * f, lng: fallbackFrom.lng + (fallbackTo.lng - fallbackFrom.lng) * f };
  }
  return null;
}

export default function TripReplayModal({ tripId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(SPEEDS[1]);

  const [mapNode, setMapNode] = useState(null);
  const mapObjRef = useRef(null);
  const markerRef = useRef(null);
  const tickRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [keyRes, locRes] = await Promise.all([
          api.get("/external/config/maps-key"),
          api.get(`/admin/trips/${tripId}/locations`),
        ]);
        if (cancelled) return;
        setData({ ...locRes.data, mapsKey: keyRes.data.key });
      } catch {
        if (!cancelled) setError("Couldn't load this trip's location history.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [tripId]);

  const recordedSpanSec = data?.started_at && data?.ended_at ? (new Date(data.ended_at) - new Date(data.started_at)) / 1000 : 0;
  const totalSec = data?.points?.length
    ? data.points[data.points.length - 1].elapsed_sec
    // Some historical/seeded trips have started_at === ended_at (no real duration
    // recorded). Fall back to a rough estimate from distance so replay still has
    // something to animate through, assuming a modest 40 km/h average speed.
    : (recordedSpanSec > 0 ? recordedSpanSec : Math.max((data?.distance_km || 0) / 40 * 3600, 30));

  // Build the map once we have both the key and the trip's location data.
  useEffect(() => {
    if (!data?.mapsKey || !mapNode) return;
    let cancelled = false;
    (async () => {
      const google = await loadGoogleMaps(data.mapsKey).catch(() => null);
      if (!google || cancelled) return;

      try {
        const map = new google.maps.Map(mapNode, {
          zoom: 7, center: { lat: 20.5937, lng: 78.9629 }, disableDefaultUI: true, styles: DARK_MAP_STYLE,
        });
        mapObjRef.current = map;

        const bounds = new google.maps.LatLngBounds();
        if (data.points.length > 0) {
          const path = data.points.map((p) => ({ lat: p.lat, lng: p.lng }));
          new google.maps.Polyline({ path, map, strokeColor: "#4285F4", strokeWeight: 4 });
          path.forEach((p) => bounds.extend(p));
        } else if (data.origin_lat && data.dest_lat) {
          const path = [{ lat: data.origin_lat, lng: data.origin_lng }, { lat: data.dest_lat, lng: data.dest_lng }];
          new google.maps.Polyline({ path, map, strokeColor: "#F0B429", strokeWeight: 4, icons: [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 1, scale: 3 }, offset: "0", repeat: "14px" }] });
          path.forEach((p) => bounds.extend(p));
        }
        if (data.origin_lat) bounds.extend({ lat: data.origin_lat, lng: data.origin_lng });
        if (data.dest_lat) bounds.extend({ lat: data.dest_lat, lng: data.dest_lng });
        if (!bounds.isEmpty()) map.fitBounds(bounds, 40);

        if (data.origin_lat) new google.maps.Marker({ position: { lat: data.origin_lat, lng: data.origin_lng }, map, label: "A" });
        if (data.dest_lat) new google.maps.Marker({ position: { lat: data.dest_lat, lng: data.dest_lng }, map, label: "B" });

        markerRef.current = new google.maps.Marker({
          map, zIndex: 999,
          icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: "#4285F4", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2 },
        });
      } catch (err) {
        console.error("Trip replay map drawing failed:", err);
      }
    })();
    return () => { cancelled = true; };
  }, [data, mapNode]);

  // Move the marker whenever elapsed time changes (from playback or scrubbing).
  useEffect(() => {
    if (!data || !markerRef.current) return;
    const from = data.origin_lat != null ? { lat: data.origin_lat, lng: data.origin_lng } : null;
    const to = data.dest_lat != null ? { lat: data.dest_lat, lng: data.dest_lng } : null;
    const pos = positionAt(elapsed, data.points || [], from, to, totalSec);
    if (pos) {
      markerRef.current.setPosition(pos);
      if (mapObjRef.current) mapObjRef.current.panTo(pos);
    }
  }, [elapsed, data, totalSec]);

  // Playback loop.
  useEffect(() => {
    if (!playing) { clearInterval(tickRef.current); return; }
    tickRef.current = setInterval(() => {
      setElapsed((e) => {
        const next = e + speed.rate * 0.25;
        if (next >= totalSec) { setPlaying(false); return totalSec; }
        return next;
      });
    }, 250);
    return () => clearInterval(tickRef.current);
  }, [playing, speed, totalSec]);

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose} role="presentation">
      <GlassCard strong className="w-full max-w-3xl overflow-hidden" role="dialog" aria-modal="true" aria-label="Trip Replay" >
        <div onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between border-b border-white/10 p-4">
            <div className="flex items-center gap-2">
              <Navigation size={16} className="text-amber" />
              <h3 className="font-display text-sm font-semibold text-ink">
                Trip Replay {data?.trip_code && <span className="font-mono text-ink-faint">— {data.trip_code}</span>}
              </h3>
              {data && (
                <Badge tone={data.has_real_gps ? "success" : "warning"}>
                  {data.has_real_gps ? "Real GPS" : "Estimated path"}
                </Badge>
              )}
            </div>
            <button onClick={onClose} aria-label="Close" className="text-ink-dim hover:text-ink"><X size={20} /></button>
          </div>

          {loading ? (
            <div className="flex h-72 items-center justify-center text-sm text-ink-dim">Loading trip locations…</div>
          ) : error ? (
            <div className="flex h-72 items-center justify-center text-sm text-danger">{error}</div>
          ) : (
            <>
              <div className="flex items-center justify-between px-4 pt-3 text-xs text-ink-dim">
                <span className="flex items-center gap-1.5"><MapPin size={12} /> {data.source} → {data.destination}</span>
                {!data.has_real_gps && (
                  <span className="text-ink-faint">No GPS pings were recorded for this trip — showing an estimated straight-line path.</span>
                )}
              </div>
              <div ref={setMapNode} className="m-4 h-72 rounded-xl" />

              <div className="flex items-center gap-4 border-t border-white/10 p-4">
                <button
                  onClick={() => setPlaying((p) => !p)}
                  disabled={totalSec <= 0}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.05] text-ink backdrop-blur-md transition-colors hover:bg-white/[0.09] disabled:opacity-40"
                >
                  {playing ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <span className="w-12 shrink-0 font-mono text-xs text-ink-dim">{fmtClock(elapsed)}</span>
                <input
                  type="range" min={0} max={Math.max(totalSec, 1)} step={1} value={Math.min(elapsed, totalSec)}
                  onChange={(e) => { setPlaying(false); setElapsed(Number(e.target.value)); }}
                  className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-white/10 accent-amber"
                />
                <span className="w-12 shrink-0 text-right font-mono text-xs text-ink-faint">{fmtClock(totalSec)}</span>
                <div className="flex shrink-0 gap-1">
                  {SPEEDS.map((s) => (
                    <button
                      key={s.label}
                      onClick={() => setSpeed(s)}
                      className={`rounded-md px-2 py-1 text-[11px] font-medium ${speed.label === s.label ? "bg-amber/20 text-amber" : "text-ink-faint hover:text-ink-dim"}`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </GlassCard>
    </div>
  );
}

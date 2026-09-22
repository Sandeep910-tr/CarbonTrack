import { useEffect, useState } from "react";
import { Navigation } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import TripReplayModal from "../../components/TripReplayModal";
import api from "../../lib/api";

const STATUS_KEY = { Completed: "trip.completed", Ongoing: "trip.ongoing", Cancelled: "trip.cancelled" };

export default function AdminTrips() {
  const { t } = useTranslation();
  const [trips, setTrips] = useState([]);
  const [replayTripId, setReplayTripId] = useState(null);

  useEffect(() => {
    api.get("/admin/trips").then((r) => setTrips(r.data.slice(0, 100)));
  }, []);

  return (
    <>
      <GlassCard className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-ink-faint">
              <th className="px-4 py-3">{t("newTrip.tripLabel")}</th>
              <th className="px-4 py-3">{t("trip.route")}</th>
              <th className="px-4 py-3">{t("trip.distance")}</th>
              <th className="px-4 py-3">{t("trip.fuel")}</th>
              <th className="px-4 py-3">CO2</th>
              <th className="px-4 py-3">{t("trip.cost")}</th>
              <th className="px-4 py-3">{t("common.status")}</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {trips.map((trip) => (
              <tr key={trip.id} className="border-b border-white/5 text-ink-dim hover:bg-white/[0.02]">
                <td className="px-4 py-3 font-mono text-xs text-ink">{trip.trip_code}</td>
                <td className="px-4 py-3">{trip.source} → {trip.destination}</td>
                <td className="px-4 py-3">{trip.distance_km} km</td>
                <td className="px-4 py-3">{trip.actual_fuel_l ?? trip.predicted_fuel_l} L</td>
                <td className="px-4 py-3">{trip.actual_co2_kg ?? trip.predicted_co2_kg} kg</td>
                <td className="px-4 py-3">₹{trip.actual_cost ?? trip.predicted_cost}</td>
                <td className="px-4 py-3">
                  <Badge tone={trip.status === "Completed" ? "success" : trip.status === "Ongoing" ? "warning" : "neutral"}>
                    {STATUS_KEY[trip.status] ? t(STATUS_KEY[trip.status]) : trip.status}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  {(trip.status === "Completed" || trip.status === "Ongoing") && (
                    <button
                      onClick={() => setReplayTripId(trip.id)}
                      className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-ink-dim hover:border-amber/40 hover:text-amber"
                    >
                      <Navigation size={12} /> {t("adminTrips.replay")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>

      {replayTripId && <TripReplayModal tripId={replayTripId} onClose={() => setReplayTripId(null)} />}
    </>
  );
}

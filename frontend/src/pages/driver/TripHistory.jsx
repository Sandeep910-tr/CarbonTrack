import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Route as RouteIcon, PlusCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge, Button, StatCard } from "../../components/ui";
import { Fuel, Leaf, DollarSign } from "lucide-react";
import api from "../../lib/api";

const STATUS_KEY = { Completed: "trip.completed", Ongoing: "trip.ongoing", Cancelled: "trip.cancelled" };

export default function TripHistory() {
  const { t } = useTranslation();
  const [trips, setTrips] = useState([]);
  useEffect(() => { api.get("/driver/trips").then((r) => setTrips(r.data)); }, []);

  const completed = trips.filter((t) => t.status === "Completed");
  const totalFuel = completed.reduce((s, t) => s + (t.actual_fuel_l || 0), 0);
  const totalCo2 = completed.reduce((s, t) => s + (t.actual_co2_kg || 0), 0);
  const totalCost = completed.reduce((s, t) => s + (t.actual_cost || 0), 0);

  return (
    <div className="space-y-6">
      {trips.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label={t("tripHistory.totalFuelUsed")} value={totalFuel.toFixed(1)} unit="L" icon={Fuel} accent="indigo" />
          <StatCard label={t("tripHistory.totalCo2Emitted")} value={totalCo2.toFixed(1)} unit="kg" icon={Leaf} accent="success" />
          <StatCard label={t("tripHistory.totalFuelCost")} value={`₹${totalCost.toFixed(0)}`} icon={DollarSign} accent="success" />
        </div>
      )}

      <div className="space-y-3">
        {trips.length === 0 && (
          <GlassCard className="flex flex-col items-center gap-3 p-10 text-center">
            <RouteIcon size={28} className="text-ink-faint" />
            <p className="text-sm text-ink-dim">{t("tripHistory.noTripsYet")}</p>
            <Link to="/driver/new-trip"><Button variant="primary"><PlusCircle size={15} /> {t("tripHistory.startNewTrip")}</Button></Link>
          </GlassCard>
        )}
        {trips.map((tr) => (
          <GlassCard key={tr.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-ink">{tr.source} → {tr.destination}</p>
              <p className="text-xs text-ink-faint">{tr.trip_code} · {tr.distance_km} km · {new Date(tr.created_at).toLocaleDateString()}</p>
            </div>
            <div className="flex items-center gap-4 text-xs text-ink-dim">
              <span>{t("trip.fuel")} {tr.actual_fuel_l ?? tr.predicted_fuel_l} L</span>
              <span>CO2 {tr.actual_co2_kg ?? tr.predicted_co2_kg} kg</span>
              <span>₹{tr.actual_cost ?? tr.predicted_cost}</span>
              <Badge tone={tr.status === "Completed" ? "success" : tr.status === "Ongoing" ? "warning" : "neutral"}>
                {STATUS_KEY[tr.status] ? t(STATUS_KEY[tr.status]) : tr.status}
              </Badge>
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}

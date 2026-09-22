import { useEffect, useState } from "react";
import { Truck, Gauge, Fuel, Wrench, ShieldCheck, Weight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge, StatCard } from "../../components/ui";
import api from "../../lib/api";

const HEALTH_ACCENT = (score) => (score >= 80 ? "success" : score >= 50 ? "amber" : "danger");

export default function DriverVehicle() {
  const { t } = useTranslation();
  const [vehicle, setVehicle] = useState(undefined); // undefined = loading, null = none assigned

  useEffect(() => {
    api.get("/driver/profile").then((r) => setVehicle(r.data.vehicle || null));
  }, []);

  if (vehicle === undefined) return <p className="text-ink-dim">…</p>;

  if (vehicle === null) {
    return (
      <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
        <Truck size={28} className="text-ink-faint" />
        <p className="text-sm text-ink-dim">{t("driverVehicle.none", "No vehicle currently assigned to you.")}</p>
      </GlassCard>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <GlassCard className="p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-amber/15 p-3 text-amber"><Truck size={22} /></div>
            <div>
              <h1 className="font-display text-lg font-semibold text-ink">{vehicle.vehicle_no}</h1>
              <p className="text-xs text-ink-dim">{vehicle.vehicle_code} · {vehicle.vehicle_type} · {vehicle.fuel_type}</p>
            </div>
          </div>
          <Badge tone={vehicle.status === "Active" ? "success" : "neutral"}>{vehicle.status}</Badge>
        </div>
      </GlassCard>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard icon={Gauge} label={t("driverVehicle.mileage", "Mileage")} value={vehicle.mileage} unit="km/l" />
        <StatCard icon={Weight} label={t("driverVehicle.capacity", "Capacity")} value={vehicle.capacity_kg} unit="kg" />
        <StatCard icon={ShieldCheck} label={t("driverVehicle.healthScore", "Health Score")} value={Math.round(vehicle.health_score)} accent={HEALTH_ACCENT(vehicle.health_score)} />
        <StatCard icon={Fuel} label={t("driverVehicle.totalKm", "Total Distance")} value={vehicle.total_km} unit="km" />
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center gap-2">
          <Wrench size={15} className="text-amber" />
          <h3 className="font-display text-sm font-semibold text-ink">{t("driverVehicle.maintenance", "Maintenance")}</h3>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-ink-dim sm:grid-cols-3">
          <div>
            <p className="text-xs text-ink-faint">{t("driverVehicle.lastService", "Last Service")}</p>
            <p className="text-ink">{vehicle.last_service_date || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">{t("driverVehicle.daysSinceService", "Days Since")}</p>
            <p className="text-ink">{vehicle.days_since_service ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">{t("driverVehicle.serviceCount", "Service Count")}</p>
            <p className="text-ink">{vehicle.service_count}</p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

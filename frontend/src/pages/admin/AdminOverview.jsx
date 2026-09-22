import { useEffect, useState } from "react";
import { Users, Truck, Route as RouteIcon, Leaf, Fuel, TreePine, Lightbulb, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatCard, GlassCard, Badge, EcoScoreRing } from "../../components/ui";
import api from "../../lib/api";

export default function AdminOverview() {
  const { t } = useTranslation();
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [insights, setInsights] = useState([]);
  const [sustain, setSustain] = useState(null);

  useEffect(() => {
    api.get("/admin/analytics/overview").then((r) => setStats(r.data));
    api.get("/admin/analytics/leaderboard").then((r) => setLeaderboard(r.data.slice(0, 5)));
    api.get("/admin/insights").then((r) => setInsights(r.data));
    api.get("/admin/sustainability").then((r) => setSustain(r.data));
  }, []);

  if (!stats) return <p className="text-ink-dim">{t("adminOverview.loadingFleetOverview")}</p>;

  return (
    <div className="space-y-6">
      <GlassCard strong className="trip-console-trim p-6">
        <h1 className="font-display text-2xl font-semibold text-ink">{t("adminOverview.fleetOverview")}</h1>
      </GlassCard>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("adminOverview.approvedDrivers")} value={stats.approved_drivers} icon={Users} />
        <StatCard label={t("adminOverview.totalVehicles")} value={stats.total_vehicles} icon={Truck} accent="indigo" />
        <StatCard label={t("adminOverview.completedTrips")} value={stats.completed_trips} icon={RouteIcon} />
        <StatCard label={t("adminOverview.pendingApprovals")} value={stats.pending_drivers} icon={Users} accent={stats.pending_drivers > 0 ? "amber" : "success"} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("adminOverview.totalCo2Emitted")} value={stats.total_co2_kg} unit="kg" icon={Leaf} accent="success" />
        <StatCard label={t("adminOverview.totalFuelUsed")} value={stats.total_fuel_l} unit="L" icon={Fuel} accent="indigo" />
        <GlassCard interactive className="p-5">
          <div className="flex items-center gap-3">
            <div className="relative shrink-0">
              <EcoScoreRing score={stats.avg_eco_score} size={56} strokeWidth={6} />
              <span className="absolute inset-0 flex items-center justify-center font-display text-sm font-semibold text-ink">
                {Math.round(stats.avg_eco_score)}
              </span>
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminOverview.avgEcoScore")}</p>
              <p className="text-xs text-ink-dim">/100</p>
            </div>
          </div>
        </GlassCard>
        <StatCard label={t("adminOverview.treesEquivalent")} value={stats.trees_equivalent} unit="🌳" icon={TreePine} accent="success" />
      </div>

      {sustain && (
        <GlassCard className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.sustainabilityDashboard")}</h2>
            <Badge tone={sustain.carbon_budget_pct < 80 ? "success" : sustain.carbon_budget_pct < 100 ? "warning" : "danger"}>
              {sustain.carbon_budget_pct}{t("adminOverview.carbonBudgetUsed")}
            </Badge>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className={`h-full rounded-full ${sustain.carbon_budget_pct < 80 ? "bg-success" : sustain.carbon_budget_pct < 100 ? "bg-amber" : "bg-danger"}`}
              style={{ width: `${Math.min(sustain.carbon_budget_pct, 100)}%` }}
            />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 text-center">
            <div><p className="font-mono text-lg text-ink">{sustain.carbon_budget_used_kg} kg</p><p className="text-[11px] text-ink-faint">{t("adminOverview.ofTarget", { target: sustain.carbon_budget_target_kg })}</p></div>
            <div><p className="font-mono text-lg text-amber">{sustain.green_trips}</p><p className="text-[11px] text-ink-faint">{t("adminOverview.greenEcoTrips")}</p></div>
            <div><p className="font-mono text-lg text-ink">{sustain.green_trip_pct}%</p><p className="text-[11px] text-ink-faint">{t("adminOverview.ofAllTrips")}</p></div>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-6">
        <div className="flex items-center gap-2">
          <Lightbulb size={16} className="text-amber" />
          <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.aiInsights")}</h2>
        </div>
        <div className="mt-4 space-y-2">
          {insights.map((ins, i) => (
            <div key={i} className="flex items-start gap-3 rounded-xl bg-white/[0.02] px-4 py-3">
              {ins.severity === "high" ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-danger" /> : <Lightbulb size={15} className="mt-0.5 shrink-0 text-ink-dim" />}
              {/* ins.message is generated server-side; localizing it is a backend follow-up (see i18n docs). */}
              <p className="text-sm text-ink-dim">{ins.message}</p>
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="p-6">
        <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.driverEcoLeaderboard")}</h2>
        <div className="mt-4 space-y-2">
          {leaderboard.map((d, i) => (
            <div key={d.driver_code} className="flex items-center justify-between rounded-xl bg-white/[0.02] px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber/15 text-xs font-semibold text-amber">{i + 1}</span>
                <span className="text-sm text-ink">{d.name}</span>
                <span className="text-xs text-ink-faint">{d.driver_code}</span>
              </div>
              <Badge tone="success">{d.eco_score} {t("adminOverview.pts")}</Badge>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

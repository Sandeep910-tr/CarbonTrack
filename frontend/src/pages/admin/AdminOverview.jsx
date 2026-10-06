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
      <GlassCard strong className="trip-console-trim p-4 sm:p-6">
        <h1 className="font-display text-xl sm:text-2xl font-semibold text-ink">{t("adminOverview.fleetOverview")}</h1>
      </GlassCard>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("adminOverview.approvedDrivers")} value={stats.approved_drivers} icon={Users} />
        <StatCard label={t("adminOverview.totalVehicles")} value={stats.total_vehicles} icon={Truck} accent="indigo" />
        <StatCard label={t("adminOverview.completedTrips")} value={stats.completed_trips} icon={RouteIcon} />
        <StatCard label={t("adminOverview.pendingApprovals")} value={stats.pending_drivers} icon={Users} accent={stats.pending_drivers > 0 ? "amber" : "success"} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("adminOverview.totalCo2Emitted")} value={stats.total_co2_kg} unit="kg" icon={Leaf} accent="success" />
        <StatCard label={t("adminOverview.totalFuelUsed")} value={stats.total_fuel_l} unit="L" icon={Fuel} accent="indigo" />
        <GlassCard interactive className="p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="relative shrink-0">
              <EcoScoreRing score={stats.avg_eco_score} size={56} strokeWidth={6} />
              <span className="absolute inset-0 flex items-center justify-center font-display text-sm font-semibold text-ink">
                {Math.round(stats.avg_eco_score)}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-dim break-words">{t("adminOverview.avgEcoScore")}</p>
              <p className="text-xs text-ink-dim">/100</p>
            </div>
          </div>
        </GlassCard>
        <StatCard label={t("adminOverview.treesEquivalent")} value={stats.trees_equivalent} unit="🌳" icon={TreePine} accent="success" />
      </div>

      {sustain && (
        <GlassCard className="p-4 sm:p-6">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.sustainabilityDashboard")}</h2>
            <div className="self-start sm:self-auto">
              <Badge tone={sustain.carbon_budget_pct < 80 ? "success" : sustain.carbon_budget_pct < 100 ? "warning" : "danger"}>
                {sustain.carbon_budget_pct}{t("adminOverview.carbonBudgetUsed")}
              </Badge>
            </div>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className={`h-full rounded-full ${sustain.carbon_budget_pct < 80 ? "bg-success" : sustain.carbon_budget_pct < 100 ? "bg-amber" : "bg-danger"}`}
              style={{ width: `${Math.min(sustain.carbon_budget_pct, 100)}%` }}
            />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 text-center sm:grid-cols-3">
            <div className="rounded-xl bg-white/[0.02] p-2.5 sm:bg-transparent sm:p-0"><p className="font-mono text-base sm:text-lg text-ink break-words">{sustain.carbon_budget_used_kg} kg</p><p className="text-[11px] text-ink-faint">{t("adminOverview.ofTarget", { target: sustain.carbon_budget_target_kg })}</p></div>
            <div className="rounded-xl bg-white/[0.02] p-2.5 sm:bg-transparent sm:p-0"><p className="font-mono text-base sm:text-lg text-amber break-words">{sustain.green_trips}</p><p className="text-[11px] text-ink-faint">{t("adminOverview.greenEcoTrips")}</p></div>
            <div className="rounded-xl bg-white/[0.02] p-2.5 sm:bg-transparent sm:p-0"><p className="font-mono text-base sm:text-lg text-ink break-words">{sustain.green_trip_pct}%</p><p className="text-[11px] text-ink-faint">{t("adminOverview.ofAllTrips")}</p></div>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-4 sm:p-6">
        <div className="flex items-center gap-2">
          <Lightbulb size={16} className="text-amber shrink-0" />
          <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.aiInsights")}</h2>
        </div>
        <div className="mt-4 space-y-2">
          {insights.map((ins, i) => (
            <div key={i} className="flex items-start gap-3 rounded-xl bg-white/[0.02] px-3.5 py-3 sm:px-4">
              {ins.severity === "high" ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-danger" /> : <Lightbulb size={15} className="mt-0.5 shrink-0 text-ink-dim" />}
              {/* ins.message is generated server-side; localizing it is a backend follow-up (see i18n docs). */}
              <p className="min-w-0 flex-1 text-sm text-ink-dim break-words">{ins.message}</p>
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="p-4 sm:p-6">
        <h2 className="font-display text-base font-semibold text-ink">{t("adminOverview.driverEcoLeaderboard")}</h2>
        <div className="mt-4 space-y-2">
          {leaderboard.map((d, i) => (
            <div key={d.driver_code} className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.02] px-3.5 py-3 sm:px-4">
              <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber/15 text-xs font-semibold text-amber">{i + 1}</span>
                <span className="truncate text-sm text-ink">{d.name}</span>
                <span className="shrink-0 text-xs text-ink-faint">{d.driver_code}</span>
              </div>
              <span className="shrink-0">
                <Badge tone="success">{d.eco_score} {t("adminOverview.pts")}</Badge>
              </span>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

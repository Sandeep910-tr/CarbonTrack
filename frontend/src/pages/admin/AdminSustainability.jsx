import { useEffect, useState } from "react";
import { Leaf, TreeDeciduous, Route as RouteIcon, Target, TrendingDown, Zap, BarChart3, Gauge } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, StatCard } from "../../components/ui";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, Legend } from "recharts";
import api from "../../lib/api";

export default function AdminSustainability() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [trend, setTrend] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/admin/sustainability"),
      api.get("/admin/analytics/carbon-trend"),
    ]).then(([res, trendRes]) => {
      setData(res.data);
      setTrend(trendRes.data);
    });
  }, []);

  if (!data) return <GlassCard className="p-8 text-center text-sm text-ink-dim">…</GlassCard>;

  const { kpis, operational, analytics } = data;

  return (
    <div className="space-y-6">
      {/* KPI Section */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Leaf} label={t("adminSustainability.totalCo2", "Total CO2")} value={kpis.carbon_budget_used_kg} unit="kg" accent="amber" />
        <StatCard icon={Target} label={t("adminSustainability.budgetTarget", "Budget Target")} value={kpis.carbon_budget_target_kg} unit="kg" accent="indigo" />
        <StatCard icon={RouteIcon} label={t("adminSustainability.greenTrips", "Eco Route Adoption")} value={kpis.green_trip_pct} unit="%" accent="success" />
        <StatCard icon={TreeDeciduous} label={t("adminSustainability.treesEquivalent", "Trees Equivalent")} value={kpis.trees_equivalent} unit="trees" accent="amber" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Budget Progress */}
        <GlassCard className="lg:col-span-2 p-5">
          <div className="mb-4 flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <Target size={16} className="text-indigo" />
              <span className="text-ink-dim">{t("adminSustainability.carbonBudgetUsage", "Carbon Budget Usage")}</span>
            </div>
            <span className="font-mono text-ink">{kpis.carbon_budget_pct}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className={`h-full rounded-full transition-all duration-1000 ${kpis.carbon_budget_pct > 100 ? "bg-danger" : kpis.carbon_budget_pct > 80 ? "bg-amber" : "bg-success"}`}
              style={{ width: `${Math.min(kpis.carbon_budget_pct, 100)}%` }}
            />
          </div>
          <p className="mt-3 text-xs text-ink-faint">
            {kpis.carbon_budget_used_kg} kg used out of {kpis.carbon_budget_target_kg} kg annual target.
          </p>
        </GlassCard>

        {/* Reduction Opportunity */}
        <GlassCard className="p-5 flex flex-col justify-center items-center text-center">
          <TrendingDown size={32} className="text-success mb-3" />
          <h3 className="text-sm text-ink-dim mb-1">{t("adminSustainability.reductionOpp", "Estimated Reduction Opportunity")}</h3>
          <p className="text-3xl font-display font-bold text-success">{analytics.est_reduction_opportunity_kg} <span className="text-sm font-normal text-ink-dim">kg CO2</span></p>
          <p className="mt-2 text-xs text-ink-faint">Potential saving by optimizing non-eco routes</p>
        </GlassCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Operational Metrics Grid */}
        <GlassCard className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <Gauge size={18} className="text-cyan" />
            <h3 className="text-sm font-semibold text-ink">{t("adminSustainability.operationalMetrics", "Operational Efficiency")}</h3>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4">
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">Total Distance</span>
              <span className="text-xs font-mono text-ink">{operational.total_distance_km} km</span>
            </div>
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">Total Fuel</span>
              <span className="text-xs font-mono text-ink">{operational.total_fuel_l} L</span>
            </div>
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">CO2 / km</span>
              <span className="text-xs font-mono text-ink">{operational.co2_per_km} kg</span>
            </div>
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">Fuel / 100 km</span>
              <span className="text-xs font-mono text-ink">{operational.fuel_per_100km} L</span>
            </div>
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">Avg CO2 / Trip</span>
              <span className="text-xs font-mono text-ink">{operational.avg_co2_kg} kg</span>
            </div>
            <div className="flex justify-between items-center border-b border-white/5 pb-2">
              <span className="text-xs text-ink-dim">Prediction Coverage</span>
              <span className="text-xs font-mono text-ink">{operational.prediction_coverage_pct}%</span>
            </div>
          </div>
        </GlassCard>

        {/* Trend Chart */}
        <GlassCard className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 size={18} className="text-amber" />
            <h3 className="text-sm font-semibold text-ink">{t("adminSustainability.carbonTrend", "Daily Carbon Trend")}</h3>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="colorCo2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
                <XAxis dataKey="day" stroke="#ffffff40" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#ffffff40" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1A1F2B', borderColor: '#ffffff20', fontSize: '12px', color: '#fff' }}
                  itemStyle={{ color: '#f59e0b' }}
                />
                <Area type="monotone" dataKey="co2" stroke="#f59e0b" fillOpacity={1} fill="url(#colorCo2)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

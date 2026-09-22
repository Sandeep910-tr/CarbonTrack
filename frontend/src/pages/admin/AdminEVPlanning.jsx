import { useEffect, useState } from "react";
import { Zap, Fuel, Leaf, TrendingDown, Info } from "lucide-react";
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { useTranslation } from "react-i18next";
import { GlassCard } from "../../components/ui";
import api from "../../lib/api";

const YEAR_OPTIONS = [3, 5, 10];

function money(n) {
  if (n == null) return "—";
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

export default function AdminEVPlanning() {
  const { t } = useTranslation();
  const [years, setYears] = useState(5);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get("/admin/ev-planning", { params: { years } }).then((r) => { setData(r.data); setLoading(false); });
  }, [years]);

  if (loading || !data) return <p className="text-ink-dim">{t("adminEvPlanning.loadingEvAnalysis")}</p>;

  if (data.fleet_size_ice === 0) {
    return (
      <GlassCard className="p-8 text-center">
        <Zap className="mx-auto text-ink-faint" size={28} />
        <p className="mt-3 text-sm text-ink-dim">{t("adminEvPlanning.noNonEvVehicles")}</p>
      </GlassCard>
    );
  }

  const costChartData = data.timeline.map((tl) => ({
    year: `${t("adminEvPlanning.yr")} ${tl.year}`, ICE: tl.cumulative_cost_ice, EV: tl.cumulative_cost_ev,
  }));
  const co2ChartData = data.timeline.map((tl) => ({
    year: `${t("adminEvPlanning.yr")} ${tl.year}`, ICE: tl.cumulative_co2_ice_kg, EV: tl.cumulative_co2_ev_kg,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-dim">
          {t("adminEvPlanning.projectionIntro")} <span className="text-ink">{data.fleet_size_ice} {t("adminEvPlanning.nonElectricVehicles")}</span> {t("adminEvPlanning.projectionIntro2", { tripsAnalyzed: data.data_basis.trips_analyzed, days: data.data_basis.annualized_from_days })}
        </p>
        <div className="flex shrink-0 gap-1 rounded-lg border border-white/10 bg-white/[0.03] p-1">
          {YEAR_OPTIONS.map((y) => (
            <button
              key={y}
              onClick={() => setYears(y)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${years === y ? "bg-amber/20 text-amber" : "text-ink-faint hover:text-ink-dim"}`}
            >
              {y} {t("adminEvPlanning.yr")}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <GlassCard interactive className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminEvPlanning.annualCo2Saved")}</p>
            <div className="rounded-lg bg-success/15 p-2 text-success"><Leaf size={18} /></div>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-ink">{(data.annual.co2_saved_kg / 1000).toFixed(1)} <span className="text-base font-normal text-ink-dim">{t("adminEvPlanning.tonnes")}</span></p>
        </GlassCard>
        <GlassCard interactive className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminEvPlanning.fleetUpfrontPremium")}</p>
            <div className="rounded-lg bg-amber/15 p-2 text-amber"><Zap size={18} /></div>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-ink">{money(data.fleet_upfront_premium_inr)}</p>
        </GlassCard>
        <GlassCard interactive className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminEvPlanning.costPayback")}</p>
            <div className="rounded-lg bg-indigo/15 p-2 text-indigo-soft"><TrendingDown size={18} /></div>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-ink">
            {data.payback_year ? t("adminEvPlanning.yearN", { year: data.payback_year }) : t("adminEvPlanning.moreThanYrs", { years })}
          </p>
        </GlassCard>
        <GlassCard interactive className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminEvPlanning.annualDistanceAnalyzed")}</p>
            <div className="rounded-lg bg-white/[0.06] p-2 text-ink-dim"><Fuel size={18} /></div>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-ink">{data.annual.distance_km.toLocaleString()} <span className="text-base font-normal text-ink-dim">km</span></p>
        </GlassCard>
      </div>

      <GlassCard className="p-6">
        <h2 className="font-display text-base font-semibold text-ink">{t("adminEvPlanning.cumulativeCostChart")}</h2>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={costChartData} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
              <YAxis tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`} width={56} />
              <Tooltip
                contentStyle={{ background: "#1A1712", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "#E7EAF3" }} formatter={(v) => money(v)}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="ICE" stroke="#FF6B6B" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="EV" stroke="#4ADE80" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {data.payback_year && (
          <p className="mt-2 text-xs text-ink-faint">{t("adminEvPlanning.paybackNote", { year: data.payback_year })}</p>
        )}
      </GlassCard>

      <GlassCard className="p-6">
        <h2 className="font-display text-base font-semibold text-ink">{t("adminEvPlanning.cumulativeCo2Chart")}</h2>
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={co2ChartData} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="iceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#FF6B6B" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#FF6B6B" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="evFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4ADE80" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#4ADE80" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
              <YAxis tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}t`} width={44} />
              <Tooltip
                contentStyle={{ background: "#1A1712", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "#E7EAF3" }} formatter={(v) => `${v.toLocaleString()} kg`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="ICE" stroke="#FF6B6B" strokeWidth={2} fill="url(#iceFill)" />
              <Area type="monotone" dataKey="EV" stroke="#4ADE80" strokeWidth={2} fill="url(#evFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-start gap-2 text-xs text-ink-faint">
          <Info size={14} className="mt-0.5 shrink-0" />
          <p>
            {t("adminEvPlanning.assumptionsText", {
              fuelPrice: money(data.assumptions.fuel_price_per_l),
              elecPrice: money(data.assumptions.electricity_price_per_kwh),
              evEfficiency: data.assumptions.ev_efficiency_kwh_per_km,
              gridFactor: data.assumptions.ev_grid_emission_factor_kg_per_kwh,
              icePrice: money(data.assumptions.ice_vehicle_price_inr),
              evPrice: money(data.assumptions.ev_vehicle_price_inr),
            })}
          </p>
        </div>
      </GlassCard>
    </div>
  );
}

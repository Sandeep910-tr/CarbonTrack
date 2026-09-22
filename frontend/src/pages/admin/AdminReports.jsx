import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { GlassCard, StatCard, Button, Badge } from "../../components/ui";
import {
  Leaf, Fuel, FileDown, AlertTriangle, Cpu, RefreshCw, TrendingUp, Truck, Users,
  ShieldCheck, Route as RouteIcon, TreePine, FileSpreadsheet, FileText, BarChart3,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "../../lib/api";

const TABS = [
  { key: "Trend", labelKey: "adminReports.tabTrend", icon: TrendingUp },
  { key: "Vehicles", labelKey: "adminReports.tabVehicles", icon: Truck },
  { key: "Drivers", labelKey: "adminReports.tabDrivers", icon: Users },
  { key: "Fuel", labelKey: "adminReports.tabFuel", icon: Fuel },
  { key: "Anomalies", labelKey: "adminReports.tabAnomalies", icon: AlertTriangle },
  { key: "ML Pipeline", labelKey: "adminReports.tabMlPipeline", icon: Cpu },
];

export default function AdminReports() {
  const { t } = useTranslation();
  const [tab, setTab] = useState("Trend");
  const [exporting, setExporting] = useState(null);

  // ---- Export functions are UNCHANGED (same endpoints, same payloads,
  // same download mechanism) — only wrapped with a brief per-button
  // loading state for the redesigned export control below. ----
  async function exportCsv() {
    setExporting("csv");
    try {
      const res = await api.get("/admin/analytics/carbon-trend");
      const rows = [["Day", "CO2 (kg)", "Fuel (L)"], ...res.data.map((t) => [t.day, t.co2, t.fuel])];
      downloadBlob(rows.map((r) => r.join(",")).join("\n"), "text/csv", "carbon_report.csv");
    } finally { setExporting(null); }
  }

  async function exportPdf() {
    setExporting("pdf");
    try {
      const res = await api.get("/admin/export/report.pdf", { responseType: "blob" });
      downloadBlob(res.data, "application/pdf", "fleet_report.pdf");
    } finally { setExporting(null); }
  }

  async function exportXlsx() {
    setExporting("xlsx");
    try {
      const res = await api.get("/admin/export/report.xlsx", { responseType: "blob" });
      downloadBlob(res.data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "fleet_report.xlsx");
    } finally { setExporting(null); }
  }

  function downloadBlob(data, type, filename) {
    const blob = data instanceof Blob ? data : new Blob([data], { type });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
  }

  return (
    <div className="space-y-6">
      {/* ---- Header: establishes Reports as a major section, not a lone
          settings-style page. Description is grounded in what the app
          actually does — no invented claims. ---- */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-white/10 pb-5">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-gradient-to-br from-indigo/20 to-cyan/10 p-2.5 text-cyan-soft">
            <BarChart3 size={22} />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink">{t("adminReports.headerTitle")}</h1>
            <p className="mt-0.5 text-sm text-ink-dim">{t("adminReports.headerDescription")}</p>
          </div>
        </div>

        {/* ---- Export: same three functions/endpoints as before, presented
            as one grouped, labeled control instead of three loose buttons. ---- */}
        <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-1.5">
          <span className="hidden pl-2 text-xs font-medium uppercase tracking-wide text-ink-faint sm:inline">
            {t("adminReports.exportLabel")}
          </span>
          <Button variant="ghost" className="!px-3 !py-1.5 text-xs" onClick={exportCsv} disabled={exporting !== null}>
            <FileText size={13} className={exporting === "csv" ? "animate-pulse" : ""} /> CSV
          </Button>
          <Button variant="ghost" className="!px-3 !py-1.5 text-xs" onClick={exportXlsx} disabled={exporting !== null}>
            <FileSpreadsheet size={13} className={exporting === "xlsx" ? "animate-pulse" : ""} /> Excel
          </Button>
          <Button variant="primary" className="!px-3 !py-1.5 text-xs" onClick={exportPdf} disabled={exporting !== null}>
            <FileDown size={13} className={exporting === "pdf" ? "animate-pulse" : ""} /> PDF
          </Button>
        </div>
      </div>

      {/* ---- Tabs: same tab keys/behavior, richer active/hover treatment + icons ---- */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {TABS.map((tb) => {
          const Icon = tb.icon;
          const active = tab === tb.key;
          return (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-xs font-medium transition-all duration-200 ${
                active
                  ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_16px_-2px_rgba(34,211,238,0.5)]"
                  : "border border-white/10 bg-white/[0.03] text-ink-dim hover:border-white/20 hover:bg-white/[0.06] hover:text-ink"
              }`}
            >
              <Icon size={13} /> {t(tb.labelKey)}
            </button>
          );
        })}
      </div>

      {tab === "Trend" && <TrendTab />}
      {tab === "Vehicles" && <VehiclesTab />}
      {tab === "Drivers" && <DriversTab />}
      {tab === "Fuel" && <FuelTab />}
      {tab === "Anomalies" && <AnomaliesTab />}
      {tab === "ML Pipeline" && <MlPipelineTab />}
    </div>
  );
}

// ---- Shared, purely-presentational loading/empty helpers (new — none of
// these tabs had any loading/empty treatment before; adding them doesn't
// change when/how data loads, only what's shown meanwhile). ----
function TableSkeleton({ cols = 5, rows = 5 }) {
  return (
    <div className="animate-pulse divide-y divide-white/5">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 px-4 py-3.5">
          {Array.from({ length: cols }).map((_, c) => (
            <div key={c} className="h-3 flex-1 rounded bg-white/[0.06]" />
          ))}
        </div>
      ))}
    </div>
  );
}

function EmptyState({ icon: Icon, message }) {
  return (
    <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
      <Icon size={26} className="text-ink-faint" />
      <p className="text-sm text-ink-dim">{message}</p>
    </GlassCard>
  );
}

function TrendTab() {
  const { t } = useTranslation();
  const [trend, setTrend] = useState(null);
  const [overview, setOverview] = useState(null);
  useEffect(() => {
    api.get("/admin/analytics/carbon-trend").then((r) => setTrend(r.data));
    api.get("/admin/analytics/overview").then((r) => setOverview(r.data));
  }, []);
  return (
    <div className="space-y-6">
      {overview && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <StatCard label={t("adminReports.fleetCarbonBudgetUsed")} value={overview.total_co2_kg} unit="kg" icon={Leaf} accent="success" />
          <StatCard label={t("adminReports.fleetFuelSpend")} value={`₹${overview.total_cost.toLocaleString()}`} icon={Fuel} accent="indigo" />
          <StatCard label={t("adminReports.totalTrips")} value={overview.total_trips} icon={RouteIcon} accent="cyan" />
          <StatCard label={t("adminReports.avgEcoScore")} value={overview.avg_eco_score} unit="/100" icon={ShieldCheck} accent="amber" />
          <StatCard label={t("adminReports.avgFleetHealth")} value={overview.avg_fleet_health} unit="%" icon={Truck} accent="indigo" />
          <StatCard label={t("adminReports.treesEquivalent")} value={overview.trees_equivalent} icon={TreePine} accent="success" />
        </div>
      )}
      <GlassCard className="p-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-base font-semibold text-ink">{t("adminReports.co2FuelTrend")}</h2>
        </div>
        {trend === null ? (
          <div className="flex h-[300px] items-center justify-center text-sm text-ink-dim">{t("adminReports.loadingTrend")}</div>
        ) : trend.length === 0 ? (
          <EmptyState icon={TrendingUp} message={t("adminReports.noTrendData")} />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="co2Fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4ADE80" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#4ADE80" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="fuelFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6E6BFF" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#6E6BFF" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: "#8891A8", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} />
              <YAxis tick={{ fill: "#8891A8", fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
              <Tooltip
                contentStyle={{ background: "#131a2b", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "#E7EAF3", fontWeight: 600, marginBottom: 4 }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "#8891A8" }} />
              <Area type="monotone" dataKey="co2" name="CO2 (kg)" stroke="#4ADE80" strokeWidth={2} fill="url(#co2Fill)" dot={false} />
              <Area type="monotone" dataKey="fuel" name="Fuel (L)" stroke="#6E6BFF" strokeWidth={2} fill="url(#fuelFill)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </GlassCard>
    </div>
  );
}

function VehiclesTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/admin/reports/vehicles").then((r) => setRows(r.data)); }, []);
  return (
    <GlassCard className="overflow-x-auto p-0">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-ink-faint">
            <th className="px-4 py-3 font-medium">{t("adminReports.colVehicle")}</th>
            <th className="px-4 py-3 font-medium">{t("adminReports.colType")}</th>
            <th className="px-4 py-3 font-medium">{t("adminReports.colHealth")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colTrips")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colTotalKm")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colFuelL")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colCo2Kg")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colL100km")}</th>
          </tr>
        </thead>
        {rows === null ? (
          <tbody><tr><td colSpan={8}><TableSkeleton cols={8} /></td></tr></tbody>
        ) : (
          <tbody>
            {rows.map((r) => (
              <tr key={r.vehicle_id} className="border-b border-white/5 text-ink-dim transition-colors hover:bg-white/[0.03]">
                <td className="px-4 py-3.5 font-medium text-ink">{r.vehicle_no}</td>
                <td className="px-4 py-3.5">{r.vehicle_type}</td>
                <td className="px-4 py-3.5">
                  <span className={`inline-flex items-center gap-1.5 ${r.health_score >= 80 ? "text-success" : r.health_score >= 50 ? "text-amber-soft" : "text-danger"}`}>
                    <span className="h-1.5 w-1.5 rounded-full bg-current" /> {r.health_score}%
                  </span>
                </td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.trip_count}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.total_km}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.total_fuel_l}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums text-ink">{r.total_co2_kg}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.avg_fuel_per_100km}</td>
              </tr>
            ))}
          </tbody>
        )}
      </table>
      {rows !== null && rows.length === 0 && (
        <div className="p-10 text-center">
          <Truck size={26} className="mx-auto mb-2 text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminReports.noVehicleData")}</p>
        </div>
      )}
    </GlassCard>
  );
}

function DriversTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/admin/reports/drivers").then((r) => setRows(r.data)); }, []);
  return (
    <GlassCard className="overflow-x-auto p-0">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-ink-faint">
            <th className="px-4 py-3 font-medium">{t("adminReports.colDriver")}</th>
            <th className="px-4 py-3 font-medium">{t("adminReports.colEcoScore")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colTrips")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colTotalKm")}</th>
            <th className="px-4 py-3 text-right font-medium">{t("adminReports.colCo2Kg")}</th>
          </tr>
        </thead>
        {rows === null ? (
          <tbody><tr><td colSpan={5}><TableSkeleton cols={5} /></td></tr></tbody>
        ) : (
          <tbody>
            {rows.map((r) => (
              <tr key={r.driver_id} className="border-b border-white/5 text-ink-dim transition-colors hover:bg-white/[0.03]">
                <td className="px-4 py-3.5">
                  <span className="font-medium text-ink">{r.name}</span>{" "}
                  <span className="text-ink-faint">({r.driver_code})</span>
                </td>
                <td className="px-4 py-3.5">
                  <span className={`inline-flex items-center gap-1.5 font-mono tabular-nums ${r.eco_score >= 80 ? "text-success" : r.eco_score >= 60 ? "text-amber-soft" : "text-danger"}`}>
                    {r.eco_score}
                  </span>
                </td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.trip_count}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums">{r.total_km}</td>
                <td className="px-4 py-3.5 text-right font-mono tabular-nums text-ink">{r.total_co2_kg}</td>
              </tr>
            ))}
          </tbody>
        )}
      </table>
      {rows !== null && rows.length === 0 && (
        <div className="p-10 text-center">
          <Users size={26} className="mx-auto mb-2 text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminReports.noDriverData")}</p>
        </div>
      )}
    </GlassCard>
  );
}

const FUEL_ACCENTS = { Diesel: "amber", Petrol: "danger", CNG: "cyan", Electric: "success" };

function FuelTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/admin/reports/fuel").then((r) => setRows(r.data)); }, []);

  if (rows === null) {
    return (
      <div className="grid animate-pulse gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-32 rounded-2xl bg-white/[0.03]" />)}
      </div>
    );
  }
  if (rows.length === 0) return <EmptyState icon={Fuel} message={t("adminReports.noFuelData")} />;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {rows.map((r) => (
        <GlassCard key={r.fuel_type} interactive className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{r.fuel_type}</p>
            <div className={`rounded-lg p-1.5 ${FUEL_ACCENTS[r.fuel_type] === "success" ? "bg-success/15 text-success" : FUEL_ACCENTS[r.fuel_type] === "cyan" ? "bg-cyan/15 text-cyan-soft" : FUEL_ACCENTS[r.fuel_type] === "danger" ? "bg-danger/15 text-danger" : "bg-amber/15 text-amber"}`}>
              <Fuel size={14} />
            </div>
          </div>
          <p className="mt-3 font-display text-2xl font-semibold text-ink">{r.total_fuel_l} <span className="text-sm font-normal text-ink-dim">L</span></p>
          <p className="mt-1 text-xs text-ink-faint">{r.trip_count} {t("adminReports.tripsSuffix")} · ₹{r.total_cost.toLocaleString()}</p>
        </GlassCard>
      ))}
    </div>
  );
}

function AnomaliesTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/admin/anomalies").then((r) => setRows(r.data)); }, []);
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-faint">{t("adminReports.anomalyDesc")}</p>
      {rows === null && (
        <GlassCard className="flex items-center justify-center gap-2 p-8 text-sm text-ink-dim">
          <AlertTriangle size={15} className="animate-pulse" /> {t("adminReports.loadingAnomalies")}
        </GlassCard>
      )}
      {rows !== null && rows.length === 0 && <EmptyState icon={ShieldCheck} message={t("adminReports.noAnomalies")} />}
      {rows && rows.map((r, i) => (
        <GlassCard key={i} interactive className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-danger/15 p-2 text-danger"><AlertTriangle size={15} /></div>
            <div>
              <p className="text-sm text-ink">{r.trip_code} — {r.source} → {r.destination}</p>
              <p className="text-xs text-ink-faint">{r.vehicle_type} · {t("adminReports.fleetAvg")} {r.fleet_avg_co2_kg} kg</p>
            </div>
          </div>
          <Badge tone="danger">{r.co2_kg} kg · z={r.z_score}</Badge>
        </GlassCard>
      ))}
    </div>
  );
}

function MlPipelineTab() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState(null);
  const [retraining, setRetraining] = useState(false);

  async function load() { api.get("/admin/ml/runs").then((r) => setRuns(r.data)); }
  useEffect(() => { load(); }, []);

  async function retrain() {
    setRetraining(true);
    try { await api.post("/admin/ml/retrain"); } finally { setRetraining(false); load(); }
  }

  return (
    <div className="space-y-4">
      <GlassCard strong className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo/15 p-2.5 text-indigo-soft"><Cpu size={18} /></div>
          <div>
            <p className="text-sm font-medium text-ink">{t("adminReports.continuousLearningPipeline")}</p>
            <p className="text-xs text-ink-dim">{t("adminReports.pipelineDesc")}</p>
          </div>
        </div>
        <Button variant="primary" onClick={retrain} disabled={retraining}>
          <RefreshCw size={15} className={retraining ? "animate-spin" : ""} /> {retraining ? t("adminReports.retraining") : t("adminReports.retrainNow")}
        </Button>
      </GlassCard>

      <div className="space-y-2">
        {runs === null && <TableSkeleton cols={1} rows={3} />}
        {runs && runs.map((r) => (
          <GlassCard key={r.id} interactive className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={r.status === "success" ? "success" : r.status === "failed" ? "danger" : "warning"}>{r.status}</Badge>
                <span className="text-xs text-ink-faint">{r.triggered_by} · {new Date(r.started_at).toLocaleString()}</span>
              </div>
              <span className="font-mono text-xs text-ink-dim">{r.training_rows} {t("adminReports.rowsSuffix")}</span>
            </div>
            {r.metrics && (
              <div className="mt-3 flex flex-wrap gap-3 border-t border-white/5 pt-3 text-xs text-ink-dim">
                {Object.entries(r.metrics).map(([k, v]) => {
                  const isAccuracy = k.endsWith("_accuracy");
                  const label = k.replace(/_mae_?(kg|l)?$/i, "").replace(/_accuracy$/, "").replace(/_/g, " ");
                  const display = isAccuracy
                    ? `${(v * 100).toFixed(1)}% ${t("adminReports.accuracySuffix")}`
                    : `${t("adminReports.mae")} ${v}${k.includes("kg") ? " kg" : k.includes("_l") ? " L" : k === "cost_mae" ? " Rs." : ""}`;
                  return (
                    <span key={k} className="capitalize">
                      {label}: <span className={`font-mono ${isAccuracy && v < 0.9 ? "text-danger" : "text-ink"}`}>{display}</span>
                    </span>
                  );
                })}
              </div>
            )}
          </GlassCard>
        ))}
        {runs && runs.length === 0 && <EmptyState icon={Cpu} message={t("adminReports.noTrainingRuns")} />}
      </div>
    </div>
  );
}

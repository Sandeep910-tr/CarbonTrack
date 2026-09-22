import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Truck, Leaf, Route as RouteIcon, PlusCircle, Award, Download, TrendingDown, Trophy, Lock, Clock, ArrowRight, MapPin } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, StatCard, EcoScoreRing, Button, Badge } from "../../components/ui";
import api from "../../lib/api";

const STATUS_KEY = { Completed: "trip.completed", Ongoing: "trip.ongoing", Cancelled: "trip.cancelled" };

export default function DriverOverview() {
  const { t } = useTranslation();
  const [profile, setProfile] = useState(null);
  const [trips, setTrips] = useState([]);
  const [certStatus, setCertStatus] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api.get("/driver/profile").then((r) => setProfile(r.data));
    api.get("/driver/trips").then((r) => setTrips(r.data));
    api.get("/driver/certificate/status").then((r) => setCertStatus(r.data));
  }, []);

  if (!profile) return <p className="text-ink-dim">{t("driverOverview.loadingProfile")}</p>;

  const completed = trips.filter((t) => t.status === "Completed");
  const totalCo2 = completed.reduce((s, t) => s + (t.actual_co2_kg || 0), 0);
  const totalDistance = completed.reduce((s, t) => s + (t.distance_km || 0), 0);

  // Eco trend: CO2 per trip over the last 10 completed trips, oldest first.
  const trendData = [...completed]
    .sort((a, b) => new Date(a.ended_at || a.created_at) - new Date(b.ended_at || b.created_at))
    .slice(-10)
    .map((t, i) => ({
      name: t.trip_code || `Trip ${i + 1}`,
      co2: t.actual_co2_kg != null ? +t.actual_co2_kg.toFixed(1) : 0,
    }));

  // Last 5 completed trips flagged clean (no anomaly) — used for the "Clean Streak" badge.
  const recentCompleted = [...completed].sort((a, b) => new Date(b.ended_at || b.created_at) - new Date(a.ended_at || a.created_at));
  const cleanStreak = recentCompleted.length >= 5 && recentCompleted.slice(0, 5).every((t) => !t.is_anomaly);

  const badges = [
    { key: "first", icon: RouteIcon, unlocked: completed.length >= 1 },
    { key: "ten", icon: Trophy, unlocked: completed.length >= 10 },
    { key: "distance", icon: MapPin, unlocked: totalDistance >= 1000 },
    { key: "eco", icon: Leaf, unlocked: profile.eco_score >= 90 },
    { key: "clean", icon: TrendingDown, unlocked: cleanStreak },
    { key: "certified", icon: Award, unlocked: !!certStatus?.eligible },
  ];

  // Most recent activity across all statuses, not just completed.
  const recentActivity = [...trips]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5);

  async function downloadCertificate() {
    setDownloading(true);
    try {
      const res = await api.get("/driver/certificate/download", { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "eco_certificate.pdf";
      a.click();
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-6">
      <GlassCard strong className="trip-console-trim flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink">{t("driverOverview.welcomeBack", { name: profile.name.split(" ")[0] })}</h1>
          <p className="text-sm text-ink-dim">{profile.driver_code} · {profile.status}</p>
        </div>
        <Link to="/driver/new-trip"><Button variant="primary"><PlusCircle size={16} /> {t("driverOverview.startNewTrip")}</Button></Link>
      </GlassCard>

      <div className="grid gap-4 sm:grid-cols-3">
        <GlassCard interactive className="p-5">
          <div className="flex items-center gap-4">
            <div className="relative shrink-0">
              <EcoScoreRing score={profile.eco_score} size={72} strokeWidth={7} />
              <span className="absolute inset-0 flex items-center justify-center font-display text-lg font-semibold text-ink">
                {Math.round(profile.eco_score)}
              </span>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("driverOverview.ecoScore")}</p>
              <p className="mt-1 text-sm text-ink-dim">/100</p>
            </div>
          </div>
        </GlassCard>
        <StatCard label={t("driverOverview.tripsCompleted")} value={completed.length} icon={RouteIcon} />
        <StatCard label={t("driverOverview.co2SavedTracked")} value={totalCo2.toFixed(1)} unit="kg" icon={Leaf} accent="success" />
      </div>

      <GlassCard className="p-6">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-base font-semibold text-ink">{t("driverOverview.ecoTrend")}</h2>
          <div className="flex items-center gap-1.5 text-xs text-ink-dim"><TrendingDown size={14} className="text-success" /> {t("driverOverview.co2PerTrip")}</div>
        </div>
        {trendData.length > 0 ? (
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="co2Fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4ADE80" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#4ADE80" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
                <YAxis tick={{ fill: "#8891A8", fontSize: 11 }} axisLine={false} tickLine={false} unit=" kg" width={56} />
                <Tooltip
                  contentStyle={{ background: "#1A1712", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 12 }}
                  labelStyle={{ color: "#E7EAF3" }} itemStyle={{ color: "#4ADE80" }}
                  formatter={(v) => [`${v} kg`, "CO2"]}
                />
                <Area type="monotone" dataKey="co2" stroke="#4ADE80" strokeWidth={2} fill="url(#co2Fill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="mt-4 flex flex-col items-center gap-2 py-10 text-center">
            <TrendingDown size={22} className="text-ink-faint" />
            <p className="text-sm text-ink-dim">{t("driverOverview.noTrendYet")}</p>
          </div>
        )}
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-3">
        <GlassCard className="p-6 lg:col-span-2">
          <h2 className="font-display text-base font-semibold text-ink">{t("driverOverview.achievements")}</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {badges.map((b) => (
              <div
                key={b.key}
                className={`flex items-start gap-3 rounded-xl border p-3 ${b.unlocked ? "border-amber/30 bg-amber/[0.06]" : "border-white/10 bg-white/[0.02]"}`}
              >
                <div className={`rounded-lg p-2 ${b.unlocked ? "bg-amber/15 text-amber" : "bg-white/[0.04] text-ink-faint"}`}>
                  {b.unlocked ? <b.icon size={16} /> : <Lock size={16} />}
                </div>
                <div>
                  <p className={`text-sm font-medium ${b.unlocked ? "text-ink" : "text-ink-dim"}`}>{t(`driverOverview.badges.${b.key}.label`)}</p>
                  <p className="text-[11px] text-ink-faint">{t(`driverOverview.badges.${b.key}.desc`)}</p>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-base font-semibold text-ink">{t("driverOverview.recentActivity")}</h2>
            <Link to="/driver/history" className="flex items-center gap-1 text-xs text-ink-dim hover:text-amber">
              {t("driverOverview.viewAll")} <ArrowRight size={12} />
            </Link>
          </div>
          {recentActivity.length > 0 ? (
            <div className="mt-4 space-y-3">
              {recentActivity.map((t2) => (
                <div key={t2.id} className="flex items-start gap-3 border-b border-white/[0.06] pb-3 last:border-0 last:pb-0">
                  <div className="mt-0.5 rounded-lg bg-white/[0.04] p-1.5 text-ink-dim"><Clock size={13} /></div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-ink">{t2.source} → {t2.destination}</p>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
                      <span>{new Date(t2.created_at).toLocaleDateString()}</span>
                      <Badge tone={t2.status === "Completed" ? "success" : t2.status === "Ongoing" ? "indigo" : "neutral"}>
                        {STATUS_KEY[t2.status] ? t(STATUS_KEY[t2.status]) : t2.status}
                      </Badge>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 flex flex-col items-center gap-2 py-8 text-center">
              <RouteIcon size={20} className="text-ink-faint" />
              <p className="text-xs text-ink-dim">{t("driverOverview.noTripsStartFirst")}</p>
              <Link to="/driver/new-trip"><Button variant="ghost" className="mt-1">{t("driverOverview.startATrip")}</Button></Link>
            </div>
          )}
        </GlassCard>
      </div>

      {certStatus && (
        <GlassCard className={`p-6 ${certStatus.eligible ? "border-amber/30" : ""}`}>
          <div className="flex items-center gap-4">
            <div className={`rounded-xl p-3 ${certStatus.eligible ? "bg-amber/15 text-amber" : "bg-white/[0.04] text-ink-dim"}`}>
              <Award size={22} />
            </div>
            <div className="flex-1">
              <h2 className="font-display text-base font-semibold text-ink">{t("driverOverview.certTitle")}</h2>
              {certStatus.eligible ? (
                <p className="text-xs text-ink-dim">{t("driverOverview.certEligible", { score: certStatus.eco_score, threshold: certStatus.threshold })}</p>
              ) : (
                <p className="text-xs text-ink-dim">{t("driverOverview.certNotEligible", { threshold: certStatus.threshold, points: certStatus.points_to_go })}</p>
              )}
              {!certStatus.eligible && (
                <div className="mt-2 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-amber" style={{ width: `${Math.min((certStatus.eco_score / certStatus.threshold) * 100, 100)}%` }} />
                </div>
              )}
            </div>
            {certStatus.eligible && (
              <Button variant="primary" onClick={downloadCertificate} disabled={downloading}>
                <Download size={15} /> {downloading ? t("driverOverview.generating") : t("driverOverview.download")}
              </Button>
            )}
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-6">
        <h2 className="font-display text-base font-semibold text-ink">{t("driverOverview.assignedVehicle")}</h2>
        {profile.vehicle ? (
          <div className="mt-4 flex items-center gap-4">
            <div className="rounded-xl bg-white/[0.04] p-3 text-amber"><Truck size={22} /></div>
            <div className="flex-1">
              <p className="font-medium text-ink">{profile.vehicle.vehicle_no}</p>
              <p className="text-xs text-ink-dim">{profile.vehicle.vehicle_type} · {profile.vehicle.fuel_type} · {profile.vehicle.mileage} km/l</p>
            </div>
            <Badge tone={profile.vehicle.health_score > 75 ? "success" : "warning"}>{t("driverOverview.health")} {profile.vehicle.health_score}%</Badge>
          </div>
        ) : (
          <p className="mt-3 text-sm text-ink-dim">{t("driverOverview.noVehicleAssigned")}</p>
        )}
      </GlassCard>
    </div>
  );
}

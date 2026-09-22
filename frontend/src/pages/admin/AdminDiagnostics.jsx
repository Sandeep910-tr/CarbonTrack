import { useState } from "react";
import { CheckCircle2, XCircle, Loader2, Stethoscope, MapPin, Route as RouteIcon, MapPinned, CloudRain, Mail } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Badge } from "../../components/ui";
import api from "../../lib/api";

const CHECKS_PREVIEW = [
  { icon: MapPin, labelKey: "adminDiagnostics.mapsJsKey", descKey: "adminDiagnostics.rendersMap" },
  { icon: MapPinned, labelKey: "adminDiagnostics.geocodingApi", descKey: "adminDiagnostics.convertsAddresses" },
  { icon: RouteIcon, labelKey: "adminDiagnostics.routesApi", descKey: "adminDiagnostics.liveRouteOptions" },
  { icon: MapPin, labelKey: "adminDiagnostics.placesApi", descKey: "adminDiagnostics.nearbyLookup" },
  { icon: CloudRain, labelKey: "adminDiagnostics.openWeatherApi", descKey: "adminDiagnostics.liveWeatherPlanning" },
  { icon: Mail, labelKey: "adminDiagnostics.smtp", descKey: "adminDiagnostics.emailOtpOptional" },
];

export default function AdminDiagnostics() {
  const { t } = useTranslation();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/admin/diagnostics");
      setResults(res.data);
    } catch (err) {
      setError(err.response?.data?.error || t("adminDiagnostics.diagnosticsRequestFailed"));
    } finally {
      setLoading(false);
    }
  }

  const allOk = results && results.every((r) => r.status === "ok");
  const failCount = results ? results.filter((r) => r.status === "fail").length : 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <GlassCard strong className="p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Stethoscope size={20} className="text-amber" />
            <p className="text-xs text-ink-dim">{t("adminDiagnostics.apiDiagnosticsDesc")}</p>
          </div>
          <Button variant="primary" onClick={run} disabled={loading}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Stethoscope size={15} />}
            {loading ? t("adminDiagnostics.testing") : t("adminDiagnostics.runDiagnostics")}
          </Button>
        </div>

        {error && <p className="mt-4 text-xs text-danger">{error}</p>}

        {results ? (
          <div className="mt-5 space-y-2">
            <div className={`rounded-xl px-4 py-2.5 text-sm font-medium ${allOk ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}>
              {allOk ? t("adminDiagnostics.allChecksPassed") : t("adminDiagnostics.checksFailed", { failCount, total: results.length })}
            </div>
            {results.map((r) => (
              <div key={r.name} className="flex items-start gap-3 rounded-xl bg-white/[0.02] px-4 py-3">
                {r.status === "ok" ? (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
                ) : (
                  <XCircle size={16} className="mt-0.5 shrink-0 text-danger" />
                )}
                <div>
                  {/* r.name / r.detail are generated server-side; localizing them is a backend follow-up (see i18n docs). */}
                  <p className="text-sm text-ink">{r.name}</p>
                  <p className={`mt-0.5 text-xs ${r.status === "ok" ? "text-ink-dim" : "text-danger"}`}>{r.detail}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-5 space-y-2">
            {CHECKS_PREVIEW.map((c) => (
              <div key={c.labelKey} className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-4 py-3">
                <c.icon size={16} className="shrink-0 text-ink-faint" />
                <div>
                  <p className="text-sm text-ink">{t(c.labelKey)}</p>
                  <p className="text-xs text-ink-faint">{t(c.descKey)}</p>
                </div>
                <span className="ml-auto text-[10px] uppercase tracking-wide text-ink-faint">{t("adminDiagnostics.notRun")}</span>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <div className="space-y-4">
        <GlassCard className="p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminDiagnostics.whyThisExists")}</p>
          <p className="mt-2 text-sm leading-relaxed text-ink-dim">
            {t("adminDiagnostics.whyThisExistsDesc")}
          </p>
        </GlassCard>
        {results && (
          <GlassCard className="p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminDiagnostics.summary")}</p>
            <div className="mt-3 flex items-center gap-3">
              <Badge tone={allOk ? "success" : "danger"}>{results.length - failCount}/{results.length} {t("adminDiagnostics.passing")}</Badge>
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { ScrollText, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import api from "../../lib/api";

const ACTOR_TONE = { admin: "indigo", driver: "neutral", system: "warning" };

export default function AdminAuditLogs() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [actorType, setActorType] = useState("");

  useEffect(() => {
    setLoading(true);
    api.get("/admin/audit-logs", { params: { page, per_page: 25, ...(actorType ? { actor_type: actorType } : {}) } })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [page, actorType]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {["", "admin", "driver", "system"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => { setActorType(s); setPage(1); }}
            className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors ${actorType === s ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}
          >
            {s || t("adminAuditLogs.all", "All")}
          </button>
        ))}
      </div>

      {loading ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">…</GlassCard>
      ) : !data?.items?.length ? (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <ScrollText size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminAuditLogs.none", "No audit entries.")}</p>
        </GlassCard>
      ) : (
        <>
          <GlassCard className="overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-white/10 text-ink-faint">
                <tr>
                  <th className="p-3 font-medium">{t("adminAuditLogs.when", "When")}</th>
                  <th className="p-3 font-medium">{t("adminAuditLogs.actor", "Actor")}</th>
                  <th className="p-3 font-medium">{t("adminAuditLogs.action", "Action")}</th>
                  <th className="p-3 font-medium">{t("adminAuditLogs.resource", "Resource")}</th>
                  <th className="p-3 font-medium">{t("adminAuditLogs.details", "Details")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className="border-b border-white/5 text-ink-dim last:border-0">
                    <td className="whitespace-nowrap p-3 font-mono">{a.created_at ? new Date(a.created_at).toLocaleString() : ""}</td>
                    <td className="p-3">
                      <Badge tone={ACTOR_TONE[a.actor_type] || "neutral"}>{a.actor_name || a.actor_type}</Badge>
                    </td>
                    <td className="p-3 font-mono text-ink">{a.action}</td>
                    <td className="p-3">{a.resource_type}{a.resource_id ? ` #${a.resource_id}` : ""}</td>
                    <td className="max-w-xs truncate p-3" title={typeof a.details === "object" ? JSON.stringify(a.details) : a.details || ""}>
                      {typeof a.details === "object" ? JSON.stringify(a.details) : a.details || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>

          <div className="mt-3 flex items-center justify-between text-xs text-ink-dim">
            <span>{t("adminAuditLogs.pageOf", "Page {{page}} of {{total}}", { page: data.page, total: data.total_pages || 1 })}</span>
            <div className="flex gap-2">
              <button disabled={!data.has_prev} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-white/10 p-1.5 disabled:opacity-30">
                <ChevronLeft size={14} />
              </button>
              <button disabled={!data.has_next} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-white/10 p-1.5 disabled:opacity-30">
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

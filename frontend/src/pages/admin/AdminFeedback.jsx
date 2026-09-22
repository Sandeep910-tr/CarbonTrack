import { useEffect, useState } from "react";
import { Star, MessageSquareText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import api from "../../lib/api";

const EXPERIENCE_TONE = { Excellent: "success", Good: "success", Average: "neutral", Poor: "warning", "Very Poor": "danger" };

function Stars({ value }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star key={i} size={12} className={i < value ? "fill-amber text-amber" : "text-white/15"} />
      ))}
    </span>
  );
}

export default function AdminFeedback() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("All");

  useEffect(() => {
    api.get("/admin/feedback", { params: filter === "All" ? {} : { experience: filter } })
      .then((r) => setItems(r.data.items))
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {["All", "Excellent", "Good", "Average", "Poor", "Very Poor"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${filter === s ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">…</GlassCard>
      ) : items.length === 0 ? (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <MessageSquareText size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminFeedback.none", "No feedback yet.")}</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {items.map((f) => (
            <GlassCard key={f.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-ink">{f.trip_code} · {f.driver_name}</p>
                  <p className="text-xs text-ink-dim">{f.route}</p>
                </div>
                <Badge tone={EXPERIENCE_TONE[f.experience] || "neutral"}>{f.experience}</Badge>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
                <div>
                  <p className="text-ink-faint">{t("adminFeedback.overall", "Overall")}</p>
                  <Stars value={f.overall_rating} />
                </div>
                <div>
                  <p className="text-ink-faint">{t("adminFeedback.navigation", "Navigation")}</p>
                  <Stars value={f.navigation_rating} />
                </div>
                <div>
                  <p className="text-ink-faint">{t("adminFeedback.ecoRoute", "Eco Route")}</p>
                  <Stars value={f.eco_route_rating} />
                </div>
              </div>
              {f.comments && <p className="mt-3 border-t border-white/10 pt-2 text-xs text-ink-dim">"{f.comments}"</p>}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}

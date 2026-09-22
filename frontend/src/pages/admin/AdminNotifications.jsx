import { useEffect, useState } from "react";
import { BellOff, CloudRain, Truck, Wrench, Leaf, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import api from "../../lib/api";
import { useNotifications } from "../../context/NotificationContext";

const TYPE_ICON = { TRIP: Truck, WEATHER: CloudRain, VEHICLE: Wrench, CARBON: Leaf, SYSTEM: Settings2 };
const PRIORITY_TONE = { INFO: "neutral", ACTION: "indigo", WARNING: "warning", CRITICAL: "danger" };

export default function AdminNotifications() {
  const { t } = useTranslation();
  const [notes, setNotes] = useState([]);
  const [filter, setFilter] = useState("All");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const { markRead, markAllRead, unread } = useNotifications();

  useEffect(() => { api.get("/admin/notifications").then((r) => setNotes(r.data)); }, []);

  // Filter by the canonical notif_type taxonomy (TRIP/WEATHER/VEHICLE/CARBON/SYSTEM)
  // rather than the finer-grained free-form category, so the filter chips stay
  // small and predictable regardless of how many category strings exist.
  const types = ["All", ...new Set(notes.map((n) => n.notif_type).filter(Boolean))];
  const priorities = ["All", "INFO", "ACTION", "WARNING", "CRITICAL"];
  const filtered = notes.filter((n) => {
    const typeMatch = filter === "All" || n.notif_type === filter;
    const priorityMatch = priorityFilter === "All" || n.priority === priorityFilter;
    return typeMatch && priorityMatch;
  });

  async function handleMarkRead(id) {
    await markRead(id);
    setNotes((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  }

  async function handleMarkAll() {
    await markAllRead();
    setNotes((prev) => prev.map((n) => ({ ...n, is_read: true })));
  }

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {notes.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {types.map((c) => (
                <button key={c} onClick={() => setFilter(c)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors ${filter === c ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}>
                  {c === "All" ? t("adminNotifications.all") : c.toLowerCase()}
                </button>
              ))}
            </div>
          )}
          {notes.length > 0 && unread > 0 && (
            <button onClick={handleMarkAll} className="text-xs font-medium text-amber hover:text-amber-soft">
              {t("adminNotifications.markAllRead", "Mark all as read")}
            </button>
          )}
        </div>
        {notes.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-ink-faint mr-1 uppercase tracking-wider">{t("adminNotifications.filterPriority", "Priority:")}</span>
            {priorities.map((p) => (
              <button key={p} onClick={() => setPriorityFilter(p)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${priorityFilter === p ? "bg-white/15 text-ink shadow-sm" : "bg-white/[0.02] text-ink-dim hover:text-ink"}`}>
                {p === "All" ? t("adminNotifications.all") : p}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-3">
        {notes.length === 0 && (
          <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
            <BellOff size={28} className="text-ink-faint" />
            <p className="text-sm text-ink-dim">{t("adminNotifications.noNotificationsYet")}</p>
            <p className="max-w-sm text-xs text-ink-faint">
              {t("adminNotifications.notificationsDescription")}
            </p>
          </GlassCard>
        )}
        {filtered.map((n) => {
          const Icon = TYPE_ICON[n.notif_type] || Settings2;
          return (
            <GlassCard key={n.id} className={`flex items-start gap-3 p-4 ${!n.is_read ? "border-amber/30" : ""}`}>
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-ink-dim">
                <Icon size={16} />
              </span>
              <div className="min-w-0 flex-1">
                {/* n.message / n.category are generated server-side; localizing them is a backend follow-up (see i18n docs). */}
                {n.title && <p className={`text-sm ${!n.is_read ? "font-semibold text-ink" : "font-medium text-ink-dim"}`}>{n.title}</p>}
                <p className="text-sm text-ink-dim">{n.message}</p>
                <p className="mt-0.5 text-xs text-ink-faint">{new Date(n.created_at).toLocaleString()}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <Badge tone={PRIORITY_TONE[n.priority] || "neutral"}>{n.priority || n.category}</Badge>
                {!n.is_read && (
                  <button onClick={() => handleMarkRead(n.id)} className="text-[11px] text-ink-faint hover:text-ink">
                    {t("adminNotifications.markRead", "Mark read")}
                  </button>
                )}
              </div>
            </GlassCard>
          );
        })}
      </div>
    </div>
  );
}

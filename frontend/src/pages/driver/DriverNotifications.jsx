import { useEffect, useState } from "react";
import { BellOff, CloudRain, Truck, Wrench, Leaf, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import api from "../../lib/api";
import { useNotifications } from "../../context/NotificationContext";

const TYPE_ICON = { TRIP: Truck, WEATHER: CloudRain, VEHICLE: Wrench, CARBON: Leaf, SYSTEM: Settings2 };
const PRIORITY_TONE = { INFO: "neutral", ACTION: "indigo", WARNING: "warning", CRITICAL: "danger" };

export default function DriverNotifications() {
  const { t } = useTranslation();
  const [notes, setNotes] = useState([]);
  const { markRead, markAllRead, unread } = useNotifications();

  useEffect(() => { api.get("/driver/notifications").then((r) => setNotes(r.data)); }, []);

  async function handleMarkRead(id) {
    await markRead(id);
    setNotes((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  }

  async function handleMarkAll() {
    await markAllRead();
    setNotes((prev) => prev.map((n) => ({ ...n, is_read: true })));
  }

  return (
    <div className="space-y-3">
      {notes.length > 0 && unread > 0 && (
        <div className="flex justify-end">
          <button onClick={handleMarkAll} className="text-xs font-medium text-amber hover:text-amber-soft">
            {t("driverNotifications.markAllRead", "Mark all as read")}
          </button>
        </div>
      )}
      {notes.length === 0 && (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <BellOff size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("driver.noNotifications")}</p>
          <p className="max-w-sm text-xs text-ink-faint">
            {t("driverNotifications.description")}
          </p>
        </GlassCard>
      )}
      {notes.map((n) => {
        const Icon = TYPE_ICON[n.notif_type] || Settings2;
        return (
          <GlassCard
            key={n.id}
            className={`flex items-start gap-3 p-4 ${!n.is_read ? "border-amber/30" : ""}`}
            interactive
          >
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-ink-dim">
              <Icon size={16} />
            </span>
            <div className="min-w-0 flex-1">
              {n.title && <p className={`text-sm ${!n.is_read ? "font-semibold text-ink" : "font-medium text-ink-dim"}`}>{n.title}</p>}
              <p className="text-sm text-ink-dim">{n.message}</p>
              <p className="mt-0.5 text-xs text-ink-faint">{new Date(n.created_at).toLocaleString()}</p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <Badge tone={PRIORITY_TONE[n.priority] || "neutral"}>{n.priority || n.category}</Badge>
              {!n.is_read && (
                <button onClick={() => handleMarkRead(n.id)} className="text-[11px] text-ink-faint hover:text-ink">
                  {t("driverNotifications.markRead", "Mark read")}
                </button>
              )}
            </div>
          </GlassCard>
        );
      })}
    </div>
  );
}

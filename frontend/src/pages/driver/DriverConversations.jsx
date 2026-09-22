import { useEffect, useState } from "react";
import { MessageCircle, MessagesSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import ChatPanel from "../../components/ChatPanel";
import api from "../../lib/api";

export default function DriverConversations() {
  const { t } = useTranslation();
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openConv, setOpenConv] = useState(null);

  function refresh() {
    api.get("/driver/conversations").then((r) => setConversations(r.data)).finally(() => setLoading(false));
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setOpenConv({ id: null })}
          className="rounded-xl bg-white/[0.05] border border-white/10 px-3 py-1.5 text-xs font-medium text-ink hover:bg-white/[0.09]"
        >
          {t("chat.title")}
        </button>
      </div>

      {loading ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">…</GlassCard>
      ) : conversations.length === 0 ? (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <MessagesSquare size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("chat.empty")}</p>
        </GlassCard>
      ) : (
        <div className="space-y-2">
          {conversations.map((c) => (
            <div key={c.id} onClick={() => setOpenConv(c)} role="button" tabIndex={0}>
              <GlassCard interactive className="flex cursor-pointer items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <MessageCircle size={16} className="text-amber" />
                  <div>
                    <p className="text-sm text-ink">{c.trip_code ? `${t("newTrip.tripLabel")} ${c.trip_code}` : t("chat.title")}</p>
                    <p className="text-xs text-ink-dim">{c.last_message || "—"}</p>
                  </div>
                </div>
                {c.unread_count > 0 && <Badge tone="warning">{c.unread_count}</Badge>}
              </GlassCard>
            </div>
          ))}
        </div>
      )}

      <ChatPanel
        open={!!openConv}
        onClose={() => { setOpenConv(null); refresh(); }}
        role="driver"
        conversationId={openConv?.id || undefined}
        tripId={openConv?.trip_id}
      />
    </div>
  );
}

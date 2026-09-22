import { useEffect, useState, useMemo } from "react";
import { Search, MessageSquare, User, ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge } from "../../components/ui";
import { ChatInterface } from "../../components/ChatPanel";
import api from "../../lib/api";

export default function AdminConversations() {
  const { t } = useTranslation();
  const [drivers, setDrivers] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [chatLoading, setChatLoading] = useState(false);

  async function loadData() {
    try {
      const [dRes, cRes] = await Promise.all([
        api.get("/admin/drivers"),
        api.get("/admin/conversations"),
      ]);
      setDrivers(dRes.data);
      setConversations(cRes.data);
    } catch (err) {
      console.error("Failed to load conversations data", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadData(); }, []);

  const filteredDrivers = useMemo(() => {
    return drivers.filter(d =>
      d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.driver_code.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [drivers, searchQuery]);

  async function handleSelectDriver(driver) {
    console.log("Driver clicked", driver);
    setChatLoading(true);
    try {
      // Check if a conversation already exists for this driver
      const existing = conversations.find(c => c.driver_id === driver.id);
      if (existing) {
        setSelectedDriver({ ...driver, conversationId: existing.id });
      } else {
        // Create a new conversation
        const res = await api.post("/admin/conversations", { driver_id: driver.id });
        setSelectedDriver({ ...driver, conversationId: res.data.id });
      }
    } catch (err) {
      console.error("Failed to open conversation", err);
    } finally {
      setChatLoading(false);
    }
  }

  if (loading) {
    return (
      <GlassCard className="flex h-64 items-center justify-center p-8 text-sm text-ink-dim">
        {t("common.loading")}
      </GlassCard>
    );
  }

  return (
    <div className="flex h-[calc(100vh-12rem)] gap-4">
      {/* Driver List Pane */}
      <div className={`flex flex-col gap-3 transition-all duration-300 ${selectedDriver ? "hidden md:flex" : "flex w-full md:w-80"}`}>
        <div className="shrink-0">
          <GlassCard className="p-4">
            <div className="flex items-center gap-2 mb-4">
              <MessageSquare size={20} className="text-amber" />
              <h2 className="font-display text-lg font-semibold text-ink">{t("adminConversations.title", "Conversations")}</h2>
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-dim" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("common.search", "Search drivers...")}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] pl-9 pr-4 py-2 text-sm text-ink outline-none focus:border-amber/50"
              />
            </div>
          </GlassCard>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1 relative">
          {filteredDrivers.length === 0 ? (
            <p className="text-center py-10 text-xs text-ink-dim">{t("common.noResults", "No drivers found")}</p>
          ) : (
            filteredDrivers.map(d => {
              const conv = conversations.find(c => c.driver_id === d.id);
              const unread = conv?.unread_count || 0;
              return (
                <button
                  key={d.id}
                  onClick={() => handleSelectDriver(d)}
                  className="w-full text-left focus:outline-none group"
                >
                  <GlassCard
                    interactive
                    className={`flex items-center justify-between p-3 transition-colors ${selectedDriver?.id === d.id ? "bg-indigo/20 border-indigo/40" : ""}`}
                  >
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-ink-dim">
                        <User size={16} />
                      </div>
                      <div className="truncate">
                        <p className="text-sm font-medium text-ink truncate">{d.name}</p>
                        <p className="text-[10px] text-ink-dim truncate">{d.driver_code}</p>
                      </div>
                    </div>
                    {unread > 0 && <Badge tone="warning">{unread}</Badge>}
                  </GlassCard>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Chat Pane */}
      <div className={`flex-1 transition-all duration-300 ${!selectedDriver ? "hidden md:flex" : "flex"}`}>
        {selectedDriver ? (
          <div className="flex flex-1 flex-col w-full h-full">
            {/* Mobile Back Button */}
            <button
              onClick={() => setSelectedDriver(null)}
              className="md:hidden flex items-center gap-2 mb-3 text-xs text-ink-dim hover:text-ink"
            >
              <ArrowLeft size={14} /> {t("common.back", "Back to drivers")}
            </button>

            {chatLoading ? (
              <GlassCard className="flex-1 flex items-center justify-center p-8 text-sm text-ink-dim">
                {t("common.loading")}
              </GlassCard>
            ) : (
              <ChatInterface
                role="admin"
                conversationId={selectedDriver.conversationId}
                title={`${selectedDriver.name} (${selectedDriver.driver_code})`}
                onClose={() => setSelectedDriver(null)}
              />
            )}
          </div>
        ) : (
          <GlassCard className="flex flex-1 flex-col items-center justify-center p-10 text-center">
            <div className="mb-4 rounded-full bg-white/5 p-6 text-ink-faint">
              <MessageSquare size={48} />
            </div>
            <h3 className="font-display text-xl font-semibold text-ink mb-2">
              {t("adminConversations.selectDriver", "Select a Driver")}
            </h3>
            <p className="max-w-xs text-sm text-ink-dim">
              {t("adminConversations.selectDriverDesc", "Choose a driver from the list to start or continue a conversation.")}
            </p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}

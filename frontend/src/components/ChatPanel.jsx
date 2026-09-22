import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, Send, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button } from "./ui";
import api from "../lib/api";

/** Core chat logic extracted to be reusable in both modal and inline modes. */
export function ChatInterface({ role = "driver", tripId, conversationId: fixedConversationId, title, onClose }) {
  const { t } = useTranslation();
  const base = role === "admin" ? "/admin" : "/driver";
  const [conversationId, setConversationId] = useState(fixedConversationId || null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);
  const pollRef = useRef(null);
  const convIdRef = useRef(fixedConversationId || null);

  useEffect(() => {
    convIdRef.current = fixedConversationId || convIdRef.current;
    let cancelled = false;

    async function init() {
      setLoading(true);
      setError("");
      try {
        let id = fixedConversationId;
        if (!id && role === "driver") {
          const res = await api.post("/driver/conversations", tripId ? { trip_id: tripId } : {});
          id = res.data.id;
        }
        if (cancelled || !id) return;
        setConversationId(id);
        convIdRef.current = id;
        await loadMessages(id);
        await api.post(`${base}/conversations/${id}/read`).catch(() => {});
      } catch {
        if (!cancelled) setError(t("chat.loadFailed"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    async function loadMessages(id) {
      const res = await api.get(`${base}/conversations/${id}/messages`);
      if (!cancelled) setMessages(res.data);
    }

    init();
    pollRef.current = setInterval(() => {
      const id = convIdRef.current;
      if (id) loadMessages(id).catch(() => {});
    }, 6000);
    return () => { cancelled = true; clearInterval(pollRef.current); };
  }, [fixedConversationId, tripId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || !conversationId || sending) return;
    setSending(true);
    setInput("");
    try {
      const res = await api.post(`${base}/conversations/${conversationId}/messages`, { message: text });
      setMessages((m) => [...m, res.data]);
    } catch {
      setError(t("chat.loadFailed"));
    } finally {
      setSending(false);
    }
  }

  return (
    <GlassCard strong className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/10 p-4">
        <div className="flex items-center gap-2">
          <MessageCircle size={16} className="text-amber" />
          <h3 className="font-display text-sm font-semibold text-ink">{title || t("chat.title")}</h3>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label={t("common.cancel", "Cancel")} className="text-ink-dim hover:text-ink">
            <X size={18} />
          </button>
        )}
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        {loading ? (
          <p className="text-center text-xs text-ink-dim">…</p>
        ) : error ? (
          <p className="text-center text-xs text-danger">{error}</p>
        ) : messages.length === 0 ? (
          <p className="text-center text-xs text-ink-dim">
            {role === "admin"
              ? t("chat.adminEmpty", "Start a conversation with the driver")
              : t("chat.empty")}
          </p>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`flex ${m.sender_role === role ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                  m.sender_role === role
                    ? "bg-amber text-[#12100a]"
                    : "border border-white/10 bg-white/[0.05] text-ink"
                }`}
              >
                {m.message}
              </div>
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>

      <div className="flex items-center gap-2 border-t border-white/10 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={t("chat.placeholder")}
          className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-amber/50"
          disabled={loading || !conversationId}
        />
        <Button variant="primary" onClick={send} disabled={sending || !input.trim() || !conversationId}>
          <Send size={15} />
        </Button>
      </div>
    </GlassCard>
  );
}

/** Section 22-26: a driver<->admin chat thread, optionally scoped to a
 * trip. `role` picks the API base ("driver" or "admin") — the backend
 * endpoints and their authorization rules differ per role, but the shape
 * of the conversation/messages is identical either side. */
export default function ChatPanel({ open, onClose, role = "driver", tripId, conversationId, title }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={onClose}
          role="presentation"
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.97 }}
            onClick={(e) => e.stopPropagation()}
            className="flex h-[70vh] w-full max-w-md flex-col"
            role="dialog"
            aria-modal="true"
          >
            <ChatInterface
              role={role}
              tripId={tripId}
              conversationId={conversationId}
              title={title}
              onClose={onClose}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

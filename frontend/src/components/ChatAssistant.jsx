import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, Send, X, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";

export default function ChatAssistant() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "bot", text: t("ai.welcomeMessage") },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  const SUGGESTIONS = t("ai.suggestions", { returnObjects: true });

  // Reset the greeting if the user switches language before sending anything.
  useEffect(() => {
    setMessages((m) => (m.length === 1 && m[0].role === "bot" ? [{ role: "bot", text: t("ai.welcomeMessage") }] : m));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.language]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);

  async function send(text) {
    const msg = text ?? input;
    if (!msg.trim()) return;
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setInput("");
    setLoading(true);
    try {
      // `lang` is passed so the backend can localize its reply once that
      // support is added there (see i18n docs — AI reply localization is a
      // backend follow-up, not yet implemented server-side).
      const res = await api.post("/admin/ai-chat", { message: msg, lang: i18n.language });
      setMessages((m) => [...m, { role: "bot", text: res.data.reply }]);
    } catch {
      setMessages((m) => [...m, { role: "bot", text: t("ai.unreachable") }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <motion.button
        onClick={() => setOpen((o) => !o)}
        whileTap={{ scale: 0.94 }}
        aria-label={t("ai.assistant")}
        className="fixed bottom-6 right-6 z-[var(--z-ai-assistant)] flex h-14 w-14 items-center justify-center rounded-full bg-amber text-[#12100a] shadow-[0_8px_24px_-6px_rgba(240,180,41,0.6)]"
      >
        {open ? <X size={22} /> : <Bot size={22} />}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="panel-solid fixed bottom-24 right-6 z-[var(--z-ai-assistant)] flex h-[26rem] w-80 flex-col rounded-2xl"
            role="dialog"
            aria-modal="true"
            aria-label={t("ai.assistant")}
          >
            <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
              <Sparkles size={16} className="text-amber" />
              <span className="text-sm font-semibold text-ink">{t("ai.assistant")}</span>
              <span className="ml-auto rounded-full bg-white/[0.08] px-2 py-0.5 text-[10px] text-ink-faint">{t("ai.ruleBased")}</span>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3" role="log" aria-live="polite" aria-relevant="additions">
              {messages.map((m, i) => (
                <div key={i} className={`max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed ${
                  m.role === "user" ? "ml-auto bg-amber/20 text-ink" : "bg-white/[0.09] text-ink"
                }`}>
                  {m.text}
                </div>
              ))}
              {loading && <div className="max-w-[60%] rounded-xl bg-white/[0.09] px-3 py-2 text-xs text-ink-faint">{t("ai.thinking")}</div>}
              <div ref={endRef} />
            </div>

            {messages.length < 3 && (
              <div className="flex flex-wrap gap-1.5 px-4 pb-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-white/15 px-2.5 py-1 text-[10px] text-ink-dim hover:border-amber/40 hover:text-amber">
                    {s}
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-center gap-2 border-t border-white/10 p-3">
              <label htmlFor="ai-assistant-input" className="sr-only">{t("ai.askSomething")}</label>
              <input
                id="ai-assistant-input"
                value={input} onChange={(e) => setInput(e.target.value)}
                placeholder={t("ai.askSomething")}
                className="flex-1 rounded-lg border border-white/15 bg-white/[0.07] px-3 py-2 text-xs text-ink placeholder:text-ink-faint outline-none focus:border-amber/50"
              />
              <button type="submit" aria-label={t("ai.send", "Send")} className="rounded-lg bg-amber p-2 text-[#12100a]"><Send size={14} /></button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

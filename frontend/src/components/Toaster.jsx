import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, Info, Zap } from "lucide-react";
import { useNotifications } from "../context/NotificationContext";

const ICONS = {
  INFO: CheckCircle2,
  ACTION: Zap,
  WARNING: AlertTriangle,
  CRITICAL: AlertTriangle,
};

const TONE_CLASSES = {
  INFO: "border-white/10",
  ACTION: "border-amber/40",
  WARNING: "border-danger/50",
  CRITICAL: "border-danger/50",
};

export default function Toaster() {
  const { toasts, dismissToast } = useNotifications();

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[var(--z-toast)] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2 md:right-6 md:top-6">
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = ICONS[t.priority] || Info;
          return (
            <motion.div
              key={t._toastId}
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40 }}
              className={`glass-strong pointer-events-auto flex items-start gap-3 rounded-2xl border p-3.5 shadow-lg ${TONE_CLASSES[t.priority] || TONE_CLASSES.INFO}`}
            >
              <Icon size={18} className={t.priority === "WARNING" ? "mt-0.5 shrink-0 text-danger" : "mt-0.5 shrink-0 text-amber"} />
              <div className="min-w-0 flex-1">
                {t.title && <p className="truncate text-sm font-semibold text-ink">{t.title}</p>}
                <p className="mt-0.5 text-xs leading-snug text-ink-dim">{t.message}</p>
              </div>
              <button
                onClick={() => dismissToast(t._toastId)}
                aria-label="Dismiss"
                className="shrink-0 text-ink-faint hover:text-ink"
              >
                ×
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

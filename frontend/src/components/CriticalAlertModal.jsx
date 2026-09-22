import { AnimatePresence, motion } from "framer-motion";
import { AlertOctagon } from "lucide-react";
import { useNotifications } from "../context/NotificationContext";

export default function CriticalAlertModal() {
  const { criticalQueue, acknowledgeCritical } = useNotifications();
  const current = criticalQueue[0];

  return (
    <AnimatePresence>
      {current && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[var(--z-critical-alert)] flex items-center justify-center bg-black/70 p-4"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong w-full max-w-sm rounded-3xl border border-danger/40 p-7 text-center shadow-2xl"
          >
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/15 text-danger">
              <AlertOctagon size={28} />
            </div>
            {current.title && <h2 className="font-display text-lg font-semibold text-ink">{current.title}</h2>}
            <p className="mt-2 text-sm leading-relaxed text-ink-dim">{current.message}</p>
            <button
              onClick={() => acknowledgeCritical(current.id)}
              className="mt-6 w-full rounded-xl bg-danger px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-danger/90"
            >
              OK, GOT IT
            </button>
            {criticalQueue.length > 1 && (
              <p className="mt-3 text-[11px] text-ink-faint">{criticalQueue.length - 1} more alert(s) pending</p>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

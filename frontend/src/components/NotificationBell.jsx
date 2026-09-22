import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, CloudRain, Truck, Wrench, Leaf, Settings2, BellOff } from "lucide-react";
import { useNotifications } from "../context/NotificationContext";

const TYPE_ICON = {
  TRIP: Truck,
  WEATHER: CloudRain,
  VEHICLE: Wrench,
  CARBON: Leaf,
  SYSTEM: Settings2,
};

const PRIORITY_DOT = {
  INFO: "bg-ink-faint",
  ACTION: "bg-amber",
  WARNING: "bg-danger/80",
  CRITICAL: "bg-danger",
};

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? "s" : ""} ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// Panel width/viewport-margin used both for rendering and for the
// position math below — kept as constants so they can't drift apart.
const PANEL_WIDTH = 352; // 22rem
const VIEWPORT_MARGIN = 16; // matches max-w-[calc(100vw-2rem)] on mobile

export default function NotificationBell() {
  const { notifications, unread, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState(null); // { top, left, width } in viewport px
  const wrapRef = useRef(null); // wraps just the bell button
  const panelRef = useRef(null); // the portaled panel

  const recalcPosition = useCallback(() => {
    const btn = wrapRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const width = Math.min(PANEL_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);
    // Anchor to the bell's right edge, clamped so the panel never runs
    // past the viewport edge on narrow screens.
    let left = rect.right - width;
    left = Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - width - VIEWPORT_MARGIN));
    const top = rect.bottom + 8;
    setCoords({ top, left, width });
  }, []);

  // Recompute position whenever the panel opens, and keep it pinned to
  // the bell on scroll/resize anywhere in the app (portal content is no
  // longer inside any scrollable ancestor, so it needs its own tracking).
  useLayoutEffect(() => {
    if (!open) return;
    recalcPosition();
    let raf = null;
    const onMove = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        recalcPosition();
      });
    };
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true); // capture: any scrollable ancestor
    return () => {
      window.removeEventListener("resize", onMove);
      window.removeEventListener("scroll", onMove, true);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [open, recalcPosition]);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e) {
      if (
        wrapRef.current && !wrapRef.current.contains(e.target) &&
        panelRef.current && !panelRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="relative" ref={wrapRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        aria-expanded={open}
        aria-haspopup="true"
        className="relative flex h-9 w-9 items-center justify-center rounded-xl text-ink-dim transition hover:bg-white/[0.06] hover:text-ink"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {typeof document !== "undefined" && createPortal(
        <AnimatePresence>
          {open && coords && (
            <motion.div
              ref={panelRef}
              role="dialog"
              aria-label="Notifications"
              initial={{ opacity: 0, y: -8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.97 }}
              style={{
                position: "fixed",
                top: coords.top,
                left: coords.left,
                width: coords.width,
                zIndex: "var(--z-notification)",
              }}
              className="glass-strong max-h-[26rem] overflow-hidden rounded-2xl border border-white/10 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
                <p className="text-sm font-semibold text-ink">Notifications</p>
                {unread > 0 && (
                  <button onClick={markAllRead} className="text-xs font-medium text-amber hover:text-amber-soft">
                    Mark all as read
                  </button>
                )}
              </div>
              <div className="max-h-[21rem] overflow-y-auto">
                {notifications.length === 0 && (
                  <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                    <BellOff size={22} className="text-ink-faint" />
                    <p className="text-xs text-ink-faint">Nothing here yet.</p>
                  </div>
                )}
                {notifications.map((n) => {
                  const Icon = TYPE_ICON[n.notif_type] || Settings2;
                  return (
                    <button
                      key={n.id}
                      onClick={() => !n.is_read && markRead(n.id)}
                      className={`flex w-full items-start gap-3 border-b border-white/5 px-4 py-3 text-left transition hover:bg-white/[0.04] ${!n.is_read ? "bg-amber/[0.04]" : ""}`}
                    >
                      <span className="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.06] text-ink-dim">
                        <Icon size={15} />
                        {!n.is_read && (
                          <span className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ${PRIORITY_DOT[n.priority] || PRIORITY_DOT.INFO}`} />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        {n.title && <span className={`block truncate text-sm ${!n.is_read ? "font-semibold text-ink" : "font-medium text-ink-dim"}`}>{n.title}</span>}
                        <span className="block truncate text-xs text-ink-dim">{n.message}</span>
                        <span className="mt-0.5 block text-[11px] text-ink-faint">{timeAgo(n.created_at)}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </div>
  );
}

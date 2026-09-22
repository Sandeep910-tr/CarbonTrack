import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import api from "../lib/api";
import { useAuth } from "./AuthContext";

const NotificationContext = createContext(null);

const POLL_MS = 15000;

// Only these two combinations are voiced (section 25: "only for
// safety-critical driving events") - never voice every normal notification.
function shouldVoice(n) {
  if (n.category === "route_deviation" && (n.priority === "WARNING" || n.priority === "CRITICAL")) return true;
  if (n.notif_type === "WEATHER" && (n.priority === "WARNING" || n.priority === "CRITICAL")) return true;
  if (n.category === "destination_approaching") return true;
  return false;
}

function speak(text) {
  try {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel(); // don't stack utterances
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1;
    window.speechSynthesis.speak(utter);
  } catch {
    // speech synthesis unsupported/blocked - fail silently, toast/modal still shown
  }
}

export function NotificationProvider({ children }) {
  const { token, role } = useAuth();
  const base = role === "admin" ? "/admin" : "/driver";

  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [criticalQueue, setCriticalQueue] = useState([]);
  const seenIds = useRef(new Set());
  const firstLoad = useRef(true);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t._toastId !== id));
  }, []);

  const pushToast = useCallback((n) => {
    const durationMs = n.priority === "WARNING" ? 10000 : 4500; // section 23: warnings linger longer
    const toastId = `${n.id}-${Date.now()}`;
    setToasts((prev) => [...prev, { ...n, _toastId: toastId }]);
    setTimeout(() => dismissToast(toastId), durationMs);
  }, [dismissToast]);

  const acknowledgeCritical = useCallback((id) => {
    setCriticalQueue((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const fetchAll = useCallback(async () => {
    if (!token || !role) return;
    try {
      const [listRes, countRes] = await Promise.all([
        api.get(`${base}/notifications`),
        api.get(`${base}/notifications/unread-count`),
      ]);
      const list = listRes.data || [];
      setNotifications(list);
      setUnread(countRes.data?.unread ?? 0);

      if (firstLoad.current) {
        // Don't replay history as toasts/voice/critical-modals on first load
        // after login/refresh - only genuinely NEW events during this session.
        list.forEach((n) => seenIds.current.add(n.id));
        firstLoad.current = false;
        return;
      }

      const fresh = list.filter((n) => !seenIds.current.has(n.id));
      fresh.forEach((n) => seenIds.current.add(n.id));
      // Oldest-first so toasts/voice queue in chronological order
      fresh.reverse().forEach((n) => {
        if (n.priority === "CRITICAL") {
          setCriticalQueue((prev) => [...prev, n]);
        } else {
          pushToast(n);
        }
        if (shouldVoice(n)) speak(n.message);
      });
    } catch {
      // notification polling is best-effort; a transient failure shouldn't surface as an error to the user
    }
  }, [token, role, base, pushToast]);

  useEffect(() => {
    if (!token) return;
    firstLoad.current = true;
    seenIds.current = new Set();
    fetchAll();
    const id = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, role]);

  const markRead = useCallback(async (id) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    setUnread((prev) => Math.max(0, prev - 1));
    try {
      await api.post(`${base}/notifications/${id}/read`);
    } catch {
      // best-effort; local state already optimistically updated
    }
  }, [base]);

  const markAllRead = useCallback(async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnread(0);
    try {
      await api.post(`${base}/notifications/read-all`);
    } catch {
      // best-effort
    }
  }, [base]);

  return (
    <NotificationContext.Provider
      value={{ notifications, unread, toasts, criticalQueue, dismissToast, acknowledgeCritical, markRead, markAllRead, refetch: fetchAll }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotifications must be used within a NotificationProvider");
  return ctx;
}

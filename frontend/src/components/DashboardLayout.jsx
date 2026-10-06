import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { Leaf, LogOut, Menu, X, WifiOff, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import useOnlineStatus from "../hooks/useOnlineStatus";
import ChatAssistant from "./ChatAssistant";
import LanguageSelector from "./LanguageSelector";
import NotificationBell from "./NotificationBell";
import Toaster from "./Toaster";
import CriticalAlertModal from "./CriticalAlertModal";
import IsoTruckBadge from "./IsoTruckBadge";
import api from "../lib/api";

// Desktop sidebar width when expanded (md:w-64, 16rem) vs collapsed
// icon-only rail (md:w-[4.5rem], 72px). The sidebar's width classes and the
// main content's margin-left classes below must always match these two
// values so the content never overlaps or leaves a gap.

export default function DashboardLayout({ nav, children, title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false); // mobile drawer open/closed
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sidebarCollapsed") === "1";
    } catch {
      return false;
    }
  }); // desktop expanded/collapsed
  const [unreadCount, setUnreadCount] = useState(0);
  const isOnline = useOnlineStatus();
  const { t } = useTranslation();

  // Close mobile drawer on route change
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Close mobile drawer on Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  // Close mobile drawer when resizing up to desktop
  useEffect(() => {
    function handleResize() {
      if (window.innerWidth >= 768 && open) {
        setOpen(false);
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [open]);

  // Prevent background scroll on mobile when drawer is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    async function fetchUnread() {
      if (!user) return;
      try {
        const endpoint = user.role === "admin"
          ? "/admin/conversations/unread-count"
          : "/driver/conversations/unread-count";
        const res = await api.get(endpoint);
        setUnreadCount(res.data.unread);
      } catch (err) {
        console.error("Failed to fetch unread count", err);
      }
    }
    fetchUnread();
    const interval = setInterval(fetchUnread, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [user]);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("sidebarCollapsed", next ? "1" : "0");
      } catch {
        // ignore storage errors (private browsing, etc.)
      }
      return next;
    });
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="relative min-h-screen w-full max-w-full overflow-x-hidden md:flex">
      {!isOnline && (
        <div className="fixed inset-x-0 top-0 z-[var(--z-header)] flex items-center justify-center gap-2 bg-amber py-1.5 text-xs font-medium text-black">
          <WifiOff size={13} /> {t("offline.message")}
        </div>
      )}
      {/* Mobile top bar */}
      <div className={`glass-strong trip-console-trim fixed inset-x-0 z-[var(--z-header)] flex w-full max-w-full box-border items-center justify-between px-3.5 py-2.5 sm:px-4 sm:py-3 md:hidden ${isOnline ? "top-0" : "top-7"}`}>
        <span className="flex items-center gap-2 font-display text-sm font-semibold text-ink shrink-0">
          <span className="glow-chip-cyan flex h-7 w-7 items-center justify-center rounded-lg text-success shrink-0"><Leaf size={14} /></span>
          <span>Carbon<span className="text-amber">Track</span></span>
        </span>
        <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
          <NotificationBell />
          <LanguageSelector variant="topbar" />
          <button
            onClick={() => setOpen(!open)}
            aria-label={open ? t("common.closeMenu", "Close menu") : t("common.openMenu", "Open menu")}
            aria-expanded={open}
            className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-dim hover:bg-white/[0.06] hover:text-ink transition-colors"
          >{open ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
      </div>

      {/* Mobile drawer backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-300 md:hidden ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      {/* Sidebar & Mobile Drawer */}
      <aside
        className={`fixed left-0 top-0 bottom-0 z-50 flex h-screen h-[100dvh] w-[280px] max-w-[85vw] shrink-0 flex-col
          sidebar-drawer-surface bg-[#0a0d16] md:bg-transparent md:trip-console-trim md:z-[var(--z-sidebar)]
          transition-transform duration-300 ease-out
          ${open ? "translate-x-0 pointer-events-auto" : "-translate-x-full pointer-events-none md:translate-x-0 md:pointer-events-auto"}
          ${collapsed ? "md:w-[4.5rem]" : "md:w-64"}
          ${isOnline ? "pt-0 md:pt-0" : "pt-7 md:pt-7"}`}
      >
        {/* Mobile drawer header */}
        <div className="flex items-center justify-between border-b border-white/5 px-4 py-3.5 md:hidden">
          <div className="flex items-center gap-2">
            <span className="glow-chip-cyan flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-success">
              <Leaf size={14} />
            </span>
            <span className="font-display text-base font-semibold text-ink">
              Carbon<span className="text-amber">Track</span>
            </span>
          </div>
          <button
            onClick={() => setOpen(false)}
            aria-label={t("common.closeMenu", "Close menu")}
            className="rounded-lg p-1.5 text-ink-dim hover:bg-white/[0.06] hover:text-ink transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Desktop sidebar brand header */}
        <div className={`hidden items-center gap-2 px-6 py-6 md:flex ${collapsed ? "md:justify-center md:px-0" : "md:justify-between"}`}>
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="glow-chip-cyan flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-success"><Leaf size={16} /></span>
            <span className={`font-display text-lg font-semibold whitespace-nowrap text-ink transition-all duration-200 ${collapsed ? "md:w-0 md:opacity-0" : "md:w-auto md:opacity-100"}`}>
              Carbon<span className="text-amber">Track</span>
            </span>
          </div>
          {!collapsed && (
            <button
              onClick={toggleCollapsed}
              aria-label={t("common.collapseSidebar", "Collapse sidebar")}
              className="hidden shrink-0 rounded-lg p-1.5 text-ink-dim hover:bg-white/[0.06] hover:text-ink md:flex"
            >
              <PanelLeftClose size={17} />
            </button>
          )}
        </div>
        {collapsed && (
          <button
            onClick={toggleCollapsed}
            aria-label={t("common.expandSidebar", "Expand sidebar")}
            className="mx-auto mb-2 hidden rounded-lg p-1.5 text-ink-dim hover:bg-white/[0.06] hover:text-ink md:flex"
          >
            <PanelLeftOpen size={17} />
          </button>
        )}

        <nav className="sidebar-scroll mt-2 flex min-h-0 flex-1 flex-col gap-1 overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth px-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setOpen(false)}
              title={collapsed ? t(item.labelKey) : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors
                ${collapsed ? "md:justify-center md:px-2" : ""}
                ${isActive ? "bg-indigo/15 text-cyan-soft shadow-[inset_0_0_0_1px_rgba(34,211,238,0.25)]" : "text-ink-dim hover:bg-white/[0.04] hover:text-ink"}`
              }
            >
              <div className="relative">
                <item.icon size={17} className="shrink-0" />
                { (item.to === "/admin/conversations" || item.to === "/driver/conversations") && unreadCount > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-3 w-3 items-center justify-center rounded-full bg-amber text-[8px] font-bold text-black shadow-sm">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </div>
              <span className={collapsed ? "md:hidden" : ""}>{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="w-full border-t border-white/5 p-4">
          <div className={`mb-3 rounded-xl bg-white/[0.03] px-3 py-2.5 ${collapsed ? "md:hidden" : ""}`}>
            <p className="truncate text-sm font-medium text-ink">{user?.name}</p>
            <p className="text-xs text-ink-dim">{user?.username}</p>
          </div>
          <div className={`mb-1 ${collapsed ? "md:hidden" : ""}`}>
            <LanguageSelector variant="sidebar" />
          </div>
          <button
            onClick={handleLogout}
            title={collapsed ? t("nav.logout") : undefined}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink-dim hover:bg-danger/10 hover:text-danger ${collapsed ? "md:justify-center md:px-2" : ""}`}
          >
            <LogOut size={16} className="shrink-0" /> <span className={collapsed ? "md:hidden" : ""}>{t("nav.logout")}</span>
          </button>
        </div>
      </aside>

      {/* Content */}
      <main
        className={`w-full max-w-full box-border px-4 pb-20 sm:px-6 sm:pb-16 md:px-8
          transition-[margin] duration-300 ease-out
          ${isOnline ? "pt-16 sm:pt-20 md:pt-8" : "pt-24 sm:pt-28 md:pt-14"}
          ml-0 ${collapsed ? "md:ml-[4.5rem]" : "md:ml-64"}
          md:flex-1 md:min-w-0 md:w-auto`}
      >
        {title ? (
          <div className="trip-console-trim glass mb-6 flex items-center justify-between gap-3 rounded-2xl px-4 py-3 sm:px-5 sm:py-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="glow-chip-cyan flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
                <IsoTruckBadge size={20} />
              </span>
              <h1 className="truncate font-display text-lg font-semibold text-ink sm:text-xl md:text-2xl">{title}</h1>
            </div>
            <span className="hidden md:inline"><NotificationBell /></span>
          </div>
        ) : (
          <div className="mb-6 hidden items-center justify-end md:flex"><NotificationBell /></div>
        )}
        {children}
      </main>

      <Toaster />
      <CriticalAlertModal />
      <ChatAssistant />
    </div>
  );
}
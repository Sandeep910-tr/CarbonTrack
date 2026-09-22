import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Check, ChevronDown } from "lucide-react";
import { SUPPORTED_LANGUAGES, setLanguage } from "../i18n";

/**
 * Language switcher. Renders as a compact pill that expands into a
 * dropdown, matching the sidebar/navbar styling used elsewhere in the app.
 *
 * The dropdown panel uses `.panel-solid` (opaque), not `.glass-strong`
 * (translucent + blurred) — this dropdown always opens directly over other
 * text (sidebar nav links, or the mobile drawer's nav list), and a
 * translucent background let that text show through and visually collide
 * with the language list on top of it. `.panel-solid` exists in
 * index.css specifically for floating UI that must stay readable over
 * busy content behind it.
 *
 * `variant="sidebar"` -> full-width row (used in the desktop sidebar footer)
 * `variant="topbar"`  -> compact icon+code pill (used in the mobile top bar)
 */
export default function LanguageSelector({ variant = "sidebar" }) {
  const { i18n, t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const current =
    SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language) ||
    SUPPORTED_LANGUAGES[0];

  useEffect(() => {
    function onClickAway(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  function choose(code) {
    setLanguage(code);
    setOpen(false);
  }

  const isTopbar = variant === "topbar";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("language.select")}
        className={
          isTopbar
            ? "flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-ink-dim hover:bg-white/[0.06] hover:text-ink"
            : "flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink-dim hover:bg-white/[0.04] hover:text-ink"
        }
      >
        <Globe size={isTopbar ? 15 : 16} />
        <span className={isTopbar ? "" : "flex-1 text-left"}>{current.nativeName}</span>
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="listbox"
          className={`panel-solid absolute z-[var(--z-dropdown)] max-h-72 w-48 overflow-y-auto rounded-xl p-1.5
            ${isTopbar ? "right-0 top-full mt-2" : "bottom-full left-0 mb-2"}`}
        >
          <p className="px-2.5 pb-1.5 pt-1 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
            {t("language.label")}
          </p>
          {SUPPORTED_LANGUAGES.map((lang) => {
            const active = lang.code === current.code;
            return (
              <button
                key={lang.code}
                role="option"
                aria-selected={active}
                onClick={() => choose(lang.code)}
                className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm transition-colors
                  ${active ? "bg-amber/10 text-amber" : "text-ink-dim hover:bg-white/[0.05] hover:text-ink"}`}
              >
                <span>{lang.nativeName}</span>
                {active && <Check size={14} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

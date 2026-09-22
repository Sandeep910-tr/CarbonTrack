import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

export function GlassCard({ children, className = "", strong = false, interactive = false }) {
  return (
    <div className={`${strong ? "glass-strong" : "glass"} ${interactive ? "glass-interactive" : ""} card-enter rounded-2xl ${className}`}>
      {children}
    </div>
  );
}

export function Button({ children, variant = "primary", className = "", ...props }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all duration-200 focus-ring disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.97] hover:scale-[1.015]";
  const variants = {
    primary: "bg-amber text-[#12100a] hover:brightness-110 shadow-[0_0_0_1px_rgba(240,180,41,0.4),0_8px_24px_-8px_rgba(240,180,41,0.5)]",
    ghost: "bg-white/[0.05] border border-white/10 text-ink backdrop-blur-md hover:bg-white/[0.09] hover:border-white/20",
    danger: "bg-danger/15 border border-danger/40 text-danger backdrop-blur-md hover:bg-danger/25",
    indigo: "bg-indigo/15 border border-indigo/40 text-indigo-soft backdrop-blur-md hover:bg-indigo/25",
    subtle: "text-ink-dim hover:text-ink",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Input({ label, className = "", type = "text", ...props }) {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const inputType = isPassword ? (showPassword ? "text" : "password") : type;

  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-dim">{label}</span>}
      <div className={isPassword ? "relative" : undefined}>
        <input
          type={inputType}
          className={`w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-amber/50 focus:bg-white/[0.05] ${isPassword ? "pr-11" : ""} ${className}`}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="focus-ring absolute right-3 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink-faint transition-colors hover:text-ink"
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        )}
      </div>
    </label>
  );
}

export function Select({ label, children, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-dim">{label}</span>}
      <select
        className={`w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-ink outline-none transition-colors focus:border-amber/50 focus:bg-white/[0.05] ${className}`}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

export function Badge({ children, tone = "neutral" }) {
  const tones = {
    neutral: "bg-white/[0.06] text-ink-dim border-white/10",
    success: "bg-success/10 text-success border-success/30",
    warning: "bg-amber/10 text-amber-soft border-amber/30",
    danger: "bg-danger/10 text-danger border-danger/30",
    indigo: "bg-indigo/10 text-indigo-soft border-indigo/30",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function TextArea({ label, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-dim">{label}</span>}
      <textarea
        className={`w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-amber/50 focus:bg-white/[0.05] ${className}`}
        {...props}
      />
    </label>
  );
}

// Post-Trip Feedback: a reusable 1-5 star rating control. Fully
// keyboard-accessible (arrow keys move the selection, Enter/Space commit
// it — native for a `role="radiogroup"` of `role="radio"` buttons) and
// screen-reader friendly (each star has its own "N star(s)" label, and the
// group itself is labeled via `label`). No external dependency — just SVG
// stars via lucide-react, which the project already uses everywhere else.
export function StarRating({ label, value = 0, onChange, required = false, error = false, size = 28, disabled = false }) {
  const stars = [1, 2, 3, 4, 5];

  function handleKeyDown(e, star) {
    if (disabled) return;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      onChange(Math.min(5, (value || 0) + 1));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      onChange(Math.max(1, (value || 0) - 1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onChange(star);
    }
  }

  return (
    <div>
      {label && (
        <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-dim">
          {label}{required && <span className="text-danger"> *</span>}
        </span>
      )}
      <div
        role="radiogroup"
        aria-label={label}
        aria-required={required}
        aria-invalid={error}
        className="flex items-center gap-1.5"
      >
        {stars.map((star) => {
          const filled = star <= value;
          return (
            <button
              key={star}
              type="button"
              role="radio"
              aria-checked={value === star}
              aria-label={`${star} star${star === 1 ? "" : "s"}`}
              disabled={disabled}
              tabIndex={star === (value || 1) ? 0 : -1}
              onClick={() => onChange(star)}
              onKeyDown={(e) => handleKeyDown(e, star)}
              className={`focus-ring rounded-md p-0.5 transition-transform hover:scale-110 disabled:cursor-not-allowed disabled:opacity-50 ${filled ? "text-amber" : "text-white/15"}`}
            >
              <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5">
                <path d="M12 2.5l2.9 6.02 6.6.87-4.85 4.6 1.24 6.6L12 17.6l-5.9 3-1.24-6.6-4.85-4.6 6.6-.87L12 2.5z" strokeLinejoin="round" />
              </svg>
            </button>
          );
        })}
        {error && <span className="ml-1 text-[11px] text-danger">Required</span>}
      </div>
    </div>
  );
}

// Signature element (per the CarbonTrack visual-identity pass): the ONLY
// place in the app that uses the amber->copper gradient. Everywhere else
// amber stays flat, so this ring reads as the one moment of extra polish
// instead of the gradient becoming wallpaper. Score is 0-100.
export function EcoScoreRing({ score, size = 96, strokeWidth = 8 }) {
  const clamped = Math.max(0, Math.min(100, score ?? 0));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const gradientId = "ecoRingGradient";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#F5B944" />
          <stop offset="100%" stopColor="#C97C3D" />
        </linearGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={strokeWidth} />
      <circle
        cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke={`url(#${gradientId})`} strokeWidth={strokeWidth} strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
    </svg>
  );
}

export function StatCard({ label, value, unit, icon: Icon, accent = "cyan" }) {
  const accentMap = {
    amber: "text-amber bg-amber/15",
    indigo: "text-indigo-soft bg-indigo/15",
    success: "text-success bg-success/15",
    danger: "text-danger bg-danger/15",
    cyan: "text-cyan-soft bg-cyan/15",
  };
  const accentClass = accentMap[accent] || accentMap.cyan;
  return (
    <GlassCard interactive className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{label}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-ink">
            {value}
            {unit && <span className="ml-1 text-base font-normal text-ink-dim">{unit}</span>}
          </p>
        </div>
        {Icon && (
          <div className={`rounded-lg p-2 ${accentClass}`}>
            <Icon size={18} />
          </div>
        )}
      </div>
    </GlassCard>
  );
}
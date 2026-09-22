import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Leaf, LogIn, AlertCircle, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import LanguageSelector from "../components/LanguageSelector";

export default function Login() {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(username, password);
      navigate(data.role === "admin" ? "/admin" : "/driver");
    } catch (err) {
      setError(err.response?.data?.error || t("auth.loginFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-6">
      <div className="absolute right-4 top-4 w-40">
        <LanguageSelector variant="topbar" />
      </div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="w-full max-w-sm">
        <Link to="/" className="mb-8 flex items-center justify-center gap-2 font-display text-lg font-semibold text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber/15 text-amber"><Leaf size={16} /></span>
          Carbon<span className="text-amber">Track</span>
        </Link>

        <GlassCard strong className="p-8">
          <h1 className="font-display text-xl font-semibold text-ink">{t("auth.signInTitle")}</h1>
          <p className="mt-1 text-sm text-ink-dim">{t("auth.signInSubtitle")}</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <Input label={t("auth.username")} placeholder="admin1 or driver1" value={username}
                   onChange={(e) => setUsername(e.target.value)} autoFocus required />
            <div className="block">
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-dim">
                {t("auth.password")}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 pr-11 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-amber/50 focus:bg-white/[0.05]"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((previous) => !previous)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="focus-ring absolute right-3 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink-faint transition-colors hover:text-ink"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                <AlertCircle size={14} className="mt-0.5 shrink-0" /> {error}
              </div>
            )}

            <Button type="submit" variant="primary" className="w-full" disabled={loading}>
              <LogIn size={16} /> {loading ? t("auth.signingIn") : t("auth.signIn")}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-ink-dim">
            {t("auth.newDriver")}{" "}
            <Link to="/register" className="font-medium text-amber hover:underline">{t("auth.registerHere")}</Link>
          </p>
        </GlassCard>

        <p className="mt-4 text-center text-[11px] text-ink-faint">
          {t("auth.demoAccounts")}
        </p>
      </motion.div>
    </div>
  );
}

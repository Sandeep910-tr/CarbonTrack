import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Leaf, Gauge, ShieldCheck, MapPinned, BrainCircuit, ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import RouteVisual from "../components/RouteVisual";
import { GlassCard, Button } from "../components/ui";
import LanguageSelector from "../components/LanguageSelector";

const FEATURE_ICONS = [BrainCircuit, MapPinned, Gauge, ShieldCheck];
const FEATURE_ACCENTS = ["indigo", "amber", "success", "danger"];

export default function Landing() {
  const { t } = useTranslation();
  const features = t("landing.features", { returnObjects: true });
  const how = t("landing.how", { returnObjects: true });

  return (
    <div className="min-h-screen overflow-x-hidden">
      <Nav />

      {/* Hero */}
      <section className="relative mx-auto max-w-7xl px-6 pt-20 pb-16 lg:pt-28">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <span className="inline-flex items-center gap-2 rounded-full border border-indigo/30 bg-indigo/10 px-3 py-1 font-mono text-[11px] tracking-wider text-indigo-soft">
              RT&#8209;0001 <span className="text-ink-faint">/</span> {t("landing.badge")}
            </span>
            <h1 className="mt-5 font-display text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl">
              {t("landing.headline1")}<br />
              {t("landing.headline2")} <span className="text-gradient-amber">{t("landing.headline2Accent")}</span>
            </h1>
            <p className="mt-5 max-w-md text-base leading-relaxed text-ink-dim">
              {t("landing.subhead")}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/register"><Button variant="primary">{t("landing.registerAsDriver")} <ArrowRight size={16} /></Button></Link>
              <Link to="/login"><Button variant="ghost">{t("landing.signIn")}</Button></Link>
            </div>
            <div className="mt-10 flex gap-8">
              <Stat value="9" label={t("landing.statModels")} />
              <Stat value="6" label={t("landing.statSources")} />
              <Stat value="24/7" label={t("landing.statMonitoring")} />
            </div>
          </motion.div>

          <motion.div className="float-slow" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, delay: 0.1 }}>
            <GlassCard strong className="p-6">
              <RouteVisual />
              <div className="mt-2 flex items-center justify-between border-t border-white/10 pt-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-dim">{t("landing.predictedCo2")}</p>
                  <p className="font-mono text-xl text-amber">34.5 kg</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-dim">{t("landing.fuel")}</p>
                  <p className="font-mono text-xl text-ink">18.6 L</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-dim">{t("landing.ecoScore")}</p>
                  <p className="font-mono text-xl text-indigo-soft">84</p>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        </div>
      </section>

      <div className="road-divider mx-6" />

      {/* Features */}
      <section id="features" className="mx-auto max-w-7xl px-6 py-16">
        <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">{t("landing.featuresTitle")}</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f, i) => {
            const Icon = FEATURE_ICONS[i];
            const accentClass = { indigo: "text-indigo-soft bg-indigo/15", amber: "text-amber bg-amber/15", success: "text-success bg-success/15", danger: "text-danger bg-danger/15" }[FEATURE_ACCENTS[i]];
            return (
              <motion.div key={f.title} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}>
                <GlassCard interactive className="h-full p-5">
                  <div className={`inline-flex rounded-lg p-2 ${accentClass}`}><Icon size={20} /></div>
                  <h3 className="mt-3 font-display text-base font-semibold text-ink">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-dim">{f.body}</p>
                </GlassCard>
              </motion.div>
            );
          })}
        </div>
      </section>

      <div className="road-divider mx-6" />

      {/* How it works */}
      <section id="how" className="mx-auto max-w-7xl px-6 py-16">
        <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">{t("landing.howTitle")}</h2>
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {how.map((h, i) => (
            <div key={h.step} className="relative">
              <span className="font-mono text-xs text-ink-faint">{t("landing.step")} {i + 1}</span>
              <h3 className="mt-1 font-display text-lg font-semibold text-ink">{h.step}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-dim">{h.body}</p>
              {i < how.length - 1 && <div className="absolute right-[-12px] top-2 hidden h-px w-6 bg-white/10 lg:block" />}
            </div>
          ))}
        </div>
      </section>

      <div className="road-divider mx-6" />

      {/* CTA */}
      <section className="mx-auto max-w-7xl px-6 pb-24">
        <GlassCard strong className="flex flex-col items-center gap-4 p-10 text-center sm:flex-row sm:justify-between sm:text-left">
          <div>
            <h3 className="font-display text-xl font-semibold text-ink">{t("landing.ctaTitle")}</h3>
            <p className="mt-1 text-sm text-ink-dim">{t("landing.ctaBody")}</p>
          </div>
          <Link to="/register"><Button variant="primary">{t("landing.getStarted")} <ArrowRight size={16} /></Button></Link>
        </GlassCard>
      </section>

      <footer className="border-t border-white/5 py-8 text-center text-xs text-ink-faint">
        {t("landing.footer")}
      </footer>
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div>
      <p className="font-display text-2xl font-semibold text-ink">{value}</p>
      <p className="text-xs text-ink-dim">{label}</p>
    </div>
  );
}

function Nav() {
  const { t } = useTranslation();
  return (
    <header className="glass-strong sticky top-0 z-[var(--z-header)]">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber/15 text-amber"><Leaf size={16} /></span>
          Carbon<span className="text-amber">Track</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-ink-dim md:flex">
          <a href="#features" className="hover:text-ink">{t("landing.navFeatures")}</a>
          <a href="#how" className="hover:text-ink">{t("landing.navHow")}</a>
        </nav>
        <div className="flex items-center gap-3">
          <LanguageSelector variant="topbar" />
          <Link to="/login"><Button variant="ghost">{t("landing.login")}</Button></Link>
          <Link to="/register"><Button variant="primary">{t("landing.register")}</Button></Link>
        </div>
      </div>
    </header>
  );
}

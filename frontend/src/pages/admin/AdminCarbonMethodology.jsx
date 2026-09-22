import { useEffect, useState } from "react";
import { Plus, CheckCircle2, Leaf, Calendar, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Badge } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import api from "../../lib/api";

// Matches ml/data_formulas.py's fuel types (backend/validators.py VALID_FUEL_TYPES).
const FUEL_TYPES = ["Diesel", "Petrol", "CNG", "Electric"];
const EMPTY_FACTORS = { Diesel: "", Petrol: "", CNG: "", Electric: "" };

export default function AdminCarbonMethodology() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isSuperAdmin = user?.admin_role === "SuperAdmin";

  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [versionLabel, setVersionLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [factors, setFactors] = useState(EMPTY_FACTORS);
  const [saving, setSaving] = useState(false);
  const [activatingId, setActivatingId] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get("/admin/carbon-methodologies");
      setVersions(res.data);
    } catch (err) {
      setError(err.response?.data?.error || t("adminCarbonMethodology.loadFailed"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function createVersion(e) {
    e.preventDefault();
    setError("");
    const emission_factors = {};
    for (const fuel of FUEL_TYPES) {
      const v = factors[fuel];
      if (v !== "" && v != null) emission_factors[fuel] = Number(v);
    }
    if (Object.keys(emission_factors).length === 0) {
      setError(t("adminCarbonMethodology.atLeastOneFactorRequired"));
      return;
    }
    setSaving(true);
    try {
      await api.post("/admin/carbon-methodologies", {
        version_label: versionLabel,
        emission_factors,
        notes,
      });
      setVersionLabel("");
      setNotes("");
      setFactors(EMPTY_FACTORS);
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.response?.data?.error || t("adminCarbonMethodology.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function activate(id) {
    if (!confirm(t("adminCarbonMethodology.activateConfirm"))) return;
    setActivatingId(id);
    setError("");
    try {
      await api.post(`/admin/carbon-methodologies/${id}/activate`);
      load();
    } catch (err) {
      setError(err.response?.data?.error || t("adminCarbonMethodology.activateFailed"));
    } finally {
      setActivatingId(null);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-ink-dim">{t("adminCarbonMethodology.description")}</p>
          <p className="mt-1 text-xs text-ink-faint">{t("adminCarbonMethodology.versioningNote")}</p>
        </div>
        {isSuperAdmin && (
          <Button variant="primary" onClick={() => setShowForm((s) => !s)}>
            <Plus size={15} /> {t("adminCarbonMethodology.newVersion")}
          </Button>
        )}
      </div>

      {!isSuperAdmin && (
        <div className="mb-6 flex items-center gap-2 rounded-xl border border-amber/30 bg-amber/10 px-4 py-3 text-xs text-amber">
          <ShieldAlert size={15} className="shrink-0" />
          {t("adminCarbonMethodology.viewOnlyForAdmins")}
        </div>
      )}

      {error && (
        <div role="alert" className="mb-6 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </div>
      )}

      {showForm && isSuperAdmin && (
        <GlassCard strong className="mb-6 p-5">
          <form onSubmit={createVersion} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Input label={t("adminCarbonMethodology.versionLabel")} placeholder="v1.1"
                     value={versionLabel} onChange={(e) => setVersionLabel(e.target.value)} required />
              <Input label={t("adminCarbonMethodology.notes")} placeholder={t("adminCarbonMethodology.notesPlaceholder")}
                     value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-ink-dim">{t("adminCarbonMethodology.emissionFactors")}</p>
              <div className="grid gap-3 sm:grid-cols-4">
                {FUEL_TYPES.map((fuel) => (
                  <Input key={fuel} label={fuel} type="number" step="0.01" min="0" max="10"
                         placeholder={t("adminCarbonMethodology.kgCo2PerLitre")}
                         value={factors[fuel]}
                         onChange={(e) => setFactors({ ...factors, [fuel]: e.target.value })} />
                ))}
              </div>
              <p className="mt-2 text-[11px] text-ink-faint">{t("adminCarbonMethodology.leaveBlankToOmit")}</p>
            </div>
            <div className="rounded-lg border border-indigo/30 bg-indigo/10 px-3 py-2 text-xs text-indigo-soft">
              {t("adminCarbonMethodology.createdInactiveNote")}
            </div>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? t("adminCarbonMethodology.saving") : t("adminCarbonMethodology.saveVersion")}
            </Button>
          </form>
        </GlassCard>
      )}

      {loading ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">{t("adminCarbonMethodology.loading")}</GlassCard>
      ) : versions.length === 0 ? (
        <GlassCard className="p-8 text-center">
          <Leaf className="mx-auto text-ink-faint" size={22} />
          <p className="mt-3 text-sm text-ink-dim">{t("adminCarbonMethodology.noVersionsYet")}</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {versions.map((v) => (
            <GlassCard key={v.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-display text-sm font-semibold text-ink">{v.version_label}</p>
                    {v.is_active && (
                      <Badge tone="success"><CheckCircle2 size={11} className="mr-1 inline" />{t("adminCarbonMethodology.active")}</Badge>
                    )}
                  </div>
                  <p className="mt-1 flex items-center gap-1 text-xs text-ink-faint">
                    <Calendar size={12} /> {t("adminCarbonMethodology.effectiveFrom")} {v.effective_date}
                  </p>
                  {v.notes && <p className="mt-2 text-xs text-ink-dim">{v.notes}</p>}
                </div>
                {isSuperAdmin && !v.is_active && (
                  <Button variant="ghost" onClick={() => activate(v.id)} disabled={activatingId === v.id}>
                    {activatingId === v.id ? t("adminCarbonMethodology.activating") : t("adminCarbonMethodology.makeActive")}
                  </Button>
                )}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 border-t border-white/10 pt-3 sm:grid-cols-4">
                {Object.entries(v.emission_factors || {}).map(([fuel, factor]) => (
                  <div key={fuel} className="text-xs">
                    <p className="text-ink-faint">{fuel}</p>
                    <p className="font-mono text-ink">{factor} {t("adminCarbonMethodology.kgCo2PerLitreUnit")}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}

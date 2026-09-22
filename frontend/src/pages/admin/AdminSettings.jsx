import { useEffect, useState, useRef } from "react";
import { Save, Download, Upload, Building2, Bell, Award } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Badge } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import api from "../../lib/api";

export default function AdminSettings() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState("");
  const fileRef = useRef(null);
  const isSuperAdmin = user?.admin_role === "SuperAdmin";

  useEffect(() => { api.get("/admin/settings").then((r) => setSettings(r.data)); }, []);

  function update(k, v) { setSettings((s) => ({ ...s, [k]: v })); setSaved(false); }

  async function save(e) {
    e.preventDefault();
    await api.put("/admin/settings", settings);
    setSaved(true);
  }

  async function downloadBackup() {
    const res = await api.get("/admin/backup", { responseType: "blob" });
    const blob = new Blob([res.data], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "carbontrack_backup.json";
    a.click();
  }

  async function restoreBackup(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!confirm(t("adminSettings.restoreConfirm"))) {
      fileRef.current.value = "";
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await api.post("/admin/restore", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setRestoreMsg(res.data.message);
    } catch (err) {
      setRestoreMsg(err.response?.data?.error || t("adminSettings.restoreFailed"));
    }
    fileRef.current.value = "";
  }

  if (!settings) return <p className="text-ink-dim">{t("adminSettings.loadingSettings")}</p>;

  const notifyFields = [
    ["notify_maintenance", t("adminSettings.maintenanceAlerts")],
    ["notify_weather", t("adminSettings.weatherAlerts")],
    ["notify_traffic", t("adminSettings.trafficAlerts")],
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        <GlassCard className="p-6">
          <h2 className="font-display text-base font-semibold text-ink">{t("adminSettings.systemSettings")}</h2>
          <form onSubmit={save} className="mt-5 space-y-4">
            <Input label={t("adminSettings.companyName")} value={settings.company_name}
                   onChange={(e) => update("company_name", e.target.value)} />
            <div className="grid grid-cols-2 gap-3">
              <Input label={t("adminSettings.carbonBudgetTarget")} type="number" value={settings.carbon_budget_target_kg}
                     onChange={(e) => update("carbon_budget_target_kg", e.target.value)} />
              <Input label={t("adminSettings.fuelBudgetTarget")} type="number" value={settings.fuel_budget_target}
                     onChange={(e) => update("fuel_budget_target", e.target.value)} />
            </div>
            <Input label={t("adminSettings.certThreshold")} type="number" value={settings.certificate_eco_threshold}
                   onChange={(e) => update("certificate_eco_threshold", e.target.value)} />

            <div className="space-y-2 pt-2">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminSettings.notificationPreferences")}</p>
              {notifyFields.map(([key, label]) => (
                <label key={key} className="flex items-center justify-between rounded-xl bg-white/[0.02] px-4 py-2.5">
                  <span className="text-sm text-ink-dim">{label}</span>
                  <input type="checkbox" checked={settings[key] === "true" || settings[key] === true}
                         onChange={(e) => update(key, e.target.checked ? "true" : "false")}
                         className="h-4 w-4 accent-amber" />
                </label>
              ))}
            </div>

            <div className="space-y-2 pt-2">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminSettings.evAssumptions")}</p>
              <p className="text-[11px] text-ink-faint">{t("adminSettings.evAssumptionsDesc")}</p>
              <div className="grid grid-cols-2 gap-3">
                <Input label={t("adminSettings.iceVehiclePrice")} type="number" value={settings.ice_vehicle_price_inr}
                       onChange={(e) => update("ice_vehicle_price_inr", e.target.value)} />
                <Input label={t("adminSettings.evVehiclePrice")} type="number" value={settings.ev_vehicle_price_inr}
                       onChange={(e) => update("ev_vehicle_price_inr", e.target.value)} />
                <Input label={t("adminSettings.fuelPriceRs")} type="number" step="0.1" value={settings.fuel_price_per_l}
                       onChange={(e) => update("fuel_price_per_l", e.target.value)} />
                <Input label={t("adminSettings.electricityPrice")} type="number" step="0.1" value={settings.electricity_price_per_kwh}
                       onChange={(e) => update("electricity_price_per_kwh", e.target.value)} />
                <Input label={t("adminSettings.evEfficiency")} type="number" step="0.01" value={settings.ev_efficiency_kwh_per_km}
                       onChange={(e) => update("ev_efficiency_kwh_per_km", e.target.value)} />
                <Input label={t("adminSettings.gridEmissionFactor")} type="number" step="0.01" value={settings.ev_grid_emission_factor_kg_per_kwh}
                       onChange={(e) => update("ev_grid_emission_factor_kg_per_kwh", e.target.value)} />
                <Input label={t("adminSettings.iceMaintenance")} type="number" step="0.1" value={settings.ice_maintenance_cost_per_km}
                       onChange={(e) => update("ice_maintenance_cost_per_km", e.target.value)} />
                <Input label={t("adminSettings.evMaintenance")} type="number" step="0.1" value={settings.ev_maintenance_cost_per_km}
                       onChange={(e) => update("ev_maintenance_cost_per_km", e.target.value)} />
              </div>
            </div>

            <Button type="submit" variant="primary" className="w-full"><Save size={15} /> {t("adminSettings.saveSettings")}</Button>
            {saved && <p className="text-center text-xs text-success">{t("adminSettings.settingsSaved")}</p>}
          </form>
        </GlassCard>

        {isSuperAdmin && (
          <GlassCard className="p-6">
            <h2 className="font-display text-base font-semibold text-ink">{t("adminSettings.backupRestore")}</h2>
            <p className="mt-1 text-xs text-ink-dim">
              {t("adminSettings.backupRestoreDesc")}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button variant="ghost" onClick={downloadBackup}><Download size={15} /> {t("adminSettings.downloadBackup")}</Button>
              <Button variant="ghost" onClick={() => fileRef.current.click()}><Upload size={15} /> {t("adminSettings.restoreFromFile")}</Button>
              <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={restoreBackup} />
            </div>
            {restoreMsg && <p className="mt-3 text-xs text-ink-dim">{restoreMsg}</p>}
          </GlassCard>
        )}
      </div>

      <div className="space-y-4">
        <GlassCard className="p-5">
          <div className="flex items-center gap-2">
            <Building2 size={16} className="text-amber" />
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminSettings.currentConfiguration")}</p>
          </div>
          <div className="mt-3 space-y-2.5 text-xs">
            <div className="flex justify-between"><span className="text-ink-dim">{t("adminSettings.company")}</span><span className="text-ink">{settings.company_name}</span></div>
            <div className="flex justify-between"><span className="text-ink-dim">{t("adminSettings.carbonBudget")}</span><span className="text-ink">{Number(settings.carbon_budget_target_kg).toLocaleString()} kg</span></div>
            <div className="flex justify-between"><span className="text-ink-dim">{t("adminSettings.fuelBudget")}</span><span className="text-ink">₹{Number(settings.fuel_budget_target).toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-ink-dim">{t("adminSettings.certificateThreshold")}</span><span className="text-ink">{settings.certificate_eco_threshold} {t("adminSettings.ptsSuffix")}</span></div>
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center gap-2">
            <Bell size={16} className="text-indigo-soft" />
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminSettings.activeAlertCategories")}</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone={settings.notify_maintenance === "true" ? "success" : "neutral"}>{t("adminSettings.maintenance")}</Badge>
            <Badge tone={settings.notify_weather === "true" ? "success" : "neutral"}>{t("adminSettings.weather")}</Badge>
            <Badge tone={settings.notify_traffic === "true" ? "success" : "neutral"}>{t("adminSettings.traffic")}</Badge>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
            {t("adminSettings.alertsAutoFireDesc")}
          </p>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center gap-2">
            <Award size={16} className="text-amber" />
            <p className="text-xs font-medium uppercase tracking-wide text-ink-dim">{t("adminSettings.yourRole")}</p>
          </div>
          <p className="mt-2 text-sm text-ink">{user?.name}</p>
          <Badge tone={isSuperAdmin ? "indigo" : "neutral"}>{user?.admin_role || "Admin"}</Badge>
          {!isSuperAdmin && (
            <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
              {t("adminSettings.adminAccountsRestricted")}
            </p>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

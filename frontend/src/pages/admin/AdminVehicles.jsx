import { useEffect, useState } from "react";
import { Plus, Trash2, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Select, Badge } from "../../components/ui";
import api from "../../lib/api";

const EMPTY = { vehicle_no: "", vehicle_type: "Van", fuel_type: "Diesel", mileage: "", capacity_kg: "", insurance_expiry: "", permit_expiry: "", pollution_cert_expiry: "", depot_id: "" };

const VEHICLE_TYPES = [
  { value: "Van", labelKey: "adminVehicles.typeVan" },
  { value: "Mini Truck", labelKey: "adminVehicles.typeMiniTruck" },
  { value: "Truck", labelKey: "adminVehicles.typeTruck" },
  { value: "Trailer", labelKey: "adminVehicles.typeTrailer" },
];
const FUEL_TYPES = [
  { value: "Diesel", labelKey: "adminVehicles.fuelDiesel" },
  { value: "Petrol", labelKey: "adminVehicles.fuelPetrol" },
  { value: "CNG", labelKey: "adminVehicles.fuelCng" },
  { value: "Electric", labelKey: "adminVehicles.fuelElectric" },
];

// Returns { labelKey, params, tone } describing how urgent a document's renewal is.
function expiryStatus(dateStr) {
  if (!dateStr) return { labelKey: "adminVehicles.notSet", params: {}, tone: "neutral" };
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days < 0) return { labelKey: "adminVehicles.expiredAgo", params: { days: Math.abs(days) }, tone: "danger" };
  if (days <= 30) return { labelKey: "adminVehicles.expiresIn", params: { days }, tone: "warning" };
  return { labelKey: "adminVehicles.validUntil", params: { date: dateStr }, tone: "success" };
}

export default function AdminVehicles() {
  const { t } = useTranslation();
  const [vehicles, setVehicles] = useState([]);
  const [depots, setDepots] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY);

  async function load() {
    const [v, d] = await Promise.all([api.get("/admin/vehicles"), api.get("/admin/depots")]);
    setVehicles(v.data);
    setDepots(d.data);
  }
  useEffect(() => { load(); }, []);

  async function addVehicle(e) {
    e.preventDefault();
    await api.post("/admin/vehicles", {
      ...form, mileage: parseFloat(form.mileage), capacity_kg: parseFloat(form.capacity_kg),
      insurance_expiry: form.insurance_expiry || null,
      permit_expiry: form.permit_expiry || null,
      pollution_cert_expiry: form.pollution_cert_expiry || null,
      depot_id: form.depot_id || null,
    });
    setForm(EMPTY);
    setShowForm(false);
    load();
  }

  async function remove(id) {
    if (!confirm(t("adminVehicles.removeVehicleConfirm"))) return;
    await api.delete(`/admin/vehicles/${id}`);
    load();
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-ink-dim">{vehicles.length} {t("adminVehicles.vehiclesInFleet")}</p>
        <Button variant="primary" onClick={() => setShowForm((s) => !s)}><Plus size={15} /> {t("adminVehicles.addVehicle")}</Button>
      </div>

      {showForm && (
        <GlassCard strong className="mb-6 p-5">
          <form onSubmit={addVehicle} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Input label={t("adminVehicles.vehicleNo")} value={form.vehicle_no} onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} required />
            <Select label={t("adminVehicles.type")} value={form.vehicle_type} onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })}>
              {VEHICLE_TYPES.map((vt) => <option key={vt.value} value={vt.value}>{t(vt.labelKey)}</option>)}
            </Select>
            <Select label={t("adminVehicles.fuelType")} value={form.fuel_type} onChange={(e) => setForm({ ...form, fuel_type: e.target.value })}>
              {FUEL_TYPES.map((ft) => <option key={ft.value} value={ft.value}>{t(ft.labelKey)}</option>)}
            </Select>
            <Input label={t("adminVehicles.mileage")} type="number" step="0.1" value={form.mileage} onChange={(e) => setForm({ ...form, mileage: e.target.value })} required />
            <Input label={t("adminVehicles.capacity")} type="number" value={form.capacity_kg} onChange={(e) => setForm({ ...form, capacity_kg: e.target.value })} required />
            <Input label={t("adminVehicles.insuranceExpiry")} type="date" value={form.insurance_expiry} onChange={(e) => setForm({ ...form, insurance_expiry: e.target.value })} />
            <Input label={t("adminVehicles.permitExpiry")} type="date" value={form.permit_expiry} onChange={(e) => setForm({ ...form, permit_expiry: e.target.value })} />
            <Input label={t("adminVehicles.pollutionCertExpiry")} type="date" value={form.pollution_cert_expiry} onChange={(e) => setForm({ ...form, pollution_cert_expiry: e.target.value })} />
            <Select label={t("adminVehicles.depot")} value={form.depot_id} onChange={(e) => setForm({ ...form, depot_id: e.target.value })}>
              <option value="">{t("adminVehicles.unassigned")}</option>
              {depots.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            <Button type="submit" variant="primary" className="sm:col-span-2 lg:col-span-5">{t("adminVehicles.saveVehicle")}</Button>
          </form>
        </GlassCard>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {vehicles.map((v) => (
          <GlassCard key={v.id} className="p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium text-ink">{v.vehicle_no}</p>
                <p className="text-xs text-ink-dim">{v.vehicle_type} · {v.fuel_type}</p>
              </div>
              <button onClick={() => remove(v.id)} className="text-ink-faint hover:text-danger"><Trash2 size={15} /></button>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-ink-dim">
              <span>{t("adminVehicles.mileageLabel", { value: v.mileage })}</span>
              <span>{t("adminVehicles.capacityLabel", { value: v.capacity_kg })}</span>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <Badge tone={v.health_score > 75 ? "success" : v.health_score > 50 ? "warning" : "danger"}>
                {t("adminVehicles.health")} {v.health_score}%
              </Badge>
              <Badge tone={v.status === "Active" ? "success" : "neutral"}>{v.status === "Active" ? t("adminVehicles.statusActive") : t("adminVehicles.statusInactive")}</Badge>
            </div>
            <div className="mt-3 border-t border-white/10 pt-3">
              <select
                value={v.depot_id || ""}
                onChange={async (e) => {
                  const depot_id = e.target.value || null;
                  await api.put(`/admin/vehicles/${v.id}`, { depot_id });
                  load();
                }}
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-ink-dim"
              >
                <option value="">{t("adminVehicles.noDepotAssigned")}</option>
                {depots.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div className="mt-3 space-y-1.5 border-t border-white/10 pt-3">
              {[
                [t("adminVehicles.insurance"), v.insurance_expiry],
                [t("adminVehicles.permit"), v.permit_expiry],
                [t("adminVehicles.pollutionCert"), v.pollution_cert_expiry],
              ].map(([label, date]) => {
                const s = expiryStatus(date);
                return (
                  <div key={label} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-ink-faint">
                      {s.tone !== "success" && s.tone !== "neutral" && <ShieldAlert size={12} className={s.tone === "danger" ? "text-danger" : "text-amber"} />}
                      {label}
                    </span>
                    <Badge tone={s.tone}>{t(s.labelKey, s.params)}</Badge>
                  </div>
                );
              })}
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}

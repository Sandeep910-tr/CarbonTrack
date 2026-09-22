import { useEffect, useState } from "react";
import { Plus, Trash2, MapPin, Truck, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input } from "../../components/ui";
import api from "../../lib/api";

const EMPTY = { name: "", city: "", address: "" };

export default function AdminDepots() {
  const { t } = useTranslation();
  const [depots, setDepots] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY);

  async function load() {
    const [d, v, dr] = await Promise.all([
      api.get("/admin/depots"),
      api.get("/admin/vehicles"),
      api.get("/admin/drivers"),
    ]);
    setDepots(d.data);
    setVehicles(v.data);
    setDrivers(dr.data);
  }
  useEffect(() => { load(); }, []);

  async function addDepot(e) {
    e.preventDefault();
    await api.post("/admin/depots", form);
    setForm(EMPTY);
    setShowForm(false);
    load();
  }

  async function remove(id) {
    if (!confirm(t("adminDepots.removeDepotConfirm"))) return;
    await api.delete(`/admin/depots/${id}`);
    load();
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-ink-dim">
          {depots.length} {t("adminDepots.depot", { count: depots.length })} · {vehicles.filter((v) => !v.depot_id).length} {t("adminDepots.vehiclesAndDriversUnassigned", { driversCount: drivers.filter((d) => !d.depot_id).length })}
        </p>
        <Button variant="primary" onClick={() => setShowForm((s) => !s)}><Plus size={15} /> {t("adminDepots.addDepot")}</Button>
      </div>

      {showForm && (
        <GlassCard strong className="mb-6 p-5">
          <form onSubmit={addDepot} className="grid gap-3 sm:grid-cols-3">
            <Input label={t("adminDepots.depotName")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <Input label={t("adminDepots.city")} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            <Input label={t("adminDepots.address")} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            <Button type="submit" variant="primary" className="sm:col-span-3">{t("adminDepots.saveDepot")}</Button>
          </form>
        </GlassCard>
      )}

      {depots.length === 0 ? (
        <GlassCard className="p-8 text-center">
          <MapPin className="mx-auto text-ink-faint" size={22} />
          <p className="mt-3 text-sm text-ink-dim">{t("adminDepots.noDepotsYet")}</p>
        </GlassCard>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {depots.map((d) => {
            const depotVehicles = vehicles.filter((v) => v.depot_id === d.id);
            const depotDrivers = drivers.filter((dr) => dr.depot_id === d.id);
            return (
              <GlassCard key={d.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-medium text-ink">{d.name}</p>
                    <p className="text-xs text-ink-dim">{d.depot_code}{d.city ? ` · ${d.city}` : ""}</p>
                  </div>
                  <button onClick={() => remove(d.id)} className="text-ink-faint hover:text-danger"><Trash2 size={15} /></button>
                </div>
                {d.address && <p className="mt-2 text-xs text-ink-faint">{d.address}</p>}
                <div className="mt-3 flex items-center gap-4 border-t border-white/10 pt-3 text-xs text-ink-dim">
                  <span className="flex items-center gap-1.5"><Truck size={13} /> {depotVehicles.length} {t("adminDepots.vehiclesCount")}</span>
                  <span className="flex items-center gap-1.5"><Users size={13} /> {depotDrivers.length} {t("adminDepots.driversCount")}</span>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}
    </div>
  );
}

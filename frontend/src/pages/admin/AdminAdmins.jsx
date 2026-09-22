import { useEffect, useState } from "react";
import { Plus, Trash2, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Select, Badge } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import api from "../../lib/api";

const EMPTY = { name: "", username: "", password: "", role: "Admin" };

export default function AdminAdmins() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [admins, setAdmins] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const isSuperAdmin = user?.admin_role === "SuperAdmin";

  async function load() {
    try {
      const res = await api.get("/admin/admins");
      setAdmins(res.data);
    } catch (err) {
      setError(err.response?.data?.error || t("adminAdmins.couldNotLoadAdminList"));
    }
  }
  useEffect(() => { load(); }, []);

  async function addAdmin(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/admin/admins", form);
      setForm(EMPTY);
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.response?.data?.error || t("adminAdmins.couldNotCreateAdmin"));
    }
  }

  async function toggleStatus(a) {
    await api.put(`/admin/admins/${a.id}`, { status: a.status === "Active" ? "Suspended" : "Active" });
    load();
  }

  async function remove(a) {
    if (!confirm(t("adminAdmins.removeAdminConfirm", { name: a.name }))) return;
    await api.delete(`/admin/admins/${a.id}`);
    load();
  }

  if (!isSuperAdmin) {
    return (
      <GlassCard className="flex items-center gap-3 p-6 text-sm text-ink-dim">
        <ShieldCheck size={18} className="text-amber" />
        {t("adminAdmins.restrictedToSuperAdmin")}
      </GlassCard>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-ink-dim">{admins.length} {t("adminAdmins.adminAccountsCount")}</p>
        <Button variant="primary" onClick={() => setShowForm((s) => !s)}><Plus size={15} /> {t("adminAdmins.addAdmin")}</Button>
      </div>

      {showForm && (
        <GlassCard strong className="mb-6 p-5">
          <form onSubmit={addAdmin} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Input label={t("adminAdmins.name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <Input label={t("adminAdmins.username")} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
            <Input label={t("adminAdmins.password")} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
            <Select label={t("adminAdmins.role")} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="Admin">{t("adminAdmins.roleAdmin")}</option>
              <option value="SuperAdmin">{t("adminAdmins.roleSuperAdmin")}</option>
            </Select>
            {error && <p className="sm:col-span-2 lg:col-span-4 text-xs text-danger">{error}</p>}
            <Button type="submit" variant="primary" className="sm:col-span-2 lg:col-span-4">{t("adminAdmins.createAdmin")}</Button>
          </form>
        </GlassCard>
      )}

      <div className="space-y-3">
        {admins.map((a) => (
          <GlassCard key={a.id} className="flex items-center justify-between p-4">
            <div>
              <div className="flex items-center gap-2">
                <p className="font-medium text-ink">{a.name}</p>
                <span className="text-xs text-ink-faint">{a.username}</span>
                <Badge tone={a.role === "SuperAdmin" ? "indigo" : "neutral"}>{a.role === "SuperAdmin" ? t("adminAdmins.roleSuperAdmin") : t("adminAdmins.roleAdmin")}</Badge>
                <Badge tone={a.status === "Active" ? "success" : "danger"}>{a.status === "Active" ? t("adminAdmins.statusActive") : t("adminAdmins.statusSuspended")}</Badge>
              </div>
            </div>
            <div className="flex gap-2">
              {a.role !== "SuperAdmin" && (
                <>
                  <Button variant="ghost" onClick={() => toggleStatus(a)}>
                    {a.status === "Active" ? t("adminAdmins.suspend") : t("adminAdmins.reactivate")}
                  </Button>
                  <button onClick={() => remove(a)} className="text-ink-faint hover:text-danger"><Trash2 size={16} /></button>
                </>
              )}
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}

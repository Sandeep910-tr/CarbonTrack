import { useEffect, useState } from "react";
import { UserCog, MapPin, CheckCircle2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge, Button, Select } from "../../components/ui";
import api from "../../lib/api";

const STATUS_TONE = { Pending: "warning", Approved: "success", Rejected: "danger" };

function ApproveRow({ req, onDone }) {
  const { t } = useTranslation();
  const [eligible, setEligible] = useState([]);
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/admin/reassignment-requests/${req.id}/eligible-drivers`).then((r) => {
      setEligible(r.data);
      if (r.data[0]) setChosen(String(r.data[0].id));
    });
  }, [req.id]);

  async function approve() {
    if (!chosen) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/admin/reassignment-requests/${req.id}/approve`, { replacement_driver_id: Number(chosen) });
      onDone();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to approve.");
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    setBusy(true);
    setError("");
    try {
      await api.post(`/admin/reassignment-requests/${req.id}/reject`, {});
      onDone();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to reject.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
      <Select value={chosen} onChange={(e) => setChosen(e.target.value)} className="min-w-[180px] flex-1">
        {eligible.length === 0 && <option value="">{t("adminReassignments.noEligibleDrivers", "No eligible drivers")}</option>}
        {eligible.map((d) => (
          <option key={d.id} value={d.id}>{d.name} ({d.driver_code})</option>
        ))}
      </Select>
      <Button variant="primary" onClick={approve} disabled={busy || !chosen}>
        <CheckCircle2 size={15} /> {t("adminReassignments.approve", "Approve")}
      </Button>
      <Button variant="danger" onClick={reject} disabled={busy}>
        <XCircle size={15} /> {t("adminReassignments.reject", "Reject")}
      </Button>
      {error && <p className="w-full text-xs text-danger">{error}</p>}
    </div>
  );
}

export default function AdminReassignments() {
  const { t } = useTranslation();
  const [requests, setRequests] = useState([]);
  const [filter, setFilter] = useState("Pending");
  const [loading, setLoading] = useState(true);

  function refresh() {
    setLoading(true);
    api.get("/admin/reassignment-requests", { params: filter === "All" ? {} : { status: filter } })
      .then((r) => setRequests(r.data))
      .finally(() => setLoading(false));
  }

  useEffect(() => { refresh(); }, [filter]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {["Pending", "Approved", "Rejected", "All"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${filter === s ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">…</GlassCard>
      ) : requests.length === 0 ? (
        <GlassCard className="flex flex-col items-center gap-2 p-10 text-center">
          <UserCog size={28} className="text-ink-faint" />
          <p className="text-sm text-ink-dim">{t("adminReassignments.none", "No reassignment requests.")}</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {requests.map((r) => (
            <GlassCard key={r.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-ink">
                    {r.trip_code} — {r.requesting_driver_name}
                  </p>
                  <p className="text-xs text-ink-dim">{r.reason}{r.description ? `: ${r.description}` : ""}</p>
                  {r.destination && (
                    <p className="mt-1 flex items-center gap-1 text-xs text-ink-faint">
                      <MapPin size={11} /> {t("adminReassignments.destination", "Destination")}: {r.destination}
                      {r.vehicle_no ? ` · ${r.vehicle_no}` : ""}
                    </p>
                  )}
                  <p className="text-[11px] text-ink-faint">{r.requested_at ? new Date(r.requested_at).toLocaleString() : ""}</p>
                </div>
                <Badge tone={STATUS_TONE[r.status] || "neutral"}>{r.status}</Badge>
              </div>

              {r.status === "Pending" && <ApproveRow req={r} onDone={refresh} />}
              {r.status !== "Pending" && r.resolution_note && (
                <p className="mt-2 border-t border-white/10 pt-2 text-xs text-ink-dim">{r.resolution_note}</p>
              )}
              {r.status === "Approved" && r.replacement_driver_name && (
                <p className="mt-1 text-xs text-success">{t("adminReassignments.reassignedTo", "Reassigned to")} {r.replacement_driver_name}</p>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}

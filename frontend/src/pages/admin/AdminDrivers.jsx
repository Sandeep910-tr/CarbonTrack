import { useEffect, useState } from "react";
import { Check, X, Ban, Eye, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge, Button, Select } from "../../components/ui";
import api from "../../lib/api";

const TABS = [
  { key: "All", labelKey: "adminDrivers.tabAll" },
  { key: "Pending", labelKey: "adminDrivers.tabPending" },
  { key: "Approved", labelKey: "adminDrivers.tabApproved" },
  { key: "Rejected", labelKey: "adminDrivers.tabRejected" },
  { key: "Blocked", labelKey: "adminDrivers.tabBlocked" },
];

const STATUS_LABEL_KEY = {
  Approved: "adminDrivers.tabApproved", Pending: "adminDrivers.tabPending",
  Rejected: "adminDrivers.tabRejected", Blocked: "adminDrivers.tabBlocked",
};

export default function AdminDrivers() {
  const { t } = useTranslation();
  const [drivers, setDrivers] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [depots, setDepots] = useState([]);
  const [tab, setTab] = useState("Pending");
  const [loading, setLoading] = useState(true);
  const [selectedDocs, setSelectedDocs] = useState(null);
  const [docsLoading, setDocsLoading] = useState(false);
  const [openingDoc, setOpeningDoc] = useState(null);


  async function load() {
    setLoading(true);
    const params = tab === "All" ? {} : { status: tab };
    const [dRes, vRes, depRes] = await Promise.all([
      api.get("/admin/drivers", { params }),
      api.get("/admin/vehicles"),
      api.get("/admin/depots"),
    ]);
    setDrivers(dRes.data);
    setVehicles(vRes.data);
    setDepots(depRes.data);
    setLoading(false);
  }

  useEffect(() => { load(); }, [tab]);

  async function approve(id) { await api.post(`/admin/drivers/${id}/approve`); load(); }
  async function reject(id) {
    const reason = prompt(t("adminDrivers.reasonForRejection")) || t("adminDrivers.documentsIncomplete");
    await api.post(`/admin/drivers/${id}/reject`, { reason });
    load();
  }
  async function block(id) { await api.post(`/admin/drivers/${id}/block`); load(); }
  async function assign(id, vehicleId) { await api.post(`/admin/drivers/${id}/assign-vehicle`, { vehicle_id: vehicleId || null }); load(); }
  async function assignDepot(id, depotId) { await api.post(`/admin/drivers/${id}/assign-depot`, { depot_id: depotId || null }); load(); }

  async function viewDocuments(id) {
    setDocsLoading(true);
    try {
      const res = await api.get(`/admin/drivers/${id}/documents`);
      setSelectedDocs(res.data);
    } catch (err) {
      alert("Failed to load documents");
    } finally {
      setDocsLoading(false);
    }
  }

  async function handleViewDocument(doc) {
    if (!doc || !doc.filename) {
      alert(t("adminDrivers.missingDocError", "Document file name is missing."));
      return;
    }

    setOpeningDoc(doc.filename);
    try {
      const res = await api.get(`/admin/documents/${encodeURIComponent(doc.filename)}`, {
        responseType: "blob",
      });

      // Retrieve and preserve Content-Type header from backend response
      const headerContentType =
        (typeof res.headers?.get === "function"
          ? res.headers.get("content-type")
          : res.headers?.["content-type"]) || "";
      let contentType = headerContentType.split(";")[0].trim().toLowerCase();

      // If backend returned generic or empty type, infer from file extension or blob.type
      if (!contentType || contentType === "application/octet-stream") {
        const ext = doc.filename.split(".").pop()?.toLowerCase();
        const extMap = {
          pdf: "application/pdf",
          jpg: "image/jpeg",
          jpeg: "image/jpeg",
          png: "image/png",
          webp: "image/webp",
          gif: "image/gif",
          svg: "image/svg+xml",
          bmp: "image/bmp",
        };
        if (ext && extMap[ext]) {
          contentType = extMap[ext];
        } else if (res.data?.type && res.data.type !== "application/octet-stream") {
          contentType = res.data.type;
        } else {
          contentType = "application/octet-stream";
        }
      }

      // Check supported preview formats (PDF and standard images)
      const isSupported =
        contentType === "application/pdf" || contentType.startsWith("image/");

      if (!isSupported) {
        alert(
          t(
            "adminDrivers.unsupportedDocFormat",
            "This document format ({{type}}) is not supported for in-browser preview.",
            { type: contentType }
          )
        );
        return;
      }

      // Explicitly construct the Blob with the correct MIME type
      const fileBlob = new Blob([res.data], { type: contentType });
      const objectUrl = URL.createObjectURL(fileBlob);

      const openedTab = window.open(objectUrl, "_blank");
      if (!openedTab) {
        alert(
          t(
            "adminDrivers.popupBlocked",
            "Document window was blocked by the browser popup blocker. Please allow popups for this site."
          )
        );
      }

      // Revoke the object URL after 60 seconds to release memory
      setTimeout(() => {
        URL.revokeObjectURL(objectUrl);
      }, 60000);
    } catch (err) {
      console.error("Failed to open document:", err);
      let errMsg = t("adminDrivers.failedToOpenDoc", "Failed to open document");
      if (err.response) {
        if (err.response.status === 404) {
          errMsg = t("adminDrivers.docNotFound", "Document not found on the server.");
        } else if (err.response.status === 403 || err.response.status === 401) {
          errMsg = t("adminDrivers.unauthorizedDoc", "You do not have permission to view this document.");
        } else if (err.response.data instanceof Blob) {
          try {
            const text = await err.response.data.text();
            const parsed = JSON.parse(text);
            if (parsed.error) errMsg = parsed.error;
          } catch (_) {}
        }
      }
      alert(errMsg);
    } finally {
      setOpeningDoc(null);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center gap-2">
        {TABS.map((tb) => (
          <button key={tb.key} onClick={() => setTab(tb.key)}
            className={`rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${tab === tb.key ? "bg-gradient-to-r from-indigo to-cyan text-[#0A0D16] shadow-[0_0_12px_-2px_rgba(34,211,238,0.5)]" : "bg-white/[0.04] text-ink-dim hover:text-ink"}`}>
            {t(tb.labelKey)}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-ink-dim">{t("common.loading")}</p>
      ) : drivers.length === 0 ? (
        <GlassCard className="p-8 text-center text-sm text-ink-dim">{t("adminDrivers.noDriversInCategory")}</GlassCard>
      ) : (
        <div className="space-y-3">
          {drivers.map((d) => (
            <GlassCard key={d.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium text-ink">{d.name}</p>
                  <span className="text-xs text-ink-faint">{d.driver_code}</span>
                  <StatusBadge status={d.status} />
                </div>
                <p className="mt-0.5 text-xs text-ink-dim">{d.email} · {d.phone} · {t("adminDrivers.license")} {d.license_no || "—"}</p>
                {d.status === "Rejected" && d.rejection_reason && (
                  <p className="mt-1 text-xs text-danger">{t("adminDrivers.reasonLabel", { reason: d.rejection_reason })}</p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {d.status === "Approved" && (
                  <>
                    <Select className="w-44" value={d.assigned_vehicle_id || ""} onChange={(e) => assign(d.id, e.target.value)}>
                      <option value="">{t("adminDrivers.unassignedVehicle")}</option>
                      {vehicles.map((v) => <option key={v.id} value={v.id}>{v.vehicle_no} ({v.vehicle_type})</option>)}
                    </Select>
                    {depots.length > 0 && (
                      <Select className="w-40" value={d.depot_id || ""} onChange={(e) => assignDepot(d.id, e.target.value)}>
                        <option value="">{t("adminDrivers.noDepot")}</option>
                        {depots.map((dep) => <option key={dep.id} value={dep.id}>{dep.name}</option>)}
                      </Select>
                    )}
                  </>
                )}
                {d.status === "Pending" && (
                  <>
                    <Button variant="ghost" onClick={() => viewDocuments(d.id)}><Eye size={14} /> {t("adminDrivers.viewDocs")}</Button>
                    <Button variant="primary" onClick={() => approve(d.id)}><Check size={14} /> {t("adminDrivers.approve")}</Button>
                    <Button variant="danger" onClick={() => reject(d.id)}><X size={14} /> {t("adminDrivers.reject")}</Button>
                  </>
                )}
                {d.status === "Approved" && (
                  <Button variant="danger" onClick={() => block(d.id)}><Ban size={14} /> {t("adminDrivers.block")}</Button>
                )}
                {(d.status === "Blocked" || d.status === "Rejected") && (
                  <Button variant="ghost" onClick={() => approve(d.id)}><Check size={14} /> {t("adminDrivers.reinstate")}</Button>
                )}
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Document Review Modal */}
      {selectedDocs || docsLoading ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm bg-black/40">
          <GlassCard strong className="w-full max-w-2xl overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 p-4">
              <h3 className="font-display text-lg font-semibold text-ink">{t("adminDrivers.reviewDocsTitle", "Document Review")}</h3>
              <button onClick={() => setSelectedDocs(null)} className="text-ink-dim hover:text-ink"><X size={20} /></button>
            </div>
            <div className="p-6">
              {docsLoading ? (
                <p className="text-center py-12 text-ink-dim">{t("common.loading")}</p>
              ) : selectedDocs && selectedDocs.length > 0 ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  {selectedDocs.map((doc) => (
                    <div key={doc.type} className="flex flex-col items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-white/5 text-ink-dim">
                        <FileText size={32} />
                      </div>
                      <p className="text-xs font-medium truncate w-full text-ink">{doc.label}</p>
                      <Button
                        variant="indigo"
                        className="w-full text-xs"
                        disabled={openingDoc === doc.filename}
                        onClick={() => handleViewDocument(doc)}
                      >
                        {openingDoc === doc.filename ? (
                          <span className="flex items-center justify-center gap-1.5">
                            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                            {t("common.loading", "Loading...")}
                          </span>
                        ) : (
                          t("adminDrivers.viewBtn", "View")
                        )}
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-center py-12 text-ink-dim">{t("adminDrivers.noDocsFound")}</p>
              )}
            </div>
          </GlassCard>
        </div>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }) {
  const { t } = useTranslation();
  const tone = { Approved: "success", Pending: "warning", Rejected: "danger", Blocked: "danger" }[status] || "neutral";
  return <Badge tone={tone}>{STATUS_LABEL_KEY[status] ? t(STATUS_LABEL_KEY[status]) : status}</Badge>;
}

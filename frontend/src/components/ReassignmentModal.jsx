import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { UserCog, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Select, TextArea } from "./ui";
import api from "../lib/api";

const REASON_KEYS = [
  ["Medical Emergency", "medicalEmergency"],
  ["Vehicle Breakdown", "vehicleBreakdown"],
  ["Accident / Safety Issue", "accidentSafety"],
  ["Personal Emergency", "personalEmergency"],
  ["Vehicle Problem", "vehicleProblem"],
  ["Unable to Continue", "unableToContinue"],
  ["Other", "other"],
];

/** Section 19-21: driver-initiated request to hand an Ongoing trip to a
 * different driver without completing it. Deliberately separate from the
 * End Trip flow — submitting this does not touch the trip's status at all. */
export default function ReassignmentModal({ open, onClose, tripId }) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("Medical Emergency");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  function handleClose() {
    if (submitting) return;
    setError("");
    setSuccess(false);
    setDescription("");
    onClose();
  }

  async function submit() {
    if (reason === "Other" && !description.trim()) {
      setError(t("reassignment.descriptionRequiredForOther"));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.post(`/driver/trips/${tripId}/reassignment-request`, { reason, description: description.trim() || undefined });
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.error || t("reassignment.submit"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={handleClose}
          role="presentation"
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.97 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reassignment-dialog-title"
          >
            <GlassCard strong className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 p-4">
                <div className="flex items-center gap-2">
                  <UserCog size={16} className="text-amber" />
                  <h3 id="reassignment-dialog-title" className="font-display text-sm font-semibold text-ink">
                    {t("reassignment.title")}
                  </h3>
                </div>
                <button onClick={handleClose} disabled={submitting} aria-label={t("common.cancel", "Cancel")} className="text-ink-dim hover:text-ink disabled:opacity-40">
                  <X size={18} />
                </button>
              </div>

              <div className="space-y-4 p-5">
                {success ? (
                  <p className="text-sm text-success">{t("reassignment.success")}</p>
                ) : (
                  <>
                    <p className="text-sm text-ink-dim">{t("reassignment.subtitle")}</p>
                    <Select label={t("reassignment.reasonLabel")} value={reason} onChange={(e) => setReason(e.target.value)}>
                      {REASON_KEYS.map(([value, key]) => (
                        <option key={value} value={value}>{t(`reassignment.reasons.${key}`)}</option>
                      ))}
                    </Select>
                    <TextArea
                      label={t("reassignment.descriptionLabel")}
                      placeholder={t("reassignment.descriptionPlaceholder")}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                    />
                    {error && <p className="text-xs text-danger">{error}</p>}
                  </>
                )}
              </div>

              <div className="flex gap-3 border-t border-white/10 p-4">
                <Button variant="ghost" className="flex-1" onClick={handleClose}>
                  {success ? t("common.close", "Close") : t("reassignment.cancel")}
                </Button>
                {!success && (
                  <Button variant="danger" className="flex-1" onClick={submit} disabled={submitting}>
                    {submitting ? t("reassignment.submitting") : t("reassignment.submit")}
                  </Button>
                )}
              </div>
            </GlassCard>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

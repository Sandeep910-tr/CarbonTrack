import { useState } from "react";
import { motion } from "framer-motion";
import { Leaf, Search, CheckCircle2, XCircle, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Button, Input, Badge } from "../components/ui";
import api from "../lib/api";
import LanguageSelector from "../components/LanguageSelector";
import { useNavigate } from "react-router-dom";

export default function RegistrationStatus() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function checkStatus() {
    setError("");
    setLoading(true);
    try {
      const res = await api.get("/auth/status", { params: { email } });
      setStatusData(res.data);
    } catch (err) {
      setError(err.response?.data?.error || t("status.error"));
      setStatusData(null);
    } finally {
      setLoading(false);
    }
  }

  const getStatusIcon = () => {
    if (!statusData) return null;
    switch (statusData.status) {
      case "Approved": return <CheckCircle2 className="text-success" size={48} />;
      case "Rejected": return <XCircle className="text-danger" size={48} />;
      case "Pending": return <Clock className="text-amber" size={48} />;
      default: return null;
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center px-6 py-16">
      <div className="absolute right-4 top-4 w-40">
        <LanguageSelector variant="topbar" />
      </div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center justify-center text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber/15 text-amber mb-3">
            <Leaf size={20} />
          </div>
          <h1 className="font-display text-2xl font-semibold text-ink">Check Application Status</h1>
          <p className="text-sm text-ink-dim mt-1">Enter your email to see the status of your driver registration.</p>
        </div>

        <GlassCard strong className="p-8">
          {!statusData ? (
            <div className="space-y-4">
              <Input
                label={t("status.emailLabel", "Email Address")}
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              {error && <p className="text-xs text-danger">{error}</p>}
              <Button variant="primary" className="w-full" onClick={checkStatus} disabled={loading || !email}>
                {loading ? t("common.loading") : t("status.checkBtn", "Check Status")}
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center text-center space-y-4">
              <div className="mb-2">{getStatusIcon()}</div>
              <h2 className="font-display text-xl font-semibold text-ink">
                {t(`status.${statusData.status.toLowerCase()}`, statusData.status)}
              </h2>
              <div className="space-y-2">
                <p className="text-sm text-ink-dim">
                  {statusData.status === "Approved"
                    ? t("status.approvedMsg", "Congratulations! Your account has been approved. You can now log in.")
                    : statusData.status === "Rejected"
                    ? t("status.rejectedMsg", "Unfortunately, your application was not approved at this time.")
                    : t("status.pendingMsg", "Your application is still under review by our admin team.")
                  }
                </p>
                {statusData.rejection_reason && (
                  <div className="rounded-lg bg-danger/10 p-3 text-xs text-danger border border-danger/20">
                    <strong>Reason:</strong> {statusData.rejection_reason}
                  </div>
                )}
              </div>
              <div className="pt-4">
                <Button variant="ghost" className="w-full" onClick={() => setStatusData(null)}>
                  Check another email
                </Button>
                {statusData.status === "Approved" && (
                  <Button variant="primary" className="w-full mt-2" onClick={() => navigate("/login")}>
                    Go to Login
                  </Button>
                )}
              </div>
            </div>
          )}
        </GlassCard>
      </motion.div>
    </div>
  );
}

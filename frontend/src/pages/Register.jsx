import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Leaf, AlertCircle, CheckCircle2, Upload } from "lucide-react";
import { useTranslation, Trans } from "react-i18next";
import { GlassCard, Button, Input } from "../components/ui";
import api from "../lib/api";
import LanguageSelector from "../components/LanguageSelector";

export default function Register() {
  const { t } = useTranslation();
  const STEPS = t("register.steps", { returnObjects: true });
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [devOtp, setDevOtp] = useState("");
  const navigate = useNavigate();

  const [form, setForm] = useState({
    identifier: "", otp: "",
    name: "", dob: "", address: "", experience_years: "", emergency_contact: "", license_no: "",
    username: "", password: "", confirm: "",
  });
  const [files, setFiles] = useState({ license_doc: null, profile_photo: null, address_proof: null });

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function sendOtp() {
    setError(""); setLoading(true);
    try {
      const res = await api.post("/auth/otp/request", { identifier: form.identifier });
      if (res.data.dev_otp) setDevOtp(res.data.dev_otp);
      setStep(1);
    } catch (err) {
      setError(err.response?.data?.error || t("register.couldNotSendOtp"));
    } finally { setLoading(false); }
  }

  async function verifyOtp() {
    setError(""); setLoading(true);
    try {
      await api.post("/auth/otp/verify", { identifier: form.identifier, code: form.otp });
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.error || t("register.invalidOtp"));
    } finally { setLoading(false); }
  }

  async function submitRegistration() {
    setError("");
    if (form.password !== form.confirm) { setError(t("register.passwordsDoNotMatch")); return; }
    if (form.password.length < 6) { setError(t("register.passwordTooShort")); return; }
    setLoading(true);
    try {
      const fd = new FormData();
      Object.entries({
        identifier: form.identifier, name: form.name, username: form.username, password: form.password,
        dob: form.dob, address: form.address, experience_years: form.experience_years,
        emergency_contact: form.emergency_contact, license_no: form.license_no,
      }).forEach(([k, v]) => fd.append(k, v || ""));
      Object.entries(files).forEach(([k, f]) => { if (f) fd.append(k, f); });

      await api.post("/auth/register", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setStep(5);
    } catch (err) {
      setError(err.response?.data?.error || t("register.registrationFailed"));
    } finally { setLoading(false); }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-6 py-16">
      <div className="absolute right-4 top-4 w-40">
        <LanguageSelector variant="topbar" />
      </div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="w-full max-w-lg">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2 font-display text-lg font-semibold text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber/15 text-amber"><Leaf size={16} /></span>
          Carbon<span className="text-amber">Track</span>
        </Link>

        <Stepper step={step} steps={STEPS} />

        <GlassCard strong className="mt-6 p-8">
          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.25 }}>

              {step === 0 && (
                <div className="space-y-4">
                  <h2 className="font-display text-lg font-semibold text-ink">{t("register.enterEmailTitle")}</h2>
                  <p className="text-sm text-ink-dim">{t("register.enterEmailSubtitle")}</p>
                  <Input label={t("register.emailAddress")} type="email" placeholder="you@company.com"
                         value={form.identifier} onChange={(e) => update("identifier", e.target.value)} />
                  <ErrorBox error={error} />
                  <Button variant="primary" className="w-full" onClick={sendOtp} disabled={loading || !form.identifier}>
                    {loading ? t("register.sending") : t("register.sendOtp")}
                  </Button>
                </div>
              )}

              {step === 1 && (
                <div className="space-y-4">
                  <h2 className="font-display text-lg font-semibold text-ink">{t("register.verifyOtpTitle")}</h2>
                  <p className="text-sm text-ink-dim">
                    <Trans i18nKey="register.verifyOtpSubtitle" values={{ identifier: form.identifier }} />
                  </p>
                  {devOtp && (
                    <div className="rounded-lg border border-indigo/30 bg-indigo/10 px-3 py-2 text-xs text-indigo-soft">
                      {t("register.devModeOtp", { otp: "" })} <span className="font-mono font-semibold">{devOtp}</span>
                    </div>
                  )}
                  <Input label={t("register.otpCode")} placeholder="123456" maxLength={6}
                         value={form.otp} onChange={(e) => update("otp", e.target.value)} />
                  <ErrorBox error={error} />
                  <Button variant="primary" className="w-full" onClick={verifyOtp} disabled={loading || form.otp.length < 4}>
                    {loading ? t("register.verifying") : t("auth.verify")}
                  </Button>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <h2 className="font-display text-lg font-semibold text-ink">{t("register.yourDetailsTitle")}</h2>
                  <Input label={t("auth.fullName")} value={form.name} onChange={(e) => update("name", e.target.value)} required />
                  <div className="grid grid-cols-2 gap-3">
                    <Input label={t("register.dateOfBirth")} type="date" value={form.dob} onChange={(e) => update("dob", e.target.value)} />
                    <Input label={t("register.experienceYears")} type="number" min="0" value={form.experience_years} onChange={(e) => update("experience_years", e.target.value)} />
                  </div>
                  <Input label={t("register.address")} value={form.address} onChange={(e) => update("address", e.target.value)} />
                  <div className="grid grid-cols-2 gap-3">
                    <Input label={t("auth.licenseNumber")} value={form.license_no} onChange={(e) => update("license_no", e.target.value)} />
                    <Input label={t("register.emergencyContact")} value={form.emergency_contact} onChange={(e) => update("emergency_contact", e.target.value)} />
                  </div>
                  <Button variant="primary" className="w-full" onClick={() => setStep(3)} disabled={!form.name}>
                    {t("register.continueBtn")}
                  </Button>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4">
                  <h2 className="font-display text-lg font-semibold text-ink">{t("register.uploadDocumentsTitle")}</h2>
                  <p className="text-sm text-ink-dim">{t("register.uploadDocumentsSubtitle")}</p>
                  <FileField label={t("register.drivingLicense")} file={files.license_doc} onChange={(f) => setFiles((s) => ({ ...s, license_doc: f }))} chooseFileLabel={t("register.chooseFile")} required />
                  <FileField label={t("register.profilePhoto")} file={files.profile_photo} onChange={(f) => setFiles((s) => ({ ...s, profile_photo: f }))} chooseFileLabel={t("register.chooseFile")} required />
                  <FileField label={t("register.addressProof")} file={files.address_proof} onChange={(f) => setFiles((s) => ({ ...s, address_proof: f }))} chooseFileLabel={t("register.chooseFile")} required />
                  <Button variant="primary" className="w-full" onClick={() => setStep(4)} disabled={!files.license_doc || !files.profile_photo || !files.address_proof}>
                    {t("register.continueBtn")}
                  </Button>
                </div>
              )}

              {step === 4 && (
                <div className="space-y-4">
                  <h2 className="font-display text-lg font-semibold text-ink">{t("register.createLoginTitle")}</h2>
                  <Input label={t("auth.username")} value={form.username} onChange={(e) => update("username", e.target.value)} required />
                  <Input label={t("auth.password")} type="password" value={form.password} onChange={(e) => update("password", e.target.value)} required />
                  <Input label={t("register.confirmPasswordField")} type="password" value={form.confirm} onChange={(e) => update("confirm", e.target.value)} required />
                  <ErrorBox error={error} />
                  <Button variant="primary" className="w-full" onClick={submitRegistration}
                          disabled={loading || !form.username || !form.password}>
                    {loading ? t("register.submitting") : t("register.submitRegistration")}
                  </Button>
                </div>
              )}

              {step === 5 && (
                <div className="flex flex-col items-center py-6 text-center">
                  <CheckCircle2 className="text-success" size={40} />
                  <h2 className="mt-4 font-display text-lg font-semibold text-ink">{t("register.submittedTitle")}</h2>
                  <p className="mt-2 text-sm text-ink-dim">
                    {t("register.submittedMessage")}
                  </p>
                  <Button variant="ghost" className="mt-6" onClick={() => navigate("/login")}>{t("register.backToLogin")}</Button>
                </div>
              )}

            </motion.div>
          </AnimatePresence>
        </GlassCard>
      </motion.div>
    </div>
  );
}

function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
      <AlertCircle size={14} className="mt-0.5 shrink-0" /> {error}
    </div>
  );
}

function FileField({ label, file, onChange, chooseFileLabel, required }) {
  return (
    <label className={`flex cursor-pointer items-center justify-between rounded-xl border px-4 py-3 text-sm transition-colors ${file ? "border-success bg-success/5" : "border-dashed border-white/15 bg-white/[0.02] hover:border-amber/40"}`}>
      <div className="flex items-center gap-2">
        {file && <CheckCircle2 size={14} className="text-success" />}
        <span className={file ? "text-ink" : "text-ink-dim"}>{label} {required && <span className="text-danger">*</span>}</span>
      </div>
      <span className={`flex items-center gap-2 ${file ? "text-success" : "text-ink-faint"}`}>
        {file ? file.name.slice(0, 20) : chooseFileLabel} <Upload size={14} />
      </span>
      <input type="file" className="hidden" onChange={(e) => onChange(e.target.files[0])} />
    </label>
  );
}

function Stepper({ step, steps }) {
  return (
    <div className="flex items-center justify-between px-1">
      {steps.map((s, i) => (
        <div key={s} className="flex flex-1 items-center">
          <div className="flex flex-col items-center gap-1">
            <div className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors
              ${i < step ? "border-amber bg-amber text-[#12100a]" : i === step ? "border-amber text-amber" : "border-white/15 text-ink-faint"}`}>
              {i < step ? "✓" : i + 1}
            </div>
            <span className={`hidden text-[10px] sm:block ${i <= step ? "text-ink-dim" : "text-ink-faint"}`}>{s}</span>
          </div>
          {i < steps.length - 1 && <div className={`mx-1 h-px flex-1 ${i < step ? "bg-amber" : "bg-white/10"}`} />}
        </div>
      ))}
    </div>
  );
}

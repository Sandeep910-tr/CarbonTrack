import { useEffect, useState } from "react";
import { User, Mail, Phone, Award, Download, IdCard, Edit2, Check, X, MapPin } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassCard, Badge, Button, EcoScoreRing, Input } from "../../components/ui";
import api from "../../lib/api";

export default function DriverProfile() {
  const { t } = useTranslation();
  const [profile, setProfile] = useState(null);
  const [certStatus, setCertStatus] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [form, setForm] = useState({});

  useEffect(() => {
    load();
    api.get("/driver/certificate/status").then((r) => setCertStatus(r.data));
  }, []);

  async function load() {
    const r = await api.get("/driver/profile");
    setProfile(r.data);
  }

  async function handleSave() {
    try {
      await api.put("/driver/profile", form);
      setIsEditing(false);
      await load();
    } catch (e) {
      console.error(e);
    }
  }

  async function downloadCertificate() {
    setDownloading(true);
    try {
      const res = await api.get("/driver/certificate/download", { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "eco_certificate.pdf";
      a.click();
    } finally {
      setDownloading(false);
    }
  }

  if (!profile) return <p className="text-ink-dim">…</p>;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <GlassCard className="p-6">
        <div className="flex items-center gap-4">
          <div className="relative shrink-0">
            <EcoScoreRing score={profile.eco_score} size={72} strokeWidth={7} />
            <span className="absolute inset-0 flex items-center justify-center font-display text-lg font-semibold text-ink">
              {Math.round(profile.eco_score)}
            </span>
          </div>
          <div className="flex-1">
            <h1 className="font-display text-xl font-semibold text-ink">{profile.name}</h1>
            <p className="flex items-center gap-2 text-xs text-ink-dim">
              <IdCard size={12} /> {profile.driver_code}
              <Badge tone={profile.status === "Approved" ? "success" : "warning"}>{profile.status}</Badge>
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setIsEditing(!isEditing);
              setForm(profile);
            }}
          >
            {isEditing ? <X size={14} /> : <Edit2 size={14} />}
          </Button>
        </div>

        <div className="mt-5 space-y-3 border-t border-white/10 pt-4 text-sm">
          {isEditing ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Input label="Name" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input label="Email" value={form.email || ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              <Input label="Phone" value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <Input label="Date of Birth" value={form.dob || ""} onChange={(e) => setForm({ ...form, dob: e.target.value })} />
              <Input label="Address" value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} />
              <Input label="Experience (Years)" type="number" value={form.experience_years || ""} onChange={(e) => setForm({ ...form, experience_years: e.target.value })} />
              <Input label="Emergency Contact" value={form.emergency_contact || ""} onChange={(e) => setForm({ ...form, emergency_contact: e.target.value })} />
              <div className="flex items-end justify-end sm:col-span-2">
                <Button variant="primary" onClick={handleSave} className="flex items-center gap-2">
                  <Check size={14} /> Save Changes
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-ink-dim"><User size={14} /> {profile.username}</div>
              <div className="flex items-center gap-2 text-ink-dim"><Mail size={14} /> {profile.email}</div>
              <div className="flex items-center gap-2 text-ink-dim"><Phone size={14} /> {profile.phone}</div>
              <div className="flex items-center gap-2 text-ink-dim"><IdCard size={14} /> DOB: {profile.dob || "Not provided"}</div>
              <div className="flex items-center gap-2 text-ink-dim"><MapPin size={14} /> {profile.address || "Not provided"}</div>
              <div className="flex items-center gap-2 text-ink-dim"><Award size={14} /> Experience: {profile.experience_years} years</div>
              <div className="flex items-center gap-2 text-ink-dim"><Phone size={14} /> Emergency: {profile.emergency_contact || "Not provided"}</div>
            </>
          )}
        </div>
      </GlassCard>

      <GlassCard className="p-6">
        <div className="flex items-center gap-2">
          <Award size={16} className="text-amber" />
          <h3 className="font-display text-sm font-semibold text-ink">{t("driverProfile.ecoCertificate", "Eco-Driving Certificate")}</h3>
        </div>
        {certStatus?.eligible ? (
          <>
            <p className="mt-2 text-sm text-ink-dim">{t("driverProfile.certEligible", "You're eligible! Download your certificate.")}</p>
            <Button variant="primary" className="mt-3" onClick={downloadCertificate} disabled={downloading}>
              <Download size={15} /> {downloading ? t("driverProfile.downloading", "Downloading...") : t("driverProfile.download", "Download Certificate")}
            </Button>
          </>
        ) : (
          <p className="mt-2 text-sm text-ink-dim">
            {t("driverProfile.certNotEligible", "Reach an eco score of {{threshold}} to unlock your certificate — {{pointsToGo}} points to go.", {
              threshold: certStatus?.threshold, pointsToGo: certStatus?.points_to_go,
            })}
          </p>
        )}
      </GlassCard>
    </div>
  );
}

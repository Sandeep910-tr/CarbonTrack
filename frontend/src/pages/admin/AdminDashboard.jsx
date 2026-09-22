import { Routes, Route, useLocation } from "react-router-dom";
import { LayoutDashboard, Users, Truck, Route as RouteIcon, BarChart3, Bell, Radio, Settings as SettingsIcon, ShieldCheck, Stethoscope, Zap, Building2, Leaf, UserCog, MessagesSquare, MessageSquareText, ScrollText, Sprout } from "lucide-react";
import { useTranslation } from "react-i18next";
import DashboardLayout from "../../components/DashboardLayout";
import AdminOverview from "./AdminOverview";
import AdminDrivers from "./AdminDrivers";
import AdminVehicles from "./AdminVehicles";
import AdminTrips from "./AdminTrips";
import AdminReports from "./AdminReports";
import AdminNotifications from "./AdminNotifications";
import AdminLiveFleet from "./AdminLiveFleet";
import AdminSettings from "./AdminSettings";
import AdminAdmins from "./AdminAdmins";
import AdminDiagnostics from "./AdminDiagnostics";
import AdminEVPlanning from "./AdminEVPlanning";
import AdminDepots from "./AdminDepots";
import AdminCarbonMethodology from "./AdminCarbonMethodology";
import AdminReassignments from "./AdminReassignments";
import AdminConversations from "./AdminConversations";
import AdminFeedback from "./AdminFeedback";
import AdminAuditLogs from "./AdminAuditLogs";
import AdminSustainability from "./AdminSustainability";

const NAV = [
  { to: "/admin", labelKey: "nav.overview", icon: LayoutDashboard, end: true },
  { to: "/admin/live-fleet", labelKey: "nav.liveFleet", icon: Radio },
  { to: "/admin/depots", labelKey: "nav.depots", icon: Building2 },
  { to: "/admin/drivers", labelKey: "nav.drivers", icon: Users },
  { to: "/admin/vehicles", labelKey: "nav.vehicles", icon: Truck },
  { to: "/admin/trips", labelKey: "nav.trips", icon: RouteIcon },
  { to: "/admin/reassignments", labelKey: "nav.reassignments", icon: UserCog },
  { to: "/admin/conversations", labelKey: "nav.conversations", icon: MessagesSquare },
  { to: "/admin/carbon-methodology", labelKey: "nav.carbonMethodology", icon: Leaf },
  { to: "/admin/sustainability", labelKey: "nav.sustainability", icon: Sprout },
  { to: "/admin/reports", labelKey: "nav.reports", icon: BarChart3 },
  { to: "/admin/ev-planning", labelKey: "nav.evPlanning", icon: Zap },
  { to: "/admin/feedback", labelKey: "nav.feedback", icon: MessageSquareText },
  { to: "/admin/audit-logs", labelKey: "nav.auditLogs", icon: ScrollText },
  { to: "/admin/notifications", labelKey: "nav.notifications", icon: Bell },
  { to: "/admin/admins", labelKey: "nav.adminAccounts", icon: ShieldCheck },
  { to: "/admin/diagnostics", labelKey: "nav.apiDiagnostics", icon: Stethoscope },
  { to: "/admin/settings", labelKey: "nav.settings", icon: SettingsIcon },
];

export default function AdminDashboard() {
  const { t } = useTranslation();
  const location = useLocation();
  // The Overview page has its own bespoke "Fleet Overview" header already,
  // so it opts out of the shared page-title bar rather than showing two.
  const match = NAV.find((n) => n.to === location.pathname);
  const title = match && match.to !== "/admin" ? t(match.labelKey) : undefined;

  return (
    <DashboardLayout nav={NAV} title={title}>
      <Routes>
        <Route index element={<AdminOverview />} />
        <Route path="live-fleet" element={<AdminLiveFleet />} />
        <Route path="depots" element={<AdminDepots />} />
        <Route path="drivers" element={<AdminDrivers />} />
        <Route path="vehicles" element={<AdminVehicles />} />
        <Route path="trips" element={<AdminTrips />} />
        <Route path="reassignments" element={<AdminReassignments />} />
        <Route path="conversations" element={<AdminConversations />} />
        <Route path="carbon-methodology" element={<AdminCarbonMethodology />} />
        <Route path="sustainability" element={<AdminSustainability />} />
        <Route path="reports" element={<AdminReports />} />
        <Route path="ev-planning" element={<AdminEVPlanning />} />
        <Route path="feedback" element={<AdminFeedback />} />
        <Route path="audit-logs" element={<AdminAuditLogs />} />
        <Route path="notifications" element={<AdminNotifications />} />
        <Route path="admins" element={<AdminAdmins />} />
        <Route path="diagnostics" element={<AdminDiagnostics />} />
        <Route path="settings" element={<AdminSettings />} />
      </Routes>
    </DashboardLayout>
  );
}

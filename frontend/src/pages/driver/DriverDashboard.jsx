import { Routes, Route, useLocation } from "react-router-dom";
import { LayoutDashboard, PlusCircle, History, Bell, MessagesSquare, Truck, UserCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import DashboardLayout from "../../components/DashboardLayout";
import DriverOverview from "./DriverOverview";
import NewTrip from "./NewTrip";
import TripHistory from "./TripHistory";
import DriverNotifications from "./DriverNotifications";
import DriverConversations from "./DriverConversations";
import DriverVehicle from "./DriverVehicle";
import DriverProfile from "./DriverProfile";

const NAV = [
  { to: "/driver", labelKey: "nav.overview", icon: LayoutDashboard, end: true },
  { to: "/driver/new-trip", labelKey: "nav.newTrip", icon: PlusCircle },
  { to: "/driver/history", labelKey: "nav.tripHistory", icon: History },
  { to: "/driver/vehicle", labelKey: "nav.vehicle", icon: Truck },
  { to: "/driver/conversations", labelKey: "nav.conversations", icon: MessagesSquare },
  { to: "/driver/notifications", labelKey: "nav.notifications", icon: Bell },
  { to: "/driver/profile", labelKey: "nav.profile", icon: UserCircle },
];

export default function DriverDashboard() {
  const { t } = useTranslation();
  const location = useLocation();
  // The Overview page has its own bespoke welcome header already, so it
  // opts out of the shared page-title bar rather than showing two headers.
  const match = NAV.find((n) => n.to === location.pathname);
  const title = match && match.to !== "/driver" ? t(match.labelKey) : undefined;

  return (
    <DashboardLayout nav={NAV} title={title}>
      <Routes>
        <Route index element={<DriverOverview />} />
        <Route path="new-trip" element={<NewTrip />} />
        <Route path="history" element={<TripHistory />} />
        <Route path="vehicle" element={<DriverVehicle />} />
        <Route path="conversations" element={<DriverConversations />} />
        <Route path="notifications" element={<DriverNotifications />} />
        <Route path="profile" element={<DriverProfile />} />
      </Routes>
    </DashboardLayout>
  );
}

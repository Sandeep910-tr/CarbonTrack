import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { NotificationProvider } from "./context/NotificationContext";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AdminDashboard from "./pages/admin/AdminDashboard";
import DriverDashboard from "./pages/driver/DriverDashboard";

function Protected({ role, children }) {
  const { token, role: currentRole } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (role && currentRole !== role) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/admin/*"
        element={
          <Protected role="admin">
            <AdminDashboard />
          </Protected>
        }
      />
      <Route
        path="/driver/*"
        element={
          <Protected role="driver">
            <DriverDashboard />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  // Section 49 (Accessibility): the CSS `prefers-reduced-motion` block in
  // index.css only affects plain CSS transitions/animations - it has no
  // effect on Framer Motion's JS-driven `animate` props, which is most of
  // this app's cinematic motion. MotionConfig with reducedMotion="user"
  // makes every motion.* component in the tree automatically respect the
  // OS-level "reduce motion" setting (collapsing transforms/opacity fades
  // to instant, near-zero-duration changes) without touching each animation
  // definition individually.
  return (
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AuthProvider>
          <NotificationProvider>
            <AppRoutes />
          </NotificationProvider>
        </AuthProvider>
      </BrowserRouter>
    </MotionConfig>
  );
}

import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../store/AuthContext";

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    const loginPath = location.pathname.startsWith("/admin") ? "/admin/login" : "/login";
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }

  if (adminOnly && !user?.is_admin) {
    return <Navigate to="/admin/login" replace />;
  }

  return children;
}

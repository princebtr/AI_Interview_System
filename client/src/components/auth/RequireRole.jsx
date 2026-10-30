import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

// UI-level guard only; the backend enforces the same roles on every endpoint.
const RequireRole = ({ roles, children }) => {
  const { user } = useAuth();
  return roles.includes(user?.role) ? children : <Navigate to="/dashboard" replace />;
};

export default RequireRole;

import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { LogoMark, Spinner } from "../ui";

/**
 * Requires a signed-in user. Users still on a temporary password are held on
 * the password-setup page (`passwordSetup`) until they choose their own.
 */
const ProtectedRoute = ({ children, passwordSetup = false }) => {
  const { isAuthenticated, loading, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <LogoMark className="size-9" />
        <Spinner className="size-5 text-slate-400" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const pending = Boolean(user?.mustChangePassword);
  if (pending && !passwordSetup) return <Navigate to="/set-password" replace />;
  if (!pending && passwordSetup) return <Navigate to="/dashboard" replace />;

  return children;
};

export default ProtectedRoute;

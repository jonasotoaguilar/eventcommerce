import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/session";

/**
 * Guards shopper-only routes (cart, checkout, order tracking land here in
 * U2/U3). Anonymous shoppers are sent to /login with the attempted path
 * preserved in `state.next` so they return after signing in.
 */
export function ProtectedRoute({ children }: { children: React.JSX.Element }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <p role="status">Checking your session…</p>;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ next: location.pathname }} />;
  }
  return children;
}

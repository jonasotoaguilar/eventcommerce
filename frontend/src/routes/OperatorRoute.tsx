import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/session";
import { isOperator } from "../lib/operator";

/**
 * Guards operator-only screens. Anonymous visitors are sent to /login
 * with the attempted path preserved in `state.next` (same contract as
 * <ProtectedRoute>); signed-in shoppers see a rejection instead of the
 * page, so the operator console never renders for the wrong role.
 */
export function OperatorRoute({ children }: { children: React.JSX.Element }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <p role="status">Checking your operator session…</p>;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ next: location.pathname }} />;
  }
  if (!isOperator(user)) {
    return (
      <p role="alert">
        This area is for store operators. Your account does not have operator access.
      </p>
    );
  }
  return children;
}

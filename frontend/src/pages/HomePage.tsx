import { Link } from "react-router-dom";
import { useAuth } from "../auth/session";

export function HomePage() {
  const { status, user } = useAuth();

  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">EventCommerce</h1>
      <p>
        {status === "authenticated" && user
          ? `Welcome back, ${user.email}. Catalog, cart, and order tracking arrive in the next slice.`
          : "Browse the catalog, check out, and track your order. Sign in to get started."}
      </p>
      {status !== "authenticated" && (
        <p className="cta-row">
          <Link className="button button-primary" to="/register">
            Create account
          </Link>{" "}
          <Link className="button button-secondary" to="/login">
            Log in
          </Link>
        </p>
      )}
      <div className="notice" role="status" aria-live="polite">
        Catalog browsing opens in the next work unit.
      </div>
    </section>
  );
}

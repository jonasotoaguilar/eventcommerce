import { Link } from "react-router-dom";
import { useAuth } from "../auth/session";

export function HomePage() {
  const { status, user } = useAuth();

  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">EventCommerce</h1>
      <p>
        {status === "authenticated" && user
          ? `Welcome back, ${user.email}. Browse the catalog and review your cart.`
          : "Browse the catalog, check out, and track your order. Sign in to get started."}
      </p>
      <p className="cta-row">
        <Link className="button button-primary" to="/catalog">
          Browse the catalog
        </Link>{" "}
        {status !== "authenticated" ? (
          <>
            <Link className="button button-secondary" to="/register">
              Create account
            </Link>{" "}
            <Link className="button button-secondary" to="/login">
              Log in
            </Link>
          </>
        ) : (
          <Link className="button button-secondary" to="/cart">
            Review your cart
          </Link>
        )}
      </p>
      <div className="notice" role="status" aria-live="polite">
        Checkout and order tracking are available from your cart.
      </div>
    </section>
  );
}

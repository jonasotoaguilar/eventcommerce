import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/session";

export function Layout({ children }: { children: React.ReactNode }) {
  const { status, user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <nav className="site-nav" aria-label="Primary">
          <Link className="brand" to="/">
            EventCommerce
          </Link>
          <ul className="nav-links">
            <li>
              <NavLink to="/">Home</NavLink>
            </li>
            {status === "authenticated" && user ? (
              <>
                <li className="nav-user" aria-label={`Signed in as ${user.email}`}>
                  {user.email}
                </li>
                <li>
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => {
                      logout();
                      navigate("/");
                    }}
                  >
                    Log out
                  </button>
                </li>
              </>
            ) : (
              <>
                <li>
                  <NavLink to="/login">Log in</NavLink>
                </li>
                <li>
                  <NavLink to="/register">Register</NavLink>
                </li>
              </>
            )}
          </ul>
        </nav>
      </header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        {children}
      </main>
      <footer className="site-footer">
        <p>EventCommerce shopper storefront.</p>
      </footer>
    </div>
  );
}

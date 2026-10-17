import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/session";

export function LoginPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const next = (location.state as { next?: string } | null)?.next ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const errorId = "login-error";
  // Only reference the error region while it is rendered; never point at a missing ID.
  const emailDescribedBy = error ? errorId : undefined;
  const passwordDescribedBy = error ? `login-password-hint ${errorId}` : "login-password-hint";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="login-title" className="form-section">
      <h1 id="login-title">Log in</h1>
      {error && (
        <div id={errorId} className="alert alert-error" role="alert">
          {error}
        </div>
      )}
      <form onSubmit={onSubmit} noValidate={false}>
        <div className="field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-describedby={emailDescribedBy}
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby={passwordDescribedBy}
          />
          <p id="login-password-hint" className="hint">
            Use the password you registered with (8+ characters).
          </p>
        </div>
        <button
          type="submit"
          className="button button-primary"
          disabled={pending || status === "loading"}
          aria-disabled={pending || status === "loading"}
          aria-busy={pending}
        >
          {pending ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p>
        No account yet? <Link to="/register">Register</Link>.
      </p>
    </section>
  );
}

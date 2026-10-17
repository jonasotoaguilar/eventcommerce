import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/session";

export function RegisterPage() {
  const { register, status } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const errorId = "register-error";
  // Only reference the error region while it is rendered; never point at a missing ID.
  const emailDescribedBy = error ? errorId : undefined;
  const passwordDescribedBy = error
    ? `register-password-hint ${errorId}`
    : "register-password-hint";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await register(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="register-title" className="form-section">
      <h1 id="register-title">Create your account</h1>
      {error && (
        <div id={errorId} className="alert alert-error" role="alert">
          {error}
        </div>
      )}
      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="register-email">Email</label>
          <input
            id="register-email"
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
          <label htmlFor="register-password">Password</label>
          <input
            id="register-password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby={passwordDescribedBy}
          />
          <p id="register-password-hint" className="hint">
            8–128 characters.
          </p>
        </div>
        <button
          type="submit"
          className="button button-primary"
          disabled={pending || status === "loading"}
          aria-disabled={pending || status === "loading"}
          aria-busy={pending}
        >
          {pending ? "Creating account…" : "Register"}
        </button>
      </form>
      <p>
        Already registered? <Link to="/login">Log in</Link>.
      </p>
    </section>
  );
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { createAuthClient, type SessionUser } from "../lib/auth";
import { ApiError } from "../lib/api-client";

export type SessionStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: SessionStatus;
  user: SessionUser | null;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Client-side shopper session. The token persists in localStorage so a
 * page reload keeps the session; expiry and 401 responses return the
 * shopper to the anonymous state (routes redirect to /login).
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const client = useMemo(
    () =>
      createAuthClient({
        onSessionExpired: () => {
          setUser(null);
          setStatus("anonymous");
        },
      }),
    [],
  );
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (client.getToken() === null) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    setStatus("loading");
    try {
      const me = await client.me();
      setUser(me);
      setStatus("authenticated");
      setError(null);
    } catch (err) {
      // createAuthClient already cleared the token on 401.
      setUser(null);
      setStatus("anonymous");
      if (!(err instanceof ApiError && err.status === 401)) {
        setError(err instanceof Error ? err.message : "Could not restore the session.");
      }
    }
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      setError(null);
      try {
        const me = await client.login(email, password);
        setUser(me);
        setStatus("authenticated");
      } catch (err) {
        setStatus("anonymous");
        const message = err instanceof Error ? err.message : "Login failed.";
        setError(message);
        throw err;
      }
    },
    [client],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      setError(null);
      try {
        const me = await client.register(email, password);
        setUser(me);
        setStatus("authenticated");
      } catch (err) {
        setStatus("anonymous");
        const message = err instanceof Error ? err.message : "Registration failed.";
        setError(message);
        throw err;
      }
    },
    [client],
  );

  const logout = useCallback(() => {
    client.logout();
    setUser(null);
    setStatus("anonymous");
    setError(null);
  }, [client]);

  const value = useMemo(
    () => ({ status, user, error, login, register, logout, refresh }),
    [status, user, error, login, register, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) throw new Error("useAuth must be used inside <AuthProvider>.");
  return ctx;
}

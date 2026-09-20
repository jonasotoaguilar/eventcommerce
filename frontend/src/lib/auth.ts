import { createApiClient, type ApiClient } from "./api-client";

export interface SessionUser {
  user_id: string;
  email: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

const STORAGE_KEY = "eventcommerce.auth.token";

/** Read the persisted bearer token, if any. */
export function readStoredToken(storage: Storage = localStorage): string | null {
  try {
    return storage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredToken(token: string | null, storage: Storage = localStorage): void {
  try {
    if (token === null) storage.removeItem(STORAGE_KEY);
    else storage.setItem(STORAGE_KEY, token);
  } catch {
    // Private-mode storage failures must not break the app shell.
  }
}

/**
 * Best-effort JWT expiry check (signature is verified server-side).
 * Returns true when the token carries an `exp` claim in the past or is
 * malformed; tokens without `exp` are treated as not expired.
 */
export function isTokenExpired(token: string, nowSeconds: number = Date.now() / 1000): boolean {
  const parts = token.split(".");
  if (parts.length < 2) return true;
  try {
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof payload.exp !== "number") return false;
    return payload.exp <= nowSeconds;
  } catch {
    return true;
  }
}

export interface AuthClientOptions {
  api?: ApiClient;
  storage?: Storage;
  /** Called after the token is cleared following a 401/expired session. */
  onSessionExpired?: () => void;
}

/**
 * Shopper auth session over the IAM contract:
 * POST /api/v1/iam/register {email,password} -> 201
 * POST /api/v1/iam/login -> {access_token, token_type}
 * GET  /api/v1/iam/me   -> {user_id, email, role}
 */
export function createAuthClient(options: AuthClientOptions = {}) {
  const storage = options.storage ?? localStorage;
  let token: string | null = readStoredToken(storage);
  if (token !== null && isTokenExpired(token)) {
    token = null;
    writeStoredToken(null, storage);
  }

  const api =
    options.api ??
    createApiClient({
      getToken: () => token,
      onUnauthorized: () => {
        clearSession();
        options.onSessionExpired?.();
      },
    });

  function clearSession(): void {
    token = null;
    writeStoredToken(null, storage);
  }

  return {
    getToken: () => token,
    api,
    async register(email: string, password: string): Promise<SessionUser> {
      await api.post<unknown>("/iam/register", { email, password });
      // Registration returns the user shape but no token; log in to open the session.
      return this.login(email, password);
    },
    async login(email: string, password: string): Promise<SessionUser> {
      const tokens = await api.post<TokenResponse>("/iam/login", { email, password });
      token = tokens.access_token;
      writeStoredToken(token, storage);
      return this.me();
    },
    async me(): Promise<SessionUser> {
      return api.get<SessionUser>("/iam/me");
    },
    logout(): void {
      clearSession();
    },
  };
}

export type AuthClient = ReturnType<typeof createAuthClient>;

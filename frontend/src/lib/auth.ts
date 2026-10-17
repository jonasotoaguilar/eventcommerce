import { createApiClient, type ApiClient } from "./api-client";
import { createSingleflight } from "./refresh";

export interface SessionUser {
  user_id: string;
  email: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

const STORAGE_KEY = "eventcommerce.auth.token";
const REFRESH_STORAGE_KEY = "eventcommerce.auth.refresh_token";
const REFRESH_PATH = "/iam/refresh";

/** Read the persisted bearer token, if any. */
export function readStoredToken(storage: Storage = localStorage): string | null {
  try {
    return storage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Read the persisted opaque refresh token, if any. */
export function readStoredRefreshToken(
  storage: Storage = localStorage,
): string | null {
  try {
    return storage.getItem(REFRESH_STORAGE_KEY);
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

function writeStoredRefreshToken(
  token: string | null,
  storage: Storage = localStorage,
): void {
  try {
    if (token === null) storage.removeItem(REFRESH_STORAGE_KEY);
    else storage.setItem(REFRESH_STORAGE_KEY, token);
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
  baseUrl?: string;
  /** Called after the token is cleared following a 401/expired session. */
  onSessionExpired?: () => void;
}

/**
 * Shopper auth session over the IAM contract:
 * POST /api/v1/iam/register {email,password} -> 201
 * POST /api/v1/iam/login -> {access_token, refresh_token, token_type}
 * POST /api/v1/iam/refresh {refresh_token} -> {access_token, refresh_token}
 * GET  /api/v1/iam/me   -> {user_id, email, role}
 *
 * A 401 on a bearer request refreshes the pair once and retries the
 * request once; the session is cleared only when the refresh fails.
 * The opaque refresh token carries no `exp` claim, so unlike the access
 * token it is never expiry-checked client-side; the server owns expiry.
 */
export function createAuthClient(options: AuthClientOptions = {}) {
  const storage = options.storage ?? localStorage;
  const baseUrl = options.baseUrl ?? "/api/v1";
  let token: string | null = readStoredToken(storage);
  if (token !== null && isTokenExpired(token)) {
    token = null;
    writeStoredToken(null, storage);
  }
  let refreshToken: string | null = readStoredRefreshToken(storage);

  function clearSession(): void {
    token = null;
    refreshToken = null;
    writeStoredToken(null, storage);
    writeStoredRefreshToken(null, storage);
  }

  async function runRefresh(): Promise<string | null> {
    if (refreshToken === null) return null;
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${REFRESH_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      return null;
    }
    // A failed refresh clears the pair; the client's onUnauthorized hook
    // owns the single session-expired notification that follows.
    if (!response.ok) {
      clearSession();
      return null;
    }
    let pair: TokenResponse;
    try {
      pair = (await response.json()) as TokenResponse;
    } catch {
      return null;
    }
    if (typeof pair.access_token !== "string" || pair.access_token.length === 0) {
      return null;
    }
    token = pair.access_token;
    writeStoredToken(token, storage);
    if (typeof pair.refresh_token === "string" && pair.refresh_token.length > 0) {
      refreshToken = pair.refresh_token;
      writeStoredRefreshToken(refreshToken, storage);
    }
    return token;
  }

  const refreshAccessToken = createSingleflight(runRefresh);

  const api =
    options.api ??
    createApiClient({
      baseUrl,
      getToken: () => token,
      onUnauthorized: () => {
        clearSession();
        options.onSessionExpired?.();
      },
      refreshAccessToken,
    });

  return {
    getToken: () => token,
    getRefreshToken: () => refreshToken,
    api,
    async register(email: string, password: string): Promise<SessionUser> {
      await api.post<unknown>("/iam/register", { email, password });
      // Registration returns the user shape but no token; log in to open the session.
      return this.login(email, password);
    },
    async login(email: string, password: string): Promise<SessionUser> {
      const tokens = await api.post<TokenResponse>("/iam/login", { email, password });
      token = tokens.access_token;
      refreshToken = tokens.refresh_token;
      writeStoredToken(token, storage);
      writeStoredRefreshToken(refreshToken, storage);
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

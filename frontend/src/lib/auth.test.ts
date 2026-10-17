import { describe, expect, it, vi, beforeEach } from "vitest";
import { createAuthClient } from "./auth";
import { isTokenExpired } from "./auth";

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const store: Record<string, string> = { ...initial };
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const key of Object.keys(store)) delete store[key];
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
    get length() {
      return Object.keys(store).length;
    },
  } as Storage;
}

function unsignedToken(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_");
  return `${encode({ alg: "none" })}.${encode(payload)}.sig`;
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ACCESS_KEY = "eventcommerce.auth.token";
const REFRESH_KEY = "eventcommerce.auth.refresh_token";

describe("isTokenExpired", () => {
  it("treats tokens without exp as not expired", () => {
    expect(isTokenExpired(unsignedToken({ sub: "u-1" }))).toBe(false);
  });

  it("detects past and future exp claims", () => {
    const now = Date.now() / 1000;
    expect(isTokenExpired(unsignedToken({ exp: now - 60 }), now)).toBe(true);
    expect(isTokenExpired(unsignedToken({ exp: now + 3600 }), now)).toBe(false);
  });

  it("treats malformed tokens as expired", () => {
    expect(isTokenExpired("not-a-token")).toBe(true);
  });
});

describe("createAuthClient refresh-token session", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  function loginResponse(accessExp: number) {
    return {
      access_token: unsignedToken({ sub: "u-1", exp: accessExp }),
      refresh_token: "opaque-refresh-1",
      token_type: "bearer",
    };
  }

  it("persists the refresh token alongside the access token on login", async () => {
    const now = Date.now() / 1000;
    const fetchMock = vi.fn(async (url: unknown) => {
      const path = String(url);
      if (path.endsWith("/iam/login")) return jsonResponse(200, loginResponse(now + 3600));
      return jsonResponse(200, { user_id: "u-1", email: "a@example.com", role: "shopper" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const storage = memoryStorage();
    const client = createAuthClient({ storage });

    await client.login("a@example.com", "valid-pass-1");

    expect(storage.getItem(ACCESS_KEY)).not.toBeNull();
    expect(storage.getItem(REFRESH_KEY)).toBe("opaque-refresh-1");
    expect(client.getRefreshToken()).toBe("opaque-refresh-1");
  });

  it("restores both tokens from storage and keeps an opaque refresh token", () => {
    const now = Date.now() / 1000;
    const storage = memoryStorage({
      [ACCESS_KEY]: unsignedToken({ sub: "u-1", exp: now + 3600 }),
      [REFRESH_KEY]: "opaque-refresh-1",
    });

    const client = createAuthClient({ storage });

    expect(client.getToken()).not.toBeNull();
    expect(client.getRefreshToken()).toBe("opaque-refresh-1");
  });

  it("drops an expired access token at load but keeps the refresh token", () => {
    const now = Date.now() / 1000;
    const storage = memoryStorage({
      [ACCESS_KEY]: unsignedToken({ sub: "u-1", exp: now - 60 }),
      [REFRESH_KEY]: "opaque-refresh-1",
    });

    const client = createAuthClient({ storage });

    expect(client.getToken()).toBeNull();
    expect(storage.getItem(ACCESS_KEY)).toBeNull();
    expect(client.getRefreshToken()).toBe("opaque-refresh-1");
    expect(storage.getItem(REFRESH_KEY)).toBe("opaque-refresh-1");
  });

  it("refreshes exactly once and retries the original request after a 401", async () => {
    const now = Date.now() / 1000;
    const staleAccess = unsignedToken({ sub: "u-1", exp: now + 3600, jti: "old" });
    const renewedAccess = unsignedToken({ sub: "u-1", exp: now + 3600, jti: "new" });
    const calls: Array<{ method: string; path: string; auth: string | null }> = [];
    const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
      const path = String(url);
      const headers = (init?.headers ?? {}) as Record<string, string>;
      calls.push({
        method: init?.method ?? "GET",
        path,
        auth: headers.Authorization ?? null,
      });
      if (path.endsWith("/iam/refresh")) {
        return jsonResponse(200, {
          access_token: renewedAccess,
          refresh_token: "opaque-refresh-2",
          token_type: "bearer",
        });
      }
      if (headers.Authorization === `Bearer ${renewedAccess}`) {
        return jsonResponse(200, { user_id: "u-1", email: "a@example.com", role: "shopper" });
      }
      return jsonResponse(401, { detail: "Invalid or expired token" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const storage = memoryStorage({
      [ACCESS_KEY]: staleAccess,
      [REFRESH_KEY]: "opaque-refresh-1",
    });
    const onSessionExpired = vi.fn();
    const client = createAuthClient({ storage, onSessionExpired });

    const me = await client.me();

    expect(me.email).toBe("a@example.com");
    expect(calls.filter((c) => c.path.endsWith("/iam/refresh"))).toHaveLength(1);
    expect(calls.filter((c) => c.path.endsWith("/iam/me"))).toHaveLength(2);
    expect(client.getRefreshToken()).toBe("opaque-refresh-2");
    expect(storage.getItem(REFRESH_KEY)).toBe("opaque-refresh-2");
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it("clears both tokens when the refresh itself fails", async () => {
    const now = Date.now() / 1000;
    const fetchMock = vi.fn(async (url: unknown) => {
      if (String(url).endsWith("/iam/refresh")) {
        return jsonResponse(401, { detail: "Invalid or expired token" });
      }
      return jsonResponse(401, { detail: "Invalid or expired token" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const storage = memoryStorage({
      [ACCESS_KEY]: unsignedToken({ sub: "u-1", exp: now + 3600 }),
      [REFRESH_KEY]: "stolen-or-revoked",
    });
    const onSessionExpired = vi.fn();
    const client = createAuthClient({ storage, onSessionExpired });

    await expect(client.me()).rejects.toMatchObject({ status: 401 });

    expect(client.getToken()).toBeNull();
    expect(client.getRefreshToken()).toBeNull();
    expect(storage.getItem(ACCESS_KEY)).toBeNull();
    expect(storage.getItem(REFRESH_KEY)).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledOnce();
  });

  it("issues a single refresh for concurrent 401s", async () => {
    const now = Date.now() / 1000;
    const staleAccess = unsignedToken({ sub: "u-1", exp: now + 3600, jti: "old" });
    const renewedAccess = unsignedToken({ sub: "u-1", exp: now + 3600, jti: "new" });
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
      const path = String(url);
      const headers = (init?.headers ?? {}) as Record<string, string>;
      if (path.endsWith("/iam/refresh")) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
        return jsonResponse(200, {
          access_token: renewedAccess,
          refresh_token: "opaque-refresh-2",
          token_type: "bearer",
        });
      }
      if (headers.Authorization === `Bearer ${renewedAccess}`) {
        return jsonResponse(200, { user_id: "u-1", email: "a@example.com", role: "shopper" });
      }
      return jsonResponse(401, { detail: "Invalid or expired token" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const storage = memoryStorage({
      [ACCESS_KEY]: staleAccess,
      [REFRESH_KEY]: "opaque-refresh-1",
    });
    const client = createAuthClient({ storage });

    const [first, second] = await Promise.all([client.me(), client.me()]);

    expect(first.email).toBe("a@example.com");
    expect(second.email).toBe("a@example.com");
    expect(refreshCalls).toBe(1);
  });

  it("clears both tokens on logout", async () => {
    const now = Date.now() / 1000;
    const fetchMock = vi.fn(async (url: unknown) => {
      const path = String(url);
      if (path.endsWith("/iam/login")) return jsonResponse(200, loginResponse(now + 3600));
      return jsonResponse(200, { user_id: "u-1", email: "a@example.com", role: "shopper" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const storage = memoryStorage();
    const client = createAuthClient({ storage });
    await client.login("a@example.com", "valid-pass-1");

    client.logout();

    expect(client.getToken()).toBeNull();
    expect(client.getRefreshToken()).toBeNull();
    expect(storage.getItem(ACCESS_KEY)).toBeNull();
    expect(storage.getItem(REFRESH_KEY)).toBeNull();
  });
});

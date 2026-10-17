import { describe, expect, it, vi, beforeEach } from "vitest";
import { ApiError, createApiClient } from "./api-client";
import { createSingleflight } from "./refresh";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createSingleflight", () => {
  it("shares one in-flight call across concurrent callers", async () => {
    let calls = 0;
    const guarded = createSingleflight(async () => {
      calls += 1;
      await new Promise((resolve) => setTimeout(resolve, 5));
      return "fresh-token";
    });

    const [first, second, third] = await Promise.all([
      guarded(),
      guarded(),
      guarded(),
    ]);

    expect(first).toBe("fresh-token");
    expect(second).toBe("fresh-token");
    expect(third).toBe("fresh-token");
    expect(calls).toBe(1);
  });

  it("invokes again after the previous call settled", async () => {
    let calls = 0;
    const guarded = createSingleflight(async () => {
      calls += 1;
      return `token-${calls}`;
    });

    expect(await guarded()).toBe("token-1");
    expect(await guarded()).toBe("token-2");
    expect(calls).toBe(2);
  });

  it("propagates rejection to every waiter and allows a later retry", async () => {
    let calls = 0;
    const guarded = createSingleflight(async () => {
      calls += 1;
      if (calls === 1) throw new Error("refresh down");
      return "recovered";
    });

    await expect(
      Promise.all([guarded(), guarded(), guarded()]),
    ).rejects.toThrow("refresh down");
    expect(calls).toBe(1);
    await expect(guarded()).resolves.toBe("recovered");
    expect(calls).toBe(2);
  });
});

describe("createApiClient refresh-and-retry", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("refreshes once and retries the original request once with the new token", async () => {
    const seenAuth: Array<string | null> = [];
    const fetchMock = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      seenAuth.push(headers.Authorization ?? null);
      if (headers.Authorization === "Bearer renewed") {
        return jsonResponse(200, { user_id: "u-1" });
      }
      return jsonResponse(401, { detail: "Invalid or expired token" });
    });
    vi.stubGlobal("fetch", fetchMock);
    let current: string | null = "stale";
    const refreshAccessToken = vi.fn(async () => {
      current = "renewed";
      return current;
    });
    const onUnauthorized = vi.fn();
    const api = createApiClient({
      getToken: () => current,
      onUnauthorized,
      refreshAccessToken,
    });

    const result = await api.get<{ user_id: string }>("/iam/me");

    expect(result).toEqual({ user_id: "u-1" });
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(seenAuth).toEqual(["Bearer stale", "Bearer renewed"]);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("clears the session without retrying when the refresh fails", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(401, { detail: "Invalid or expired token" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onUnauthorized = vi.fn();
    const api = createApiClient({
      getToken: () => "stale",
      onUnauthorized,
      refreshAccessToken: async () => null,
    });

    const failure = api.get("/iam/me").catch((err: unknown) => err);

    await expect(failure).resolves.toBeInstanceOf(ApiError);
    expect((await failure) as ApiError).toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not attempt a refresh for a request sent without a token", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(401, { detail: "Invalid email or password" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const refreshAccessToken = vi.fn(async () => "renewed");
    const api = createApiClient({
      getToken: () => null,
      refreshAccessToken,
    });

    await expect(api.post("/iam/login", {})).rejects.toBeInstanceOf(ApiError);

    expect(refreshAccessToken).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("notifies once when the retried request is still unauthorized", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(401, { detail: "Invalid or expired token" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    let current: string | null = "stale";
    const refreshAccessToken = vi.fn(async () => {
      current = "renewed";
      return current;
    });
    const onUnauthorized = vi.fn();
    const api = createApiClient({
      getToken: () => current,
      onUnauthorized,
      refreshAccessToken,
    });

    await expect(api.get("/iam/me")).rejects.toBeInstanceOf(ApiError);

    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("shares one refresh across concurrent 401s instead of storming", async () => {
    const fetchMock = vi.fn(async (_url: unknown, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      if (headers.Authorization === "Bearer renewed") {
        return jsonResponse(200, { user_id: "u-1" });
      }
      return jsonResponse(401, { detail: "Invalid or expired token" });
    });
    vi.stubGlobal("fetch", fetchMock);
    let current: string | null = "stale";
    const underlying = vi.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
      current = "renewed";
      return current;
    });
    const api = createApiClient({
      getToken: () => current,
      refreshAccessToken: createSingleflight(underlying),
    });

    const [first, second] = await Promise.all([
      api.get<{ user_id: string }>("/iam/me"),
      api.get<{ user_id: string }>("/orders"),
    ]);

    expect(first).toEqual({ user_id: "u-1" });
    expect(second).toEqual({ user_id: "u-1" });
    expect(underlying).toHaveBeenCalledOnce();
  });
});

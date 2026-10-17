import { describe, expect, it, vi, beforeEach } from "vitest";
import { ApiError, createApiClient, extractDetail } from "./api-client";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("extractDetail", () => {
  it("returns the backend string detail", () => {
    expect(extractDetail({ detail: "Invalid email or password" }, "fallback")).toBe(
      "Invalid email or password",
    );
  });

  it("joins FastAPI validation error lists", () => {
    const detail = extractDetail(
      { detail: [{ msg: "email is required" }, { msg: "password too short" }] },
      "fallback",
    );
    expect(detail).toBe("email is required. password too short");
  });

  it("falls back when the body has no usable detail", () => {
    expect(extractDetail({ unexpected: true }, "fallback")).toBe("fallback");
    expect(extractDetail(null, "fallback")).toBe("fallback");
  });
});

describe("createApiClient", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("injects the bearer token and parses JSON", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { user_id: "u-1" }));
    vi.stubGlobal("fetch", fetchMock);
    const api = createApiClient({ getToken: () => "tok-123" });
    const result = await api.get<{ user_id: string }>("/iam/me");
    expect(result).toEqual({ user_id: "u-1" });
    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });

  it("throws ApiError with the backend detail and notifies on 401", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(401, { detail: "Not authenticated" }));
    vi.stubGlobal("fetch", fetchMock);
    const onUnauthorized = vi.fn();
    const api = createApiClient({ getToken: () => "stale", onUnauthorized });
    const failure = api.get("/iam/me").catch((err: unknown) => err);
    await expect(failure).resolves.toBeInstanceOf(ApiError);
    const err = (await failure) as ApiError;
    expect(err.status).toBe(401);
    expect(err.detail).toBe("Not authenticated");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});

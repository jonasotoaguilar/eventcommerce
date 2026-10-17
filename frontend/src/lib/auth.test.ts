import { describe, expect, it } from "vitest";
import { isTokenExpired } from "./auth";

function unsignedToken(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_");
  return `${encode({ alg: "none" })}.${encode(payload)}.sig`;
}

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

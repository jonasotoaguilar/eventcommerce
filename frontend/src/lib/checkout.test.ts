import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./api-client";
import { checkoutNavigation, newIdempotencyKey, placeCheckout } from "./checkout";

function stubApi() {
  const post = vi.fn(async () => null);
  const api = { post } as unknown as ApiClient;
  return { api, post };
}

describe("placeCheckout", () => {
  it("submits cart_id alone, never customer_id or inline fields", async () => {
    const { api, post } = stubApi();
    await placeCheckout(api, "cart-1", "key-1");
    expect(post).toHaveBeenCalledOnce();
    const [path, body] = post.mock.calls[0] as unknown as [string, Record<string, unknown>];
    expect(path).toBe("/checkout");
    expect(body).toEqual({ cart_id: "cart-1" });
    expect(body).not.toHaveProperty("customer_id");
    expect(body).not.toHaveProperty("items");
    expect(body).not.toHaveProperty("amount");
  });

  it("sends the attempt key on the Idempotency-Key header", async () => {
    const { api, post } = stubApi();
    await placeCheckout(api, "cart-1", "attempt-key-abc");
    const [, , init] = post.mock.calls[0] as unknown as [
      string,
      unknown,
      { headers: Record<string, string> },
    ];
    expect(init.headers["Idempotency-Key"]).toBe("attempt-key-abc");
  });
});

describe("newIdempotencyKey", () => {
  it("generates visible-ASCII keys within the 1-128 char bound", () => {
    for (let i = 0; i < 10; i += 1) {
      const key = newIdempotencyKey();
      expect(key.length).toBeGreaterThanOrEqual(1);
      expect(key.length).toBeLessThanOrEqual(128);
      expect(/^[\x21-\x7E]+$/.test(key)).toBe(true);
    }
  });

  it("generates a fresh key per place-order attempt", () => {
    const seen = new Set([newIdempotencyKey(), newIdempotencyKey(), newIdempotencyKey()]);
    expect(seen.size).toBe(3);
  });
});

describe("checkoutNavigation", () => {
  it("marks non-cancelled results for the success banner", () => {
    expect(
      checkoutNavigation({
        order_id: "o-1",
        status: "pending",
        cancel_reason: null,
        payment_status: null,
      }),
    ).toEqual({ justPlaced: true, checkoutCancelled: false, cancelReason: null });
  });

  it("suppresses success copy and carries the reason when cancelled", () => {
    expect(
      checkoutNavigation({
        order_id: "o-2",
        status: "cancelled",
        cancel_reason: "Payment declined",
        payment_status: null,
      }),
    ).toEqual({ justPlaced: false, checkoutCancelled: true, cancelReason: "Payment declined" });
  });
});

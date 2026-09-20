import type { ApiClient } from "./api-client";

/**
 * Cart-backed checkout over `POST /api/v1/checkout`.
 *
 * The body carries `cart_id` alone: lines, amounts, and ownership all
 * derive server-side (JWT subject is authoritative, so a `customer_id`
 * is never sent). Every place-order attempt generates its own
 * `Idempotency-Key` header (visible ASCII, 1-128 chars).
 */
export interface CheckoutResult {
  order_id: string;
  status: string;
  cancel_reason: string | null;
  payment_status: string | null;
}

/**
 * Generate one Idempotency-Key per place-order attempt. UUIDs are
 * visible ASCII and within the 1-128 char bound; the Math.random
 * fallback keeps the same alphabet when `crypto.randomUUID` is
 * unavailable.
 */
export function newIdempotencyKey(): string {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef && typeof cryptoRef.randomUUID === "function") {
    return cryptoRef.randomUUID();
  }
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let key = "";
  for (let i = 0; i < 32; i += 1) {
    key += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return key;
}

export interface CheckoutNavigation {
  /** Show the "Order placed" success banner on the tracker. */
  justPlaced: boolean;
  /** Show cancellation (not success) copy on the tracker. */
  checkoutCancelled: boolean;
  /** Cancellation reason to surface when cancelled at checkout. */
  cancelReason: string | null;
}

/**
 * Map a 201 checkout result to tracker navigation state. A `cancelled`
 * result must never present success copy: it suppresses `justPlaced`
 * and carries the reason for the cancellation banner instead. The
 * tracker itself still renders, so tracking stays available.
 */
export function checkoutNavigation(result: CheckoutResult): CheckoutNavigation {
  const cancelled = result.status === "cancelled";
  return {
    justPlaced: !cancelled,
    checkoutCancelled: cancelled,
    cancelReason: cancelled ? result.cancel_reason : null,
  };
}

/** Submit `{cart_id}` only, with the attempt key on the header. */
export function placeCheckout(
  api: ApiClient,
  cartId: string,
  idempotencyKey: string,
): Promise<CheckoutResult> {
  return api.post<CheckoutResult>(
    "/checkout",
    { cart_id: cartId },
    { headers: { "Idempotency-Key": idempotencyKey } },
  );
}

import { exclusiveEndOfDay } from "./operator";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "./api-client";
import {
  createOperatorApi,
  formatStockChange,
  isOperator,
  parseStockDelta,
  validateCancelReason,
  validateSimulationInput,
} from "./operator";
import { runPaymentSimulation } from "../pages/OperatorPaymentsPage";

function stubApi() {
  const get = vi.fn(async (): Promise<unknown> => null);
  const patch = vi.fn(async () => null);
  const post = vi.fn(async () => null);
  const api = { get, patch, post } as unknown as ApiClient;
  return { api, get, patch, post };
}

describe("isOperator", () => {
  it("accepts a user with the operator role", () => {
    expect(
      isOperator({
        user_id: "op-1",
        email: "op@example.com",
        role: "operator",
      }),
    ).toBe(true);
  });

  it("rejects a shopper", () => {
    expect(
      isOperator({
        user_id: "shop-1",
        email: "shop@example.com",
        role: "shopper",
      }),
    ).toBe(false);
  });

  it("rejects null", () => {
    expect(isOperator(null)).toBe(false);
  });
});

describe("createOperatorApi", () => {
  it("lists the order queue without a query string when no filters are given", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listOrders({});
    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith("/operator/orders");
  });

  it("sends every provided order filter as a query parameter", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listOrders({
      status: "confirmed",
      createdFrom: "2026-01-01T00:00:00Z",
      createdTo: "2026-02-01T00:00:00Z",
      limit: 50,
      offset: 10,
    });
    expect(get).toHaveBeenCalledWith(
      "/operator/orders?status=confirmed&created_from=2026-01-01T00%3A00%3A00Z&created_to=2026-02-01T00%3A00%3A00Z&limit=50&offset=10",
    );
  });

  it("omits absent order filters instead of sending empty values", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listOrders({ status: "pending", limit: 25 });
    expect(get).toHaveBeenCalledWith(
      "/operator/orders?status=pending&limit=25",
    );
  });

  it("URL-encodes order filter values", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listOrders({
      createdFrom: "2026-01-01T00:00:00+00:00",
    });
    expect(get).toHaveBeenCalledWith(
      "/operator/orders?created_from=2026-01-01T00%3A00%3A00%2B00%3A00",
    );
  });

  it("lists the catalog without a query string when no pagination is given", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listCatalog({});
    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith("/operator/catalog");
  });

  it("sends provided catalog pagination as query parameters", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).listCatalog({ limit: 20, offset: 40 });
    expect(get).toHaveBeenCalledWith("/operator/catalog?limit=20&offset=40");
  });

  it("sends every provided simulation input as a query parameter", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).simulatePayment({
      orderId: "order 1/x",
      amount: "12.50",
      currency: "USD",
    });
    expect(get).toHaveBeenCalledWith(
      "/operator/payments/simulation?order_id=order+1%2Fx&amount=12.50&currency=USD",
    );
  });

  it("omits absent simulation inputs instead of sending empty values", async () => {
    const { api, get } = stubApi();
    await createOperatorApi(api).simulatePayment({ currency: "USD" });
    expect(get).toHaveBeenCalledWith(
      "/operator/payments/simulation?currency=USD",
    );
  });

  it("propagates ApiError from the order queue read", async () => {
    const { api, get } = stubApi();
    const failure = new ApiError(403, "Operator role required.");
    get.mockRejectedValueOnce(failure);
    await expect(createOperatorApi(api).listOrders({})).rejects.toBe(failure);
  });

  it("propagates ApiError from the catalog read", async () => {
    const { api, get } = stubApi();
    const failure = new ApiError(403, "Operator role required.");
    get.mockRejectedValueOnce(failure);
    await expect(createOperatorApi(api).listCatalog({})).rejects.toBe(failure);
  });

  it("propagates ApiError from the payment simulation read", async () => {
    const { api, get } = stubApi();
    const failure = new ApiError(422, "Invalid simulation input.");
    get.mockRejectedValueOnce(failure);
    await expect(
      createOperatorApi(api).simulatePayment({ orderId: "order-1" }),
    ).rejects.toBe(failure);
  });
});

describe("updateProduct", () => {
  it("patches only the changed fields at the encoded product path", async () => {
    const { api, patch } = stubApi();
    await createOperatorApi(api).updateProduct("prod 1/x", {
      name: "New name",
      active: false,
    });
    expect(patch).toHaveBeenCalledOnce();
    expect(patch).toHaveBeenCalledWith("/catalog/prod%201%2Fx", {
      name: "New name",
      active: false,
    });
  });

  it("sends a full field set when every field changed", async () => {
    const { api, patch } = stubApi();
    await createOperatorApi(api).updateProduct("prod-1", {
      name: "New name",
      description: "New description",
      price: "12.50",
      currency: "USD",
      active: true,
    });
    expect(patch).toHaveBeenCalledWith("/catalog/prod-1", {
      name: "New name",
      description: "New description",
      price: "12.50",
      currency: "USD",
      active: true,
    });
  });

  it("propagates ApiError from the product write", async () => {
    const { api, patch } = stubApi();
    const failure = new ApiError(422, "Price must have at most 2 decimals");
    patch.mockRejectedValueOnce(failure);
    await expect(
      createOperatorApi(api).updateProduct("prod-1", { price: "12.505" }),
    ).rejects.toBe(failure);
  });
});

describe("adjustStock", () => {
  it("posts the delta to the encoded adjust path", async () => {
    const { api, post } = stubApi();
    await createOperatorApi(api).adjustStock("prod 1", 5);
    expect(post).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledWith("/inventory/prod%201/adjust", {
      delta: 5,
    });
  });

  it("posts negative deltas unchanged", async () => {
    const { api, post } = stubApi();
    await createOperatorApi(api).adjustStock("prod-1", -3);
    expect(post).toHaveBeenCalledWith("/inventory/prod-1/adjust", {
      delta: -3,
    });
  });

  it("propagates ApiError from the stock write", async () => {
    const { api, post } = stubApi();
    const failure = new ApiError(422, "Insufficient stock");
    post.mockRejectedValueOnce(failure);
    await expect(
      createOperatorApi(api).adjustStock("prod-1", -50),
    ).rejects.toBe(failure);
  });
});

describe("validateCancelReason", () => {
  it("accepts a valid reason and trims surrounding whitespace", () => {
    expect(validateCancelReason("  out of stock ")).toEqual({
      ok: true,
      reason: "out of stock",
    });
  });

  it("rejects an empty reason", () => {
    const result = validateCancelReason("   ");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/reason/i);
  });

  it("rejects a reason longer than 128 characters", () => {
    const result = validateCancelReason("r".repeat(129));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/128/);
  });

  it("accepts a reason of exactly 128 characters", () => {
    const reason = "r".repeat(128);
    expect(validateCancelReason(reason)).toEqual({ ok: true, reason });
  });
});

describe("confirmOrder", () => {
  it("posts to the encoded confirm path without a body", async () => {
    const { api, post } = stubApi();
    await createOperatorApi(api).confirmOrder("order 1/x");
    expect(post).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledWith("/orders/order%201%2Fx/confirm");
  });

  it("propagates ApiError from the confirm action", async () => {
    const { api, post } = stubApi();
    const failure = new ApiError(409, "Order cannot be confirmed.");
    post.mockRejectedValueOnce(failure);
    await expect(createOperatorApi(api).confirmOrder("order-1")).rejects.toBe(
      failure,
    );
  });
});

describe("cancelOrder", () => {
  it("posts the reason to the encoded cancel path", async () => {
    const { api, post } = stubApi();
    await createOperatorApi(api).cancelOrder("order 1/x", "out of stock");
    expect(post).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledWith("/orders/order%201%2Fx/cancel", {
      reason: "out of stock",
    });
  });

  it("propagates ApiError from the cancel action", async () => {
    const { api, post } = stubApi();
    const failure = new ApiError(409, "Order cannot be cancelled.");
    post.mockRejectedValueOnce(failure);
    await expect(
      createOperatorApi(api).cancelOrder("order-1", "out of stock"),
    ).rejects.toBe(failure);
  });
});

describe("parseStockDelta", () => {
  it("accepts a positive whole number", () => {
    expect(parseStockDelta("5")).toEqual({ ok: true, delta: 5 });
  });

  it("accepts a negative whole number with surrounding whitespace", () => {
    expect(parseStockDelta("  -3 ")).toEqual({ ok: true, delta: -3 });
  });

  it("rejects an empty input", () => {
    const result = parseStockDelta("   ");
    expect(result.ok).toBe(false);
  });

  it("rejects non-numeric input", () => {
    expect(parseStockDelta("abc").ok).toBe(false);
  });

  it("rejects decimals", () => {
    expect(parseStockDelta("2.5").ok).toBe(false);
  });

  it("rejects zero", () => {
    const result = parseStockDelta("0");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/non-zero/i);
  });
});

describe("formatStockChange", () => {
  it("renders a before-to-after record", () => {
    expect(formatStockChange(8, 13)).toBe("8 \u2192 13");
  });

  it("renders only the result when the previous quantity is unknown", () => {
    expect(formatStockChange(null, 5)).toBe("5");
  });
});

describe("validateSimulationInput", () => {
  const validOrderId = "123e4567-e89b-12d3-a456-426614174000";

  it("accepts a valid input and normalizes the currency to upper case", () => {
    expect(
      validateSimulationInput({
        orderId: validOrderId,
        amount: "12.50",
        currency: "usd",
      }),
    ).toEqual({
      ok: true,
      value: { orderId: validOrderId, amount: "12.50", currency: "USD" },
    });
  });

  it("rejects a malformed order id", () => {
    const result = validateSimulationInput({
      orderId: "not-a-uuid",
      amount: "12.50",
      currency: "USD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.orderId).toMatch(/uuid/i);
  });

  it("rejects a zero amount", () => {
    const result = validateSimulationInput({
      orderId: validOrderId,
      amount: "0",
      currency: "USD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.amount).toMatch(/greater than zero/i);
  });

  it("rejects a negative amount", () => {
    const result = validateSimulationInput({
      orderId: validOrderId,
      amount: "-5.00",
      currency: "USD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.amount).toMatch(/greater than zero/i);
  });

  it("rejects an amount above the delivered maximum", () => {
    const result = validateSimulationInput({
      orderId: validOrderId,
      amount: "1000000000",
      currency: "USD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.amount).toMatch(/999999999\.99/);
  });

  it("rejects an amount with more than two decimals", () => {
    const result = validateSimulationInput({
      orderId: validOrderId,
      amount: "12.505",
      currency: "USD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.amount).toMatch(/two decimal/i);
  });

  it("rejects a non-3-letter currency", () => {
    const result = validateSimulationInput({
      orderId: validOrderId,
      amount: "12.50",
      currency: "USDD",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.currency).toMatch(/three letters/i);
  });
});

describe("runPaymentSimulation", () => {
  const validOrderId = "123e4567-e89b-12d3-a456-426614174000";

  it("builds the simulation query the endpoint expects", async () => {
    const { api, get } = stubApi();
    get.mockResolvedValueOnce({
      order_id: validOrderId,
      amount: "12.50",
      currency: "USD",
      approved: true,
      digest_byte: 10,
      approval_threshold: 192,
    });
    await runPaymentSimulation(api, {
      orderId: validOrderId,
      amount: "12.50",
      currency: "usd",
    });
    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith(
      `/operator/payments/simulation?order_id=${validOrderId}&amount=12.50&currency=USD`,
    );
  });

  it("propagates ApiError from the simulation read", async () => {
    const { api, get } = stubApi();
    const failure = new ApiError(422, "Invalid simulation input.");
    get.mockRejectedValueOnce(failure);
    await expect(
      runPaymentSimulation(api, {
        orderId: validOrderId,
        amount: "12.50",
        currency: "USD",
      }),
    ).rejects.toBe(failure);
  });
});

describe("exclusiveEndOfDay", () => {
  it("maps a date input to the next midnight so the day stays included", () => {
    expect(exclusiveEndOfDay("2024-05-02")).toBe("2024-05-03T00:00:00");
  });

  it("rolls over at month and year boundaries", () => {
    expect(exclusiveEndOfDay("2024-05-31")).toBe("2024-06-01T00:00:00");
    expect(exclusiveEndOfDay("2024-12-31")).toBe("2025-01-01T00:00:00");
  });

  it("leaves an unusable value untouched", () => {
    expect(exclusiveEndOfDay("not-a-date")).toBe("not-a-date");
  });
});

import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "./api-client";
import {
  createOperatorApi,
  formatStockChange,
  isOperator,
  parseStockDelta,
} from "./operator";

function stubApi() {
  const get = vi.fn(async () => null);
  const patch = vi.fn(async () => null);
  const post = vi.fn(async () => null);
  const api = { get, patch, post } as unknown as ApiClient;
  return { api, get, patch, post };
}

describe("isOperator", () => {
  it("accepts a user with the operator role", () => {
    expect(
      isOperator({ user_id: "op-1", email: "op@example.com", role: "operator" }),
    ).toBe(true);
  });

  it("rejects a shopper", () => {
    expect(
      isOperator({ user_id: "shop-1", email: "shop@example.com", role: "shopper" }),
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
    expect(get).toHaveBeenCalledWith("/operator/orders?status=pending&limit=25");
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
    expect(get).toHaveBeenCalledWith("/operator/payments/simulation?currency=USD");
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
    expect(post).toHaveBeenCalledWith("/inventory/prod%201/adjust", { delta: 5 });
  });

  it("posts negative deltas unchanged", async () => {
    const { api, post } = stubApi();
    await createOperatorApi(api).adjustStock("prod-1", -3);
    expect(post).toHaveBeenCalledWith("/inventory/prod-1/adjust", { delta: -3 });
  });

  it("propagates ApiError from the stock write", async () => {
    const { api, post } = stubApi();
    const failure = new ApiError(422, "Insufficient stock");
    post.mockRejectedValueOnce(failure);
    await expect(createOperatorApi(api).adjustStock("prod-1", -50)).rejects.toBe(
      failure,
    );
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

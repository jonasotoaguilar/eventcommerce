import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "./api-client";
import { createOperatorApi, isOperator } from "./operator";

function stubApi() {
  const get = vi.fn(async () => null);
  const api = { get } as unknown as ApiClient;
  return { api, get };
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

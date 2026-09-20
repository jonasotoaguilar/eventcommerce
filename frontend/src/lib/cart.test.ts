import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./api-client";
import { createCartApi } from "./cart";

function stubApi() {
  const get = vi.fn(async () => null);
  const post = vi.fn(async () => null);
  const patch = vi.fn(async () => null);
  const del = vi.fn(async () => null);
  const api = { get, post, patch, del } as unknown as ApiClient;
  return { api, get, post, patch, del };
}

describe("createCartApi", () => {
  it("reads the owner-scoped cart without a request body", async () => {
    const { api, get } = stubApi();
    await createCartApi(api).get();
    expect(get).toHaveBeenCalledWith("/cart");
  });

  it("adds items with product_id/quantity and never customer_id", async () => {
    const { api, post } = stubApi();
    await createCartApi(api).add("prod-1", 2);
    expect(post).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledWith("/cart/items", { product_id: "prod-1", quantity: 2 });
  });

  it("sets an absolute quantity on the line endpoint", async () => {
    const { api, patch } = stubApi();
    await createCartApi(api).setQuantity("prod-1", 5);
    expect(patch).toHaveBeenCalledWith("/cart/items/prod-1", { quantity: 5 });
  });

  it("removes lines with an encoded id and no body", async () => {
    const { api, del } = stubApi();
    await createCartApi(api).remove("prod 1/x");
    expect(del).toHaveBeenCalledWith("/cart/items/prod%201%2Fx");
  });
});

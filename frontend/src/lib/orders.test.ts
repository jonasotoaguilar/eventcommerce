import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./api-client";
import { createOrdersApi } from "./orders";

function stubApi() {
  const get = vi.fn(async () => null);
  const api = { get } as unknown as ApiClient;
  return { api, get };
}

describe("createOrdersApi", () => {
  it("reads one order by encoded id", async () => {
    const { api, get } = stubApi();
    await createOrdersApi(api).get("order 1/x");
    expect(get).toHaveBeenCalledWith("/orders/order%201%2Fx");
  });

  it("reads the timeline under the order id", async () => {
    const { api, get } = stubApi();
    await createOrdersApi(api).timeline("order-1");
    expect(get).toHaveBeenCalledWith("/orders/order-1/timeline");
  });
});

import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./api-client";
import { createCatalogApi } from "./catalog";

function stubApi() {
  const get = vi.fn(async () => []);
  const api = { get } as unknown as ApiClient;
  return { api, get };
}

describe("createCatalogApi", () => {
  it("lists active products from the browse endpoint", async () => {
    const { api, get } = stubApi();
    await createCatalogApi(api).list();
    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith("/catalog");
  });

  it("encodes the product id in the detail path", async () => {
    const { api, get } = stubApi();
    await createCatalogApi(api).get("prod 1/x");
    expect(get).toHaveBeenCalledWith("/catalog/prod%201%2Fx");
  });
});

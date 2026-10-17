import type { ApiClient } from "./api-client";

/**
 * Shopper catalog over the public browse contract:
 * GET /api/v1/catalog      -> Product[] (active products only)
 * GET /api/v1/catalog/{id} -> Product (404 when missing or inactive)
 *
 * Decimal money (`price`) serializes as a JSON number or string, so it
 * stays `number | string` until display formatting (see lib/money.ts).
 */
export interface Product {
  id: string;
  name: string;
  description: string | null;
  price: number | string;
  currency: string;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export function createCatalogApi(api: ApiClient) {
  return {
    /** List active products. Public; works with or without a session. */
    list(): Promise<Product[]> {
      return api.get<Product[]>("/catalog");
    },
    /** Fetch one product. Rejects with 404 ApiError when unavailable. */
    get(productId: string): Promise<Product> {
      return api.get<Product>(`/catalog/${encodeURIComponent(productId)}`);
    },
  };
}

export type CatalogApi = ReturnType<typeof createCatalogApi>;

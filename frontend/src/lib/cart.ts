import type { ApiClient } from "./api-client";

/**
 * Shopper cart over the owner-scoped contract:
 * GET   /api/v1/cart                  -> Cart (requires auth, lazy-creates)
 * POST  /api/v1/cart/items            -> Cart ({product_id, quantity} increments)
 * PATCH /api/v1/cart/items/{id}       -> Cart ({quantity} sets absolute)
 * DELETE /api/v1/cart/items/{id}      -> Cart (removes the line)
 *
 * Ownership always comes from the JWT subject: request bodies never
 * carry a `customer_id`. Decimal money (`unit_price`, `line_total`,
 * `subtotal`) serializes as a JSON number or string, so those fields
 * stay `number | string` until display formatting (see lib/money.ts).
 */
export interface CartLine {
  product_id: string;
  name: string;
  quantity: number;
  unit_price: number | string;
  currency: string;
  line_total: number | string;
}

export interface Cart {
  cart_id: string;
  customer_id: string;
  items: CartLine[];
  subtotal: number | string;
  currency: string | null;
}

export function createCartApi(api: ApiClient) {
  return {
    /** Read (or lazily create) the shopper's cart. Requires auth. */
    get(): Promise<Cart> {
      return api.get<Cart>("/cart");
    },
    /** Add a line, incrementing when the product is already present. */
    add(productId: string, quantity: number): Promise<Cart> {
      return api.post<Cart>("/cart/items", { product_id: productId, quantity });
    },
    /** Set a line to an absolute quantity. 404 when the line is missing. */
    setQuantity(productId: string, quantity: number): Promise<Cart> {
      return api.patch<Cart>(`/cart/items/${encodeURIComponent(productId)}`, {
        quantity,
      });
    },
    /** Remove a line idempotently; always resolves with the cart. */
    remove(productId: string): Promise<Cart> {
      return api.del<Cart>(`/cart/items/${encodeURIComponent(productId)}`);
    },
  };
}

export type CartApi = ReturnType<typeof createCartApi>;

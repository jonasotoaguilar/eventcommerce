import type { ApiClient } from "./api-client";
import type { SessionUser } from "./auth";
import type { OrderStatus } from "./order-status";

/**
 * Operator reads over the dedicated read model:
 * GET /api/v1/operator/orders              -> queue rows with payment-derived totals
 * GET /api/v1/operator/catalog             -> products including inactive, with stock
 * GET /api/v1/operator/payments/simulation -> deterministic decision for the inputs
 *
 * Decimal money (`total`, `price`, `amount`) serializes as a JSON string,
 * so it stays `string` until display formatting (see lib/money.ts).
 */
export interface OperatorOrderRow {
  order_id: string;
  customer_id: string;
  status: OrderStatus;
  created_at: string;
  cancel_reason: string | null;
  item_count: number;
  total: string | null;
  currency: string | null;
}

export interface OperatorCatalogRow {
  product_id: string;
  name: string;
  description: string | null;
  price: number | string;
  currency: string;
  active: boolean;
  available_quantity: number | null;
  reserved_quantity: number | null;
}

export interface PaymentSimulation {
  order_id: string;
  amount: string;
  currency: string;
  approved: boolean;
  digest_byte: number;
  approval_threshold: number;
}

export interface OperatorOrderFilters {
  status?: OrderStatus;
  createdFrom?: string;
  createdTo?: string;
  limit?: number;
  offset?: number;
}

export interface OperatorPagination {
  limit?: number;
  offset?: number;
}

/**
 * Partial product edit. The caller passes only the fields that changed
 * (mirrors `ProductUpdateRequest`: every field optional); the helper
 * forwards them untouched so a PATCH never rewrites unchanged values.
 */
export interface ProductUpdateChanges {
  name?: string;
  description?: string | null;
  price?: number | string;
  currency?: string;
  active?: boolean;
}

/** Product shape returned by `PATCH /api/v1/catalog/{product_id}`. */
export interface UpdatedProduct {
  id: string;
  name: string;
  description: string | null;
  price: number | string;
  currency: string;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** Stock shape returned by `POST /api/v1/inventory/{product_id}/adjust`. */
export interface StockAdjustResponse {
  product_id: string;
  available_quantity: number;
  reserved_quantity: number;
}

export type ParsedStockDelta =
  | { ok: true; delta: number }
  | { ok: false; error: string };

/**
 * Validate a stock delta typed by an operator. Only non-zero whole
 * numbers reach the backend; zero and fractional input cannot express
 * an inventory adjustment, so they fail here instead of round-tripping
 * to a 422.
 */
export function parseStockDelta(raw: string): ParsedStockDelta {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return { ok: false, error: "Enter a whole number." };
  if (!/^[+-]?\d+$/.test(trimmed))
    return { ok: false, error: "Enter a whole number (no decimals)." };
  const delta = Number(trimmed);
  if (!Number.isSafeInteger(delta))
    return { ok: false, error: "Enter a smaller whole number." };
  if (delta === 0)
    return { ok: false, error: "Enter a non-zero whole number." };
  return { ok: true, delta };
}

/**
 * Render the stock record kept after a successful adjust. Unknown
 * previous quantities (untracked stock) render as the bare result.
 */
export function formatStockChange(before: number | null, after: number): string {
  return before === null ? `${after}` : `${before} \u2192 ${after}`;
}

export interface SimulatePaymentInput {
  orderId?: string;
  amount?: string;
  currency?: string;
}

/** Single role predicate: only JWT subjects with the operator role qualify. */
export function isOperator(user: SessionUser | null | undefined): boolean {
  return user?.role === "operator";
}

/**
 * Render query parameters, leaving out anything the caller did not
 * provide so the backend never receives an empty value for an absent
 * filter. Values are URL-encoded by URLSearchParams.
 */
function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.append(key, String(value));
  }
  const query = search.toString();
  return query.length > 0 ? `?${query}` : "";
}

export function createOperatorApi(api: ApiClient) {
  return {
    /** List the order queue. Filters map to `status`/`created_from`/`created_to`. */
    listOrders(filters: OperatorOrderFilters = {}): Promise<OperatorOrderRow[]> {
      const query = buildQuery({
        status: filters.status,
        created_from: filters.createdFrom,
        created_to: filters.createdTo,
        limit: filters.limit,
        offset: filters.offset,
      });
      return api.get<OperatorOrderRow[]>(`/operator/orders${query}`);
    },
    /** List catalog products including inactive ones, with stock joined in. */
    listCatalog(pagination: OperatorPagination = {}): Promise<OperatorCatalogRow[]> {
      const query = buildQuery({ limit: pagination.limit, offset: pagination.offset });
      return api.get<OperatorCatalogRow[]>(`/operator/catalog${query}`);
    },
    /** Inspect the deterministic payment decision for the given inputs. */
    simulatePayment(input: SimulatePaymentInput): Promise<PaymentSimulation> {
      const query = buildQuery({
        order_id: input.orderId,
        amount: input.amount,
        currency: input.currency,
      });
      return api.get<PaymentSimulation>(`/operator/payments/simulation${query}`);
    },
    /**
     * Edit a product through the delivered operator route. `changes`
     * carries only the fields that changed; the backend PATCH accepts
     * exactly this partial shape.
     */
    updateProduct(
      productId: string,
      changes: ProductUpdateChanges,
    ): Promise<UpdatedProduct> {
      return api.patch<UpdatedProduct>(
        `/catalog/${encodeURIComponent(productId)}`,
        changes,
      );
    },
    /** Apply an operator-signed delta through the delivered adjust route. */
    adjustStock(productId: string, delta: number): Promise<StockAdjustResponse> {
      return api.post<StockAdjustResponse>(
        `/inventory/${encodeURIComponent(productId)}/adjust`,
        { delta },
      );
    },
  };
}

export type OperatorApi = ReturnType<typeof createOperatorApi>;

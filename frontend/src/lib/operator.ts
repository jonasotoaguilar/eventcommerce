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
  };
}

export type OperatorApi = ReturnType<typeof createOperatorApi>;

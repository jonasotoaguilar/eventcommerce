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

/** Order shape returned by `POST /api/v1/orders/{order_id}/confirm`. */
export interface ConfirmedOrder {
  order_id: string;
  status: string;
}

/** Order shape returned by `POST /api/v1/orders/{order_id}/cancel`. */
export interface CancelledOrder {
  order_id: string;
  status: string;
  cancel_reason: string | null;
}

/** Backend bound for the cancel reason (`OrderCancelRequest`). */
export const MAX_CANCEL_REASON_LENGTH = 128;

export type ValidatedCancelReason =
  { ok: true; reason: string } | { ok: false; error: string };

/**
 * Validate a cancel reason typed by an operator. Empty and over-long
 * reasons fail here instead of round-tripping to a 422.
 */
export function validateCancelReason(raw: string): ValidatedCancelReason {
  const reason = raw.trim();
  if (reason.length === 0)
    return { ok: false, error: "Enter a cancel reason." };
  if (reason.length > MAX_CANCEL_REASON_LENGTH)
    return {
      ok: false,
      error: `Keep the reason to ${MAX_CANCEL_REASON_LENGTH} characters or fewer.`,
    };
  return { ok: true, reason };
}

export type ParsedStockDelta =
  { ok: true; delta: number } | { ok: false; error: string };

/**
 * Validate a stock delta typed by an operator. Only non-zero whole
 * numbers reach the backend; zero and fractional input cannot express
 * an inventory adjustment, so they fail here instead of round-tripping
 * to a 422.
 */
export function parseStockDelta(raw: string): ParsedStockDelta {
  const trimmed = raw.trim();
  if (trimmed.length === 0)
    return { ok: false, error: "Enter a whole number." };
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
export function formatStockChange(
  before: number | null,
  after: number,
): string {
  return before === null ? `${after}` : `${before} \u2192 ${after}`;
}

export interface SimulatePaymentInput {
  orderId?: string;
  amount?: string;
  currency?: string;
}

/** Delivered checkout ceiling mirrored by the simulation read (`MAX_AMOUNT`). */
export const MAX_SIMULATION_AMOUNT = "999999999.99";

const SIMULATION_MAX_CENTS = 99999999999n;
const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const SIMULATION_AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;
const SIMULATION_CURRENCY_PATTERN = /^[A-Za-z]{3}$/;

export interface ValidSimulationInput {
  orderId: string;
  amount: string;
  currency: string;
}

export interface SimulationInputErrors {
  orderId?: string;
  amount?: string;
  currency?: string;
}

export type ValidatedSimulationInput =
  | { ok: true; value: ValidSimulationInput }
  | { ok: false; errors: SimulationInputErrors };

/** Cents of a validated `intPart.fracPart` decimal, exact for any size. */
function decimalToCents(intPart: string, fracPart: string): bigint {
  return BigInt(intPart) * 100n + BigInt(fracPart.padEnd(2, "0"));
}

/**
 * Mirror the simulation endpoint's query rules before any request:
 * UUID order id, positive amount with at most two decimals within the
 * delivered maximum, and a three-letter currency normalized to upper
 * case. Failures stay local instead of round-tripping to a 422.
 */
export function validateSimulationInput(
  raw: SimulatePaymentInput,
): ValidatedSimulationInput {
  const errors: SimulationInputErrors = {};

  const orderId = (raw.orderId ?? "").trim();
  if (!UUID_PATTERN.test(orderId))
    errors.orderId = "Enter the order id as a UUID.";

  const amount = (raw.amount ?? "").trim();
  if (!SIMULATION_AMOUNT_PATTERN.test(amount)) {
    errors.amount =
      amount.startsWith("-") || amount === "0" || amount === "0.00"
        ? "Enter an amount greater than zero."
        : "Enter a positive amount with at most two decimal places.";
  } else {
    const dot = amount.indexOf(".");
    const cents = decimalToCents(
      dot === -1 ? amount : amount.slice(0, dot),
      dot === -1 ? "" : amount.slice(dot + 1),
    );
    if (cents <= 0n) errors.amount = "Enter an amount greater than zero.";
    else if (cents > SIMULATION_MAX_CENTS)
      errors.amount = `Enter an amount of ${MAX_SIMULATION_AMOUNT} or less.`;
  }

  const currency = (raw.currency ?? "").trim();
  if (!SIMULATION_CURRENCY_PATTERN.test(currency))
    errors.currency = "Enter a currency of exactly three letters.";

  if (errors.orderId !== undefined || errors.amount !== undefined || errors.currency !== undefined)
    return { ok: false, errors };
  return {
    ok: true,
    value: { orderId, amount, currency: currency.toUpperCase() },
  };
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
function buildQuery(
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.append(key, String(value));
  }
  const query = search.toString();
  return query.length > 0 ? `?${query}` : "";
}

/**
 * The queue's `created_to` is exclusive, so a date input has to resolve to the
 * following day's midnight; otherwise the selected end day filters itself out.
 */
export function exclusiveEndOfDay(date: string): string {
  const parts = date.split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
    return date;
  }
  const [year, month, day] = parts;
  const next = new Date(Date.UTC(year, month - 1, day + 1));
  return `${next.toISOString().slice(0, 10)}T00:00:00`;
}

export function createOperatorApi(api: ApiClient) {
  return {
    /** List the order queue. Filters map to `status`/`created_from`/`created_to`. */
    listOrders(
      filters: OperatorOrderFilters = {},
    ): Promise<OperatorOrderRow[]> {
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
    listCatalog(
      pagination: OperatorPagination = {},
    ): Promise<OperatorCatalogRow[]> {
      const query = buildQuery({
        limit: pagination.limit,
        offset: pagination.offset,
      });
      return api.get<OperatorCatalogRow[]>(`/operator/catalog${query}`);
    },
    /** Inspect the deterministic payment decision for the given inputs. */
    simulatePayment(input: SimulatePaymentInput): Promise<PaymentSimulation> {
      const query = buildQuery({
        order_id: input.orderId,
        amount: input.amount,
        currency: input.currency,
      });
      return api.get<PaymentSimulation>(
        `/operator/payments/simulation${query}`,
      );
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
    adjustStock(
      productId: string,
      delta: number,
    ): Promise<StockAdjustResponse> {
      return api.post<StockAdjustResponse>(
        `/inventory/${encodeURIComponent(productId)}/adjust`,
        { delta },
      );
    },
    /** Confirm a payment-authorized order through the delivered route. */
    confirmOrder(orderId: string): Promise<ConfirmedOrder> {
      return api.post<ConfirmedOrder>(
        `/orders/${encodeURIComponent(orderId)}/confirm`,
      );
    },
    /** Cancel an order with a validated reason through the delivered route. */
    cancelOrder(orderId: string, reason: string): Promise<CancelledOrder> {
      return api.post<CancelledOrder>(
        `/orders/${encodeURIComponent(orderId)}/cancel`,
        { reason },
      );
    },
  };
}

export type OperatorApi = ReturnType<typeof createOperatorApi>;

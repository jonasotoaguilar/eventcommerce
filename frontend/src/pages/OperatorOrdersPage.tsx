import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/session";
import { OperatorOrderRow } from "../components/OperatorOrderRow";
import { ORDER_STATUSES, type OrderStatus } from "../lib/order-status";
import {
  createOperatorApi,
  exclusiveEndOfDay,
  type CancelledOrder,
  type ConfirmedOrder,
  type OperatorOrderRow as OperatorOrder,
} from "../lib/operator";

type OrdersScreenState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: OperatorOrder[] };

type StatusFilter = OrderStatus | "all";

const PAGE_SIZE = 20;

/**
 * Operator order queue over the read model, with status and date
 * filters and limit/offset pagination. The queue refreshes on demand
 * after filters, paging, or a successful action; nothing here claims
 * live updates.
 */
export function OperatorOrdersPage() {
  const { api } = useAuth();
  const [state, setState] = useState<OrdersScreenState>({ kind: "loading" });
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const rows = await createOperatorApi(api).listOrders({
        ...(statusFilter === "all" ? {} : { status: statusFilter }),
        ...(createdFrom === "" ? {} : { createdFrom }),
        ...(createdTo === ""
          ? {}
          : { createdTo: exclusiveEndOfDay(createdTo) }),
        limit: PAGE_SIZE,
        offset,
      });
      setState({ kind: "ready", rows });
    } catch (err) {
      setState({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Could not load the queue.",
      });
    }
  }, [api, statusFilter, createdFrom, createdTo, offset, attempt]);

  useEffect(() => {
    void load();
  }, [load]);

  function retry() {
    setAttempt((count) => count + 1);
  }

  function applyFilters(status: StatusFilter, from: string, to: string) {
    setStatusFilter(status);
    setCreatedFrom(from);
    setCreatedTo(to);
    setOffset(0);
    setNotice(null);
  }

  async function handleConfirm(orderId: string): Promise<ConfirmedOrder> {
    const confirmed = await createOperatorApi(api).confirmOrder(orderId);
    setNotice(`Order ${confirmed.order_id} confirmed.`);
    setAttempt((count) => count + 1);
    return confirmed;
  }

  async function handleCancel(
    orderId: string,
    reason: string,
  ): Promise<CancelledOrder> {
    const cancelled = await createOperatorApi(api).cancelOrder(orderId, reason);
    setNotice(`Order ${cancelled.order_id} cancelled.`);
    setAttempt((count) => count + 1);
    return cancelled;
  }

  const ready = state.kind === "ready" ? state.rows : null;
  const hasNext = ready !== null && ready.length >= PAGE_SIZE;

  return (
    <section aria-labelledby="operator-orders-title">
      <h1 id="operator-orders-title">Operator orders</h1>

      <form
        className="operator-edit-form"
        aria-label="Order queue filters"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="field">
          <label htmlFor="operator-orders-status">Status</label>
          <select
            id="operator-orders-status"
            name="operator-orders-status"
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value as StatusFilter;
              setStatusFilter(next);
              setOffset(0);
              setNotice(null);
            }}
          >
            <option value="all">All</option>
            {ORDER_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="operator-orders-from">Created from</label>
          <input
            id="operator-orders-from"
            name="operator-orders-from"
            type="date"
            value={createdFrom}
            onChange={(event) => {
              setCreatedFrom(event.target.value);
              setOffset(0);
              setNotice(null);
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="operator-orders-to">Created to</label>
          <input
            id="operator-orders-to"
            name="operator-orders-to"
            type="date"
            value={createdTo}
            onChange={(event) => {
              setCreatedTo(event.target.value);
              setOffset(0);
              setNotice(null);
            }}
          />
        </div>
        <p className="cta-row">
          <button
            type="button"
            className="button button-secondary"
            onClick={() => applyFilters("all", "", "")}
          >
            Clear filters
          </button>
          <button
            type="button"
            className="button button-secondary"
            onClick={retry}
          >
            Refresh queue
          </button>
        </p>
      </form>
      <p className="hint">
        The queue refreshes on demand; it does not update live.
      </p>

      <div aria-live="polite">
        {notice !== null && state.kind === "ready" && (
          <p className="alert alert-success" role="status">
            {notice}
          </p>
        )}
        {ready !== null && (
          <p className="hint" role="status">
            {ready.length === 0
              ? "No orders match the current filters."
              : `Showing ${ready.length} order${ready.length === 1 ? "" : "s"}.`}
          </p>
        )}
      </div>

      {state.kind === "loading" && (
        <div role="status" aria-live="polite">
          <p>Loading queue\u2026</p>
          <ul className="operator-skeleton-list" aria-hidden="true">
            {Array.from({ length: 3 }, (_, index) => (
              <li key={index} className="product-card skeleton">
                Loading\u2026
              </li>
            ))}
          </ul>
        </div>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">Fetch error: {state.message}</p>
          <button
            type="button"
            className="button button-primary"
            onClick={retry}
          >
            Retry
          </button>
        </div>
      )}

      {ready !== null &&
        (ready.length === 0 ? (
          <div role="status">
            <p>No orders</p>
          </div>
        ) : (
          <>
            <div className="operator-table-wrap">
              <table className="operator-table">
                <caption className="visually-hidden">
                  Order queue with customer, total, status, and actions
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Order</th>
                    <th scope="col">Customer</th>
                    <th scope="col">Total</th>
                    <th scope="col">Status</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {ready.map((order) => (
                    <OperatorOrderRow
                      key={order.order_id}
                      order={order}
                      onConfirm={handleConfirm}
                      onCancel={handleCancel}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <nav aria-label="Order queue pages">
              <p className="cta-row">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={offset === 0}
                  aria-disabled={offset === 0}
                  onClick={() =>
                    setOffset((current) => Math.max(0, current - PAGE_SIZE))
                  }
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={!hasNext}
                  aria-disabled={!hasNext}
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                >
                  Next
                </button>
              </p>
            </nav>
          </>
        ))}
    </section>
  );
}

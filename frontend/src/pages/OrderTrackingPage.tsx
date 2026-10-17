import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../auth/session";
import { OrderTimeline } from "../components/OrderTimeline";
import { StatusBadge } from "../components/StatusBadge";
import { ApiError } from "../lib/api-client";
import { isTerminalStatus, statusDescription } from "../lib/order-status";
import { createOrdersApi, type Order, type TimelineEvent } from "../lib/orders";

type TrackingState =
  | { kind: "loading" }
  | { kind: "error"; message: string; showCatalogLink: boolean }
  | { kind: "ready"; order: Order; events: TimelineEvent[] };

function trackingError(err: unknown): { message: string; showCatalogLink: boolean } {
  if (err instanceof ApiError && err.status === 404) {
    return {
      message: "Order not found. It may belong to another account, or the link is wrong.",
      showCatalogLink: true,
    };
  }
  return {
    message: err instanceof Error ? err.message : "Could not load the order.",
    showCatalogLink: false,
  };
}

/**
 * Authenticated order tracking at `/orders/:id` (route-guarded by
 * <ProtectedRoute>). Shows the exact status vocabulary, the
 * cancellation reason when cancelled, order lines, and the
 * chronological timeline. Progress is async on the server: the page
 * never claims live updates and offers an honest manual refresh.
 * Status changes announce through a polite live region.
 */
interface TrackerNavState {
  justPlaced?: boolean;
  checkoutCancelled?: boolean;
  cancelReason?: string | null;
}

export function OrderTrackingPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navState = location.state as TrackerNavState | null;
  const justPlaced = navState?.justPlaced === true;
  const checkoutCancelled = navState?.checkoutCancelled === true;
  const checkoutCancelReason =
    typeof navState?.cancelReason === "string" ? navState.cancelReason : null;
  const { api } = useAuth();
  const [state, setState] = useState<TrackingState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const snapshotRef = useRef<{ order: Order; events: TimelineEvent[] } | null>(null);

  const load = useCallback(
    async (isRefresh: boolean) => {
      if (id === undefined || id.length === 0) {
        setState({
          kind: "error",
          message: "Order not found. It may belong to another account, or the link is wrong.",
          showCatalogLink: true,
        });
        return;
      }
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setState({ kind: "loading" });
      }
      try {
        const orders = createOrdersApi(api);
        const [order, events] = await Promise.all([orders.get(id), orders.timeline(id)]);
        snapshotRef.current = { order, events };
        setState({ kind: "ready", order, events });
        if (isRefresh) setRefreshError(null);
      } catch (err) {
        const failure = trackingError(err);
        // A failed refresh preserves the last good snapshot and
        // reports the failure next to the refresh control; a failed
        // first load has nothing to keep, so it shows the error.
        if (isRefresh && snapshotRef.current !== null) {
          setRefreshError(failure.message);
        } else {
          setState({
            kind: "error",
            message: failure.message,
            showCatalogLink: failure.showCatalogLink,
          });
        }
      } finally {
        if (isRefresh) setRefreshing(false);
      }
    },
    [api, id],
  );

  // Fresh id, fresh load; refreshes keep the snapshot on screen.
  useEffect(() => {
    snapshotRef.current = null;
    setRefreshError(null);
    setRefreshNonce(0);
  }, [id]);

  // Reason for the checkout-cancelled banner: prefer the checkout
  // result, fall back to the fetched order once it is loaded.
  const cancelledReason =
    checkoutCancelReason ?? (state.kind === "ready" ? state.order.cancel_reason : null);
  useEffect(() => {
    void load(refreshNonce > 0);
  }, [load, refreshNonce]);

  return (
    <section aria-labelledby="order-tracking-title">
      <h1 id="order-tracking-title">Order tracking</h1>

      {justPlaced &&
        !checkoutCancelled &&
        state.kind !== "loading" &&
        !(state.kind === "ready" && state.order.status === "cancelled") && (
          <p className="alert alert-success" role="status">
            Order placed. Track its progress below.
          </p>
        )}

      {(checkoutCancelled ||
        (justPlaced && state.kind === "ready" && state.order.status === "cancelled")) &&
        state.kind !== "loading" && (
          <p className="alert alert-error" role="alert">
            The order was cancelled{cancelledReason ? `: ${cancelledReason}.` : "."} Tracking is
            shown below.
          </p>
        )}

      {state.kind === "loading" && (
        <p role="status" aria-live="polite">
          Loading your order…
        </p>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">{state.message}</p>
          <div className="cta-row">
            <button
              type="button"
              className="button button-primary"
              onClick={() => setRefreshNonce((nonce) => nonce + 1)}
            >
              Retry
            </button>
            {state.showCatalogLink && (
              <Link className="button button-secondary" to="/catalog">
                Browse the catalog
              </Link>
            )}
          </div>
        </div>
      )}

      {state.kind === "ready" && (
        <>
          <p className="order-id">
            Order <code>{state.order.order_id}</code>
          </p>
          <div aria-live="polite">
            <StatusBadge status={state.order.status} />
            <p className="hint">{statusDescription(state.order.status)}</p>
          </div>

          {state.order.status === "cancelled" && (
            <p className="alert alert-error" role="status">
              {state.order.cancel_reason
                ? `Cancellation reason: ${state.order.cancel_reason}`
                : "No cancellation reason was provided."}
            </p>
          )}

          {!isTerminalStatus(state.order.status) && (
            <p className="notice" role="status">
              This order can still change as it moves through the next steps. Refresh to check
              again.
            </p>
          )}

          <h2>Items</h2>
          {state.order.items.length === 0 ? (
            <p role="status">This order has no items.</p>
          ) : (
            <ul className="order-items">
              {state.order.items.map((item) => (
                <li key={item.product_id}>
                  <code>{item.product_id}</code> × {item.quantity}
                </li>
              ))}
            </ul>
          )}

          <h2>Timeline</h2>
          <OrderTimeline events={state.events} />

          <div className="refresh-row">
            {refreshError !== null && (
              <p className="alert alert-error" role="alert">
                Could not refresh: {refreshError} Showing the last loaded status — try Refresh
                again.
              </p>
            )}
            <button
              type="button"
              className="button button-secondary"
              disabled={refreshing}
              aria-disabled={refreshing}
              aria-busy={refreshing}
              onClick={() => setRefreshNonce((nonce) => nonce + 1)}
            >
              {refreshing ? "Refreshing…" : "Refresh status"}
            </button>
            <p className="hint" role="note">
              Order progress happens on the server; this page does not update automatically. Use
              Refresh to check again.
            </p>
          </div>

          <p className="cta-row">
            <Link className="button button-secondary" to="/catalog">
              Back to catalog
            </Link>
            <Link className="button button-secondary" to="/cart">
              View cart
            </Link>
          </p>
        </>
      )}
    </section>
  );
}

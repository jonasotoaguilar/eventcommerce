import { useState } from "react";
import { formatMoney } from "../lib/money";
import {
  validateCancelReason,
  type CancelledOrder,
  type ConfirmedOrder,
  type OperatorOrderRow as OperatorOrder,
} from "../lib/operator";
import { StatusBadge } from "./StatusBadge";

interface OperatorOrderRowProps {
  order: OperatorOrder;
  onConfirm: (orderId: string) => Promise<ConfirmedOrder>;
  onCancel: (orderId: string, reason: string) => Promise<CancelledOrder>;
}

type InFlight = { kind: "confirm" } | { kind: "cancel" } | null;

/**
 * One operator queue row: order id, customer, payment-derived total,
 * status badge, and confirm/cancel actions. Cancel collects a reason
 * first and validates it locally; action failures stay inline so the
 * row never loses its place in the queue.
 */
export function OperatorOrderRow({ order, onConfirm, onCancel }: OperatorOrderRowProps) {
  const [inFlight, setInFlight] = useState<InFlight>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const busy = inFlight !== null;
  const reasonId = `cancel-reason-${order.order_id}`;

  async function confirm() {
    setActionError(null);
    setInFlight({ kind: "confirm" });
    try {
      await onConfirm(order.order_id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not confirm the order.");
    } finally {
      setInFlight(null);
    }
  }

  async function submitCancel() {
    const validated = validateCancelReason(reason);
    if (!validated.ok) {
      setReasonError(validated.error);
      return;
    }
    setReasonError(null);
    setActionError(null);
    setInFlight({ kind: "cancel" });
    try {
      await onCancel(order.order_id, validated.reason);
      setCancelOpen(false);
      setReason("");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel the order.");
    } finally {
      setInFlight(null);
    }
  }

  const total = order.total === null ? "\u2014" : formatMoney(order.total, order.currency);

  return (
    <tr>
      <th scope="row" className="operator-cell-product">
        {order.order_id}
        <span className="product-description">
          {order.item_count} item{order.item_count === 1 ? "" : "s"}
        </span>
      </th>
      <td>{order.customer_id}</td>
      <td>{total}</td>
      <td>
        <StatusBadge status={order.status} />
      </td>
      <td>
        {actionError !== null && (
          <p className="alert alert-error" role="alert">
            {actionError}
          </p>
        )}
        <p className="cta-row">
          <button
            type="button"
            className="button button-primary"
            disabled={busy}
            aria-disabled={busy}
            aria-busy={inFlight?.kind === "confirm"}
            onClick={confirm}
          >
            {inFlight?.kind === "confirm" ? "Confirming\u2026" : "Confirm"}
          </button>
          <button
            type="button"
            className="button button-secondary"
            disabled={busy}
            aria-disabled={busy}
            aria-busy={inFlight?.kind === "cancel"}
            aria-expanded={cancelOpen}
            onClick={() => {
              setReasonError(null);
              setCancelOpen((open) => !open);
            }}
          >
            Cancel order
          </button>
        </p>
        {cancelOpen && (
          <form
            className="operator-edit-form"
            aria-label={`Cancel reason for order ${order.order_id}`}
            onSubmit={(event) => {
              event.preventDefault();
              void submitCancel();
            }}
          >
            <div className="field">
              <label htmlFor={reasonId}>Cancel reason</label>
              <input
                id={reasonId}
                name={reasonId}
                value={reason}
                maxLength={128}
                onChange={(event) => setReason(event.target.value)}
                disabled={busy}
                aria-disabled={busy}
                aria-describedby={`${reasonId}-hint`}
                required
              />
              <p className="hint" id={`${reasonId}-hint`}>
                Required, up to 128 characters.
              </p>
            </div>
            {reasonError !== null && (
              <p className="alert alert-error" role="alert">
                {reasonError}
              </p>
            )}
            <p className="cta-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                aria-disabled={busy}
                aria-busy={inFlight?.kind === "cancel"}
                onClick={submitCancel}
              >
                {inFlight?.kind === "cancel" ? "Cancelling\u2026" : "Submit cancellation"}
              </button>
              <button
                type="button"
                className="button button-secondary"
                disabled={busy}
                aria-disabled={busy}
                onClick={() => setCancelOpen(false)}
              >
                Back
              </button>
            </p>
          </form>
        )}
      </td>
    </tr>
  );
}

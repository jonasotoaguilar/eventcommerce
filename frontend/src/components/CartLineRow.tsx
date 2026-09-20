import { useState } from "react";
import type { CartLine } from "../lib/cart";
import { formatMoney } from "../lib/money";

export type CartLineBusy = "updating" | "removing" | undefined;

interface CartLineProps {
  line: CartLine;
  busy: CartLineBusy;
  onSetQuantity: (productId: string, quantity: number) => void;
  onRemove: (productId: string) => void;
}

/**
 * One cart row: line name, unit price, editable quantity, line total,
 * and remove. Quantity edits set an absolute value (PATCH); every
 * control disables while its line is in flight. The parent remounts the
 * row (key on product + quantity) after each server round-trip so the
 * draft always starts from the confirmed quantity.
 */
export function CartLineRow({ line, busy, onSetQuantity, onRemove }: CartLineProps) {
  const inputId = `cart-qty-${line.product_id}`;
  const [draft, setDraft] = useState(line.quantity);
  const inFlight = busy !== undefined;
  const unchanged = draft === line.quantity;

  function commit() {
    if (!Number.isInteger(draft) || draft < 1 || draft > 10_000) return;
    if (unchanged) return;
    onSetQuantity(line.product_id, draft);
  }

  return (
    <li className="cart-line">
      <div className="cart-line-info">
        <h2 className="cart-line-name">{line.name}</h2>
        <p className="cart-line-meta">{formatMoney(line.unit_price, line.currency)} each</p>
      </div>
      <div className="qty-row">
        <label htmlFor={inputId}>Quantity</label>
        <input
          id={inputId}
          name={inputId}
          type="number"
          min={1}
          max={10_000}
          step={1}
          value={Number.isInteger(draft) ? draft : ""}
          onChange={(event) => {
            const next = Number.parseInt(event.target.value, 10);
            setDraft(Number.isNaN(next) ? line.quantity : next);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            }
          }}
          disabled={inFlight}
          aria-disabled={inFlight}
        />
        <button
          type="button"
          className="button button-secondary"
          disabled={inFlight || unchanged}
          aria-disabled={inFlight || unchanged}
          aria-busy={busy === "updating"}
          onClick={commit}
        >
          {busy === "updating" ? "Updating…" : "Update"}
        </button>
        <button
          type="button"
          className="button button-secondary"
          disabled={inFlight}
          aria-disabled={inFlight}
          aria-busy={busy === "removing"}
          aria-label={`Remove ${line.name} from cart`}
          onClick={() => onRemove(line.product_id)}
        >
          {busy === "removing" ? "Removing…" : "Remove"}
        </button>
      </div>
      <p className="cart-line-total">
        <span className="visually-hidden">Line total: </span>
        {formatMoney(line.line_total, line.currency)}
      </p>
      {inFlight ? (
        <p className="hint" role="status">
          {busy === "removing" ? "Removing this item…" : "Updating this item…"}
        </p>
      ) : null}
    </li>
  );
}

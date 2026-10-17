import type { Cart } from "../lib/cart";
import { formatMoney } from "../lib/money";

interface CheckoutSummaryProps {
  cart: Cart;
  submitting: boolean;
  onPlaceOrder: () => void;
}

/**
 * CheckoutSummary (DESIGN.md): cart lines, totals, and the place-order
 * CTA. The form submits `{cart_id}` only; while the order is in flight
 * the CTA disables with `aria-busy` so duplicate submits are
 * impossible, and the summary stays visible throughout.
 */
export function CheckoutSummary({ cart, submitting, onPlaceOrder }: CheckoutSummaryProps) {
  return (
    <div className="checkout-summary">
      <h2>Order summary</h2>
      <ul className="checkout-lines">
        {cart.items.map((line) => (
          <li key={line.product_id} className="checkout-line">
            <span className="checkout-line-name">{line.name}</span>
            <span className="checkout-line-qty" aria-label={`Quantity ${line.quantity}`}>
              × {line.quantity}
            </span>
            <span className="checkout-line-total">
              <span className="visually-hidden">Line total: </span>
              {formatMoney(line.line_total, line.currency)}
            </span>
          </li>
        ))}
      </ul>
      <p className="cart-subtotal">
        Total: {formatMoney(cart.subtotal, cart.currency)}
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onPlaceOrder();
        }}
      >
        <button
          type="submit"
          className="button button-primary"
          disabled={submitting}
          aria-disabled={submitting}
          aria-busy={submitting}
        >
          {submitting ? "Placing order…" : "Place order"}
        </button>
      </form>
    </div>
  );
}

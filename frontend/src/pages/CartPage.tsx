import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/session";
import { CartLineRow, type CartLineBusy } from "../components/CartLineRow";
import { ApiError } from "../lib/api-client";
import { createCartApi, type Cart } from "../lib/cart";
import { formatMoney } from "../lib/money";

type CartState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; cart: Cart };

/**
 * Authenticated cart (route-guarded by <ProtectedRoute>). Covers the
 * line lifecycle: loading overlay, retryable error, empty cart,
 * per-line updating/removing states, and the unavailable-item message
 * when a product disappears mid-edit.
 */
export function CartPage() {
  const { api } = useAuth();
  const [state, setState] = useState<CartState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<Record<string, CartLineBusy>>({});
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const cart = await createCartApi(api).get();
      setState({ kind: "ready", cart });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not load your cart.",
      });
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load, attempt]);

  function markBusy(productId: string, value: CartLineBusy) {
    setBusy((prev) => ({ ...prev, [productId]: value }));
  }

  async function onSetQuantity(productId: string, quantity: number) {
    markBusy(productId, "updating");
    setNotice(null);
    try {
      const cart = await createCartApi(api).setQuantity(productId, quantity);
      setState({ kind: "ready", cart });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotice("An item in your cart is unavailable. The cart was refreshed.");
        await load();
      } else {
        setNotice(err instanceof Error ? err.message : "Could not update the quantity.");
      }
    } finally {
      markBusy(productId, undefined);
    }
  }

  async function onRemove(productId: string) {
    markBusy(productId, "removing");
    setNotice(null);
    try {
      const cart = await createCartApi(api).remove(productId);
      setState({ kind: "ready", cart });
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Could not remove the item.");
    } finally {
      markBusy(productId, undefined);
    }
  }

  return (
    <section aria-labelledby="cart-title">
      <h1 id="cart-title">Your cart</h1>

      {state.kind === "loading" && (
        <p role="status" aria-live="polite">
          Loading your cart…
        </p>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">Could not load your cart: {state.message}</p>
          <button
            type="button"
            className="button button-primary"
            onClick={() => setAttempt((count) => count + 1)}
          >
            Retry
          </button>
        </div>
      )}

      {state.kind === "ready" && (
        <>
          {notice && (
            <p className="alert alert-error" role="alert">
              {notice}
            </p>
          )}
          {state.cart.items.length === 0 ? (
            <div role="status">
              <p>Your cart is empty.</p>
              <p>
                <Link className="button button-primary" to="/catalog">
                  Browse the catalog
                </Link>
              </p>
            </div>
          ) : (
            <>
              <ul className="cart-list">
                {state.cart.items.map((line) => (
                  <CartLineRow
                    key={`${line.product_id}-${line.quantity}`}
                    line={line}
                    busy={busy[line.product_id]}
                    onSetQuantity={onSetQuantity}
                    onRemove={onRemove}
                  />
                ))}
              </ul>
              <p className="cart-subtotal">
                Subtotal: {formatMoney(state.cart.subtotal, state.cart.currency)}
              </p>
              <p className="cta-row">
                <Link className="button button-primary" to="/checkout">
                  Proceed to checkout
                </Link>
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}

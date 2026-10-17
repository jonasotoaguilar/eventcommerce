import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/session";
import { CheckoutSummary } from "../components/CheckoutSummary";
import { ApiError } from "../lib/api-client";
import { createCartApi, type Cart } from "../lib/cart";
import { checkoutNavigation, newIdempotencyKey, placeCheckout } from "../lib/checkout";

type CheckoutState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; cart: Cart };

interface SubmitError {
  message: string;
  showCartLink: boolean;
}

/**
 * Map place-order failures to actionable UI. The cart summary stays
 * mounted through every error (form state is preserved); each retry is
 * a new attempt with a fresh Idempotency-Key.
 */
export function checkoutSubmitError(err: unknown): SubmitError {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return {
        message: "Your cart was not found. It may have expired — review your cart and try again.",
        showCartLink: true,
      };
    }
    if (err.status === 409) {
      return {
        message:
          "This attempt conflicted with a previous order attempt. Place the order again to retry with a fresh attempt.",
        showCartLink: false,
      };
    }
    if (err.status === 422) {
      return {
        message: `Your order could not be placed: ${err.detail} Review your cart and try again.`,
        showCartLink: true,
      };
    }
    if (err.status >= 500) {
      return {
        message:
          "The order could not be placed because of a server error. Your cart is unchanged — try again.",
        showCartLink: false,
      };
    }
    return { message: err.detail, showCartLink: false };
  }
  return {
    message: err instanceof Error ? err.message : "Could not place the order. Try again.",
    showCartLink: false,
  };
}

/**
 * Authenticated checkout (route-guarded by <ProtectedRoute>). Reviews
 * the cart, then submits `{cart_id}` only with a fresh Idempotency-Key
 * per attempt. Duplicate submits are suppressed while in flight; 201
 * redirects to the order tracker, and 404/409/422/500 stay on the page
 * with a recoverable action.
 */
export function CheckoutPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<CheckoutState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<SubmitError | null>(null);

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

  async function onPlaceOrder() {
    if (state.kind !== "ready" || submitting) return;
    if (state.cart.items.length === 0) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await placeCheckout(api, state.cart.cart_id, newIdempotencyKey());
      navigate(`/orders/${encodeURIComponent(result.order_id)}`, {
        replace: true,
        state: checkoutNavigation(result),
      });
    } catch (err) {
      setSubmitError(checkoutSubmitError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section aria-labelledby="checkout-title">
      <h1 id="checkout-title">Checkout</h1>

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

      {state.kind === "ready" &&
        (state.cart.items.length === 0 ? (
          <div role="status">
            <p>Your cart is empty — there is nothing to check out.</p>
            <p>
              <Link className="button button-primary" to="/catalog">
                Browse the catalog
              </Link>
            </p>
          </div>
        ) : (
          <>
            {submitError && (
              <div role="alert">
                <p className="alert alert-error">{submitError.message}</p>
                {submitError.showCartLink && (
                  <p>
                    <Link className="button button-secondary" to="/cart">
                      Review your cart
                    </Link>
                  </p>
                )}
              </div>
            )}
            {submitting && (
              <p role="status" aria-live="polite">
                Placing your order…
              </p>
            )}
            <CheckoutSummary
              cart={state.cart}
              submitting={submitting}
              onPlaceOrder={() => void onPlaceOrder()}
            />
            <p className="hint">
              Placing the order charges the cart shown above. Your cart is kept until the order
              succeeds.
            </p>
          </>
        ))}
    </section>
  );
}

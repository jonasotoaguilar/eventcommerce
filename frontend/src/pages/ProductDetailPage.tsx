import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../auth/session";
import { ApiError } from "../lib/api-client";
import { createCartApi } from "../lib/cart";
import { createCatalogApi, type Product } from "../lib/catalog";
import { formatMoney } from "../lib/money";

type DetailState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; product: Product };

/**
 * Public product detail. Signed-in shoppers get a quantity + add-to-cart
 * form (disabled in flight, confirmed with text + cart link); anonymous
 * shoppers get a log-in prompt instead of the form.
 */
export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const { api, status } = useAuth();
  const [state, setState] = useState<DetailState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) {
      setState({ kind: "missing" });
      return;
    }
    setState({ kind: "loading" });
    try {
      const product = await createCatalogApi(api).get(id);
      setState({ kind: "ready", product });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setState({ kind: "missing" });
      } else {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Could not load the product.",
        });
      }
    }
  }, [api, id]);

  useEffect(() => {
    void load();
  }, [load, attempt]);

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    if (state.kind !== "ready" || adding) return;
    setAdding(true);
    setAdded(false);
    setAddError(null);
    try {
      await createCartApi(api).add(state.product.id, quantity);
      setAdded(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setAddError("This product is unavailable and cannot be added to the cart.");
      } else {
        setAddError(err instanceof Error ? err.message : "Could not add this item to the cart.");
      }
    } finally {
      setAdding(false);
    }
  }

  return (
    <section aria-labelledby="product-detail-title">
      <h1 id="product-detail-title">Product details</h1>

      {state.kind === "loading" && (
        <p role="status" aria-live="polite">
          Loading product…
        </p>
      )}

      {state.kind === "missing" && (
        <div role="alert">
          <p className="alert alert-error">
            This product is unavailable. It may have been removed or deactivated.
          </p>
          <p className="cta-row">
            <button
              type="button"
              className="button button-primary"
              onClick={() => setAttempt((count) => count + 1)}
            >
              Retry
            </button>{" "}
            <Link className="button button-secondary" to="/catalog">
              Back to catalog
            </Link>
          </p>
        </div>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">Could not load the product: {state.message}</p>
          <p className="cta-row">
            <button
              type="button"
              className="button button-primary"
              onClick={() => setAttempt((count) => count + 1)}
            >
              Retry
            </button>{" "}
            <Link className="button button-secondary" to="/catalog">
              Back to catalog
            </Link>
          </p>
        </div>
      )}

      {state.kind === "ready" && (
        <article aria-labelledby="product-name">
          <h2 id="product-name">{state.product.name}</h2>
          {state.product.description ? <p>{state.product.description}</p> : null}
          <p className="product-price">
            <span className="visually-hidden">Price: </span>
            {formatMoney(state.product.price, state.product.currency)}
          </p>

          {status === "authenticated" ? (
            <form onSubmit={onAdd} className="add-to-cart">
              {addError && (
                <p className="alert alert-error" role="alert">
                  {addError}
                </p>
              )}
              {added && (
                <p className="alert alert-success" role="status">
                  Added to cart. <Link to="/cart">Review your cart</Link>.
                </p>
              )}
              <div className="field">
                <label htmlFor="detail-quantity">Quantity</label>
                <input
                  id="detail-quantity"
                  name="quantity"
                  type="number"
                  min={1}
                  max={10_000}
                  step={1}
                  value={quantity}
                  onChange={(event) => {
                    const next = Number.parseInt(event.target.value, 10);
                    setQuantity(Number.isInteger(next) && next >= 1 ? Math.min(next, 10_000) : 1);
                  }}
                  disabled={adding}
                  aria-disabled={adding}
                />
              </div>
              <button
                type="submit"
                className="button button-primary"
                disabled={adding}
                aria-disabled={adding}
                aria-busy={adding}
              >
                {adding ? "Adding…" : "Add to cart"}
              </button>
            </form>
          ) : (
            <p className="notice" role="status">
              <Link to="/login" state={{ next: location.pathname }}>Log in</Link> to add this item to your cart.
            </p>
          )}

          <p>
            <Link to="/catalog">Back to catalog</Link>
          </p>
        </article>
      )}
    </section>
  );
}

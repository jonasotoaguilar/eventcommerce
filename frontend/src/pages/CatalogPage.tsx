import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/session";
import { ProductCard } from "../components/ProductCard";
import { createCatalogApi, type Product } from "../lib/catalog";

type CatalogState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; products: Product[] };

/**
 * Public catalog browse: skeleton grid while loading, retryable error,
 * empty state, then the responsive product grid.
 */
export function CatalogPage() {
  const { api } = useAuth();
  const [state, setState] = useState<CatalogState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const products = await createCatalogApi(api).list();
      setState({ kind: "ready", products });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not load the catalog.",
      });
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load, attempt]);

  return (
    <section aria-labelledby="catalog-title">
      <h1 id="catalog-title">Catalog</h1>

      {state.kind === "loading" && (
        <div role="status" aria-live="polite">
          <p>Loading products…</p>
          <ul className="catalog-grid" aria-hidden="true">
            {Array.from({ length: 4 }, (_, index) => (
              <li key={index} className="product-card skeleton">
                Loading…
              </li>
            ))}
          </ul>
        </div>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">Could not load the catalog: {state.message}</p>
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
        (state.products.length === 0 ? (
          <div role="status">
            <p>No products yet. Check back soon.</p>
          </div>
        ) : (
          <ul className="catalog-grid">
            {state.products.map((product) => (
              <li key={product.id}>
                <ProductCard product={product} />
              </li>
            ))}
          </ul>
        ))}
    </section>
  );
}

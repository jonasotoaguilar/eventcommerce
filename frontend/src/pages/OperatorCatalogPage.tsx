import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/session";
import { OperatorProductRow } from "../components/OperatorProductRow";
import {
  createOperatorApi,
  formatStockChange,
  type OperatorCatalogRow,
  type ProductUpdateChanges,
  type StockAdjustResponse,
} from "../lib/operator";

type CatalogScreenState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: OperatorCatalogRow[] };

/**
 * Operator catalog: every product including inactive ones, with inline
 * editing and stock adjustment. Inactive rows carry an explicit text
 * label, so the distinction never relies on color alone. Stock figures
 * come from the read model at load time and from confirmed adjust
 * responses afterwards; nothing here claims live updates.
 */
export function OperatorCatalogPage() {
  const { api } = useAuth();
  const [state, setState] = useState<CatalogScreenState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const rows = await createOperatorApi(api).listCatalog({});
      setState({ kind: "ready", rows });
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

  async function handleSave(productId: string, changes: ProductUpdateChanges) {
    const updated = await createOperatorApi(api).updateProduct(productId, changes);
    setState((prev) =>
      prev.kind !== "ready"
        ? prev
        : {
            kind: "ready",
            rows: prev.rows.map((row) =>
              row.product_id === productId
                ? {
                    ...row,
                    name: updated.name,
                    description: updated.description,
                    price: updated.price,
                    currency: updated.currency,
                    active: updated.active,
                  }
                : row,
            ),
          },
    );
    setNotice(`Changes saved for ${updated.name}.`);
  }

  async function handleAdjust(
    productId: string,
    delta: number,
  ): Promise<StockAdjustResponse> {
    const before =
      state.kind === "ready"
        ? (state.rows.find((row) => row.product_id === productId)?.available_quantity ??
          null)
        : null;
    const result = await createOperatorApi(api).adjustStock(productId, delta);
    setState((prev) =>
      prev.kind !== "ready"
        ? prev
        : {
            kind: "ready",
            rows: prev.rows.map((row) =>
              row.product_id === productId
                ? {
                    ...row,
                    available_quantity: result.available_quantity,
                    reserved_quantity: result.reserved_quantity,
                  }
                : row,
            ),
          },
    );
    setNotice(
      `Stock updated: available ${formatStockChange(before, result.available_quantity)}.`,
    );
    return result;
  }

  return (
    <section aria-labelledby="operator-catalog-title">
      <h1 id="operator-catalog-title">Operator catalog</h1>

      {notice !== null && state.kind === "ready" && (
        <p className="alert alert-success" role="status" aria-live="polite">
          {notice}
        </p>
      )}

      {state.kind === "loading" && (
        <div role="status" aria-live="polite">
          <p>Loading catalog\u2026</p>
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
        (state.rows.length === 0 ? (
          <div role="status">
            <p>No catalog entries</p>
          </div>
        ) : (
          <div className="operator-table-wrap">
            <table className="operator-table">
              <caption className="visually-hidden">
                Catalog products with price, availability, and status
              </caption>
              <thead>
                <tr>
                  <th scope="col">Product</th>
                  <th scope="col">Price</th>
                  <th scope="col">Availability</th>
                  <th scope="col">Status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {state.rows.map((row) => (
                  <OperatorProductRow
                    key={row.product_id}
                    product={row}
                    onSave={handleSave}
                    onAdjust={handleAdjust}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}

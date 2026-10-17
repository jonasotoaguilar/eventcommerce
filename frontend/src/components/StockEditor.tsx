import { useState } from "react";
import {
  formatStockChange,
  parseStockDelta,
  type StockAdjustResponse,
} from "../lib/operator";

interface StockEditorProps {
  productId: string;
  productName: string;
  availableQuantity: number | null;
  reservedQuantity: number | null;
  onAdjust: (productId: string, delta: number) => Promise<StockAdjustResponse>;
}

type EditorState =
  | { kind: "idle" }
  | { kind: "confirming"; delta: number }
  | { kind: "saving"; delta: number }
  | {
      kind: "done";
      available: string;
      reserved: string;
    }
  | { kind: "error"; message: string; delta: number };

/**
 * Inline stock adjuster for one catalog row. The operator types a signed
 * delta, confirms it explicitly, and the confirmed record (before and
 * after quantities) stays visible afterwards. Stock has no event-log
 * endpoint, so the record is the latest adjust result, never a log.
 */
export function StockEditor({
  productId,
  productName,
  availableQuantity,
  reservedQuantity,
  onAdjust,
}: StockEditorProps) {
  const inputId = `stock-delta-${productId}`;
  const [draft, setDraft] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [state, setState] = useState<EditorState>({ kind: "idle" });

  const busy = state.kind === "saving";

  function requestConfirm() {
    const parsed = parseStockDelta(draft);
    if (!parsed.ok) {
      setValidationError(parsed.error);
      return;
    }
    setValidationError(null);
    setState({ kind: "confirming", delta: parsed.delta });
  }

  async function confirm() {
    if (state.kind !== "confirming" && state.kind !== "error") return;
    const { delta } = state;
    setState({ kind: "saving", delta });
    try {
      const result = await onAdjust(productId, delta);
      setState({
        kind: "done",
        available: formatStockChange(availableQuantity, result.available_quantity),
        reserved: formatStockChange(reservedQuantity, result.reserved_quantity),
      });
      setDraft("");
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not adjust stock.",
        delta,
      });
    }
  }

  function adjustAgain() {
    setState({ kind: "idle" });
    setValidationError(null);
    setDraft("");
  }

  const currentStock =
    availableQuantity === null
      ? "Stock not tracked yet"
      : `${availableQuantity} available` +
        (reservedQuantity === null ? "" : ` \u00B7 ${reservedQuantity} reserved`);

  return (
    <div className="stock-editor">
      <p className="stock-current">
        Current stock: <strong>{currentStock}</strong>
      </p>

      {state.kind === "done" ? (
        <div role="status">
          <p className="hint">
            Stock updated for {productName}: available {state.available}, reserved{" "}
            {state.reserved}.
          </p>
          <button type="button" className="button button-secondary" onClick={adjustAgain}>
            Adjust again
          </button>
        </div>
      ) : (
        <>
          <div className="qty-row">
            <label htmlFor={inputId}>Stock delta</label>
            <input
              id={inputId}
              name={inputId}
              type="number"
              step={1}
              placeholder="+5 or -3"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  requestConfirm();
                }
              }}
              disabled={busy}
              aria-disabled={busy}
              aria-describedby={`${inputId}-hint`}
            />
            <button
              type="button"
              className="button button-secondary"
              disabled={busy}
              aria-disabled={busy}
              aria-busy={busy}
              onClick={requestConfirm}
            >
              {busy ? "Adjusting\u2026" : "Adjust stock"}
            </button>
          </div>
          <p className="hint" id={`${inputId}-hint`}>
            Whole numbers only; use a minus sign to remove stock.
          </p>
          {validationError !== null && state.kind === "idle" && (
            <p className="alert alert-error" role="alert">
              {validationError}
            </p>
          )}
        </>
      )}

      {state.kind === "confirming" && (
        <div role="alertdialog" aria-label={`Confirm stock adjustment for ${productName}`}>
          <p>
            {state.delta > 0 ? "Add" : "Remove"} {Math.abs(state.delta)} unit
            {Math.abs(state.delta) === 1 ? "" : "s"}
            {state.delta > 0 ? " to " : " from "}
            {productName}? Current stock: {currentStock}.
          </p>
          <p className="cta-row">
            <button type="button" className="button button-primary" onClick={confirm}>
              Confirm adjustment
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => setState({ kind: "idle" })}
            >
              Cancel
            </button>
          </p>
        </div>
      )}

      {state.kind === "saving" && (
        <p className="hint" role="status">
          Adjusting stock\u2026
        </p>
      )}

      {state.kind === "error" && (
        <div role="alert">
          <p className="alert alert-error">
            Could not adjust stock for {productName}: {state.message}
          </p>
          <p className="cta-row">
            <button type="button" className="button button-primary" onClick={confirm}>
              Retry adjustment ({state.delta > 0 ? "+" : ""}
              {state.delta})
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => setState({ kind: "idle" })}
            >
              Back to editing
            </button>
          </p>
        </div>
      )}
    </div>
  );
}

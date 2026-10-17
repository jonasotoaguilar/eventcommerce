import { useState } from "react";
import { formatMoney, toNumber } from "../lib/money";
import type {
  OperatorCatalogRow,
  ProductUpdateChanges,
  StockAdjustResponse,
} from "../lib/operator";
import { StockEditor } from "./StockEditor";

interface OperatorProductRowProps {
  product: OperatorCatalogRow;
  onSave: (productId: string, changes: ProductUpdateChanges) => Promise<void>;
  onAdjust: (productId: string, delta: number) => Promise<StockAdjustResponse>;
}

interface ProductDraft {
  name: string;
  description: string;
  price: string;
  currency: string;
  active: boolean;
}

function toDraft(product: OperatorCatalogRow): ProductDraft {
  return {
    name: product.name,
    description: product.description ?? "",
    price: String(product.price),
    currency: product.currency,
    active: product.active,
  };
}

/**
 * Diff the edit draft against the last confirmed product so the PATCH
 * carries only what changed. Empty description means cleared (`null`);
 * price compares numerically so "12.50" over 12.5 is not a change.
 */
function diffChanges(
  product: OperatorCatalogRow,
  draft: ProductDraft,
): ProductUpdateChanges | { error: string } {
  const name = draft.name.trim();
  if (name.length === 0) return { error: "Name is required." };
  const description = draft.description.trim();
  const priceText = draft.price.trim();
  const price = Number(priceText);
  if (priceText.length === 0 || !Number.isFinite(price) || price < 0)
    return { error: "Price must be a number of 0 or more." };
  const currency = draft.currency.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(currency))
    return { error: "Currency must be a 3-letter code such as USD." };

  const changes: ProductUpdateChanges = {};
  if (name !== product.name) changes.name = name;
  const cleared = description.length === 0 ? null : description;
  if (cleared !== product.description) changes.description = cleared;
  if (price !== toNumber(product.price)) changes.price = priceText;
  if (currency !== product.currency) changes.currency = currency;
  if (draft.active !== product.active) changes.active = draft.active;
  return changes;
}

/**
 * One operator catalog row: name, price, availability, and active
 * state, with inline editing saved through `updateProduct`. Save
 * failures keep the form open with the draft intact; the parent
 * refreshes the row from the confirmed product on success.
 */
export function OperatorProductRow({ product, onSave, onAdjust }: OperatorProductRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ProductDraft>(() => toDraft(product));
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const nameId = `op-name-${product.product_id}`;
  const descriptionId = `op-description-${product.product_id}`;
  const priceId = `op-price-${product.product_id}`;
  const currencyId = `op-currency-${product.product_id}`;
  const activeId = `op-active-${product.product_id}`;

  function startEditing() {
    setDraft(toDraft(product));
    setFieldError(null);
    setSaveError(null);
    setEditing(true);
  }

  async function save() {
    const changes = diffChanges(product, draft);
    if ("error" in changes) {
      setFieldError(changes.error);
      return;
    }
    if (Object.keys(changes).length === 0) {
      setEditing(false);
      return;
    }
    setFieldError(null);
    setSaveError(null);
    setSaving(true);
    try {
      await onSave(product.product_id, changes);
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save the product.");
    } finally {
      setSaving(false);
    }
  }

  const availability =
    product.available_quantity === null
      ? "Not tracked"
      : `${product.available_quantity} available` +
        (product.reserved_quantity === null
          ? ""
          : ` \u00B7 ${product.reserved_quantity} reserved`);

  if (editing) {
    return (
      <tr className={product.active ? undefined : "operator-row-inactive"}>
        <td colSpan={5}>
          <form
            className="operator-edit-form"
            aria-label={`Edit ${product.name}`}
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <h3>
              Editing {product.name}
              {!product.active && " (inactive)"}
            </h3>
            {saveError !== null && (
              <p className="alert alert-error" role="alert">
                Save failed: {saveError}
              </p>
            )}
            {fieldError !== null && (
              <p className="alert alert-error" role="alert">
                {fieldError}
              </p>
            )}
            <div className="field">
              <label htmlFor={nameId}>Name</label>
              <input
                id={nameId}
                name={nameId}
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                disabled={saving}
                aria-disabled={saving}
                required
              />
            </div>
            <div className="field">
              <label htmlFor={descriptionId}>Description</label>
              <input
                id={descriptionId}
                name={descriptionId}
                value={draft.description}
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
                disabled={saving}
                aria-disabled={saving}
              />
            </div>
            <div className="field">
              <label htmlFor={priceId}>Price</label>
              <input
                id={priceId}
                name={priceId}
                inputMode="decimal"
                value={draft.price}
                onChange={(event) => setDraft({ ...draft, price: event.target.value })}
                disabled={saving}
                aria-disabled={saving}
              />
            </div>
            <div className="field">
              <label htmlFor={currencyId}>Currency</label>
              <input
                id={currencyId}
                name={currencyId}
                value={draft.currency}
                onChange={(event) =>
                  setDraft({ ...draft, currency: event.target.value })
                }
                disabled={saving}
                aria-disabled={saving}
                maxLength={3}
              />
            </div>
            <div className="field field-check">
              <input
                id={activeId}
                name={activeId}
                type="checkbox"
                checked={draft.active}
                onChange={(event) => setDraft({ ...draft, active: event.target.checked })}
                disabled={saving}
                aria-disabled={saving}
              />
              <label htmlFor={activeId}>Active (visible to shoppers)</label>
            </div>
            <p className="cta-row">
              <button
                type="submit"
                className="button button-primary"
                disabled={saving}
                aria-disabled={saving}
                aria-busy={saving}
              >
                {saving ? "Saving\u2026" : "Save changes"}
              </button>
              <button
                type="button"
                className="button button-secondary"
                disabled={saving}
                aria-disabled={saving}
                onClick={() => setEditing(false)}
              >
                Cancel
              </button>
            </p>
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr className={product.active ? undefined : "operator-row-inactive"}>
      <th scope="row" className="operator-cell-product">
        {product.name}
        {product.description ? (
          <span className="product-description">{product.description}</span>
        ) : null}
      </th>
      <td>{formatMoney(product.price, product.currency)}</td>
      <td>
        <p className="operator-availability">{availability}</p>
        <StockEditor
          productId={product.product_id}
          productName={product.name}
          availableQuantity={product.available_quantity}
          reservedQuantity={product.reserved_quantity}
          onAdjust={onAdjust}
        />
      </td>
      <td>
        <p className={`badge ${product.active ? "badge-active" : "badge-inactive"}`}>
          <span aria-hidden="true">{product.active ? "\u25CF " : "\u25CB "}</span>
          {product.active ? "Active" : "Inactive \u2014 hidden from shoppers"}
        </p>
      </td>
      <td>
        <button type="button" className="button button-secondary" onClick={startEditing}>
          Edit
        </button>
      </td>
    </tr>
  );
}

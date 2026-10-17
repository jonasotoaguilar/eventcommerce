/**
 * Display formatting for backend Decimal money, which serializes as a
 * JSON number or string. Parsing and formatting stay here so pages and
 * components share one display path.
 */

/** Normalize a Decimal-as-JSON value; NaN when it is not numeric. */
export function toNumber(value: number | string): number {
  if (typeof value === "number") return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

/**
 * Format an amount with its ISO currency code ("$12.50"). Falls back to
 * "<CODE> <amount>" for unknown codes and to an em-dash amount when the
 * value is not numeric, so the UI never renders a bare NaN.
 */
export function formatMoney(value: number | string, currency: string | null | undefined): string {
  const amount = toNumber(value);
  if (!Number.isFinite(amount)) return currency ? `${currency} \u2014` : "\u2014";
  const code = currency && /^[A-Z]{3}$/.test(currency) ? currency : null;
  if (code === null) return amount.toFixed(2);
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: code }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

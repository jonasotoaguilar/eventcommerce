import type { TimelineEvent } from "./orders";

/**
 * Exact order status vocabulary (DESIGN.md async status language, owned
 * by docs/GLOSSARY.md). Copy is exact, never paraphrased into
 * friendlier wording, and status is never communicated by color alone:
 * every badge pairs text with an icon.
 */
export const ORDER_STATUSES = [
  "pending",
  "inventory_reserved",
  "payment_authorized",
  "confirmed",
  "cancelled",
] as const;

export type OrderStatus = (typeof ORDER_STATUSES)[number];

export function isOrderStatus(value: unknown): value is OrderStatus {
  return (
    typeof value === "string" && (ORDER_STATUSES as readonly string[]).includes(value)
  );
}

interface StatusCopy {
  /** Short badge label (exact vocabulary). */
  label: string;
  /** One-line explanation of what the status means. */
  description: string;
  /** Decorative icon glyph (aria-hidden at render). */
  icon: string;
}

export const ORDER_STATUS_COPY: Record<OrderStatus, StatusCopy> = {
  pending: {
    label: "pending",
    description: "Order submitted, no reservation result yet.",
    icon: "◷",
  },
  inventory_reserved: {
    label: "inventory_reserved",
    description: "Inventory held for the order.",
    icon: "▣",
  },
  payment_authorized: {
    label: "payment_authorized",
    description: "Payment authorized, awaiting confirmation.",
    icon: "⬣",
  },
  confirmed: {
    label: "confirmed",
    description: "Order reached a successful terminal state.",
    icon: "✓",
  },
  cancelled: {
    label: "cancelled",
    description: "Order reached a terminal cancelled state with a reason.",
    icon: "✕",
  },
};

/** Terminal states never advance; the tracker says so honestly. */
export function isTerminalStatus(status: OrderStatus): boolean {
  return status === "confirmed" || status === "cancelled";
}

/** Badge label for a status; "unknown" when the backend sends something new. */
export function statusLabel(status: string): string {
  return isOrderStatus(status) ? ORDER_STATUS_COPY[status].label : "unknown";
}

/** Description for a status; fallback keeps unknown values honest. */
export function statusDescription(status: string): string {
  if (isOrderStatus(status)) return ORDER_STATUS_COPY[status].description;
  return `Status "${status}" is not a known order status.`;
}

/**
 * Sort timeline events oldest-first by `occurred_at`. Events with
 * unparseable timestamps keep their relative order at the end, so the
 * list never claims an order it cannot prove.
 */
export function sortTimelineEvents(events: TimelineEvent[]): TimelineEvent[] {
  return [...events].sort((a, b) => {
    const aTime = Date.parse(a.occurred_at);
    const bTime = Date.parse(b.occurred_at);
    const aBad = Number.isNaN(aTime);
    const bBad = Number.isNaN(bTime);
    if (aBad && bBad) return 0;
    if (aBad) return 1;
    if (bBad) return -1;
    return aTime - bTime;
  });
}

/**
 * Format an ISO timestamp for display ("Jan 5, 2026, 3:04 PM" in the
 * shopper locale). Returns the raw value when it cannot be parsed, so
 * the UI never renders "Invalid Date".
 */
export function formatOccurredAt(value: string): string {
  const time = Date.parse(value);
  if (Number.isNaN(time)) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(time));
}

import { ORDER_STATUS_COPY, isOrderStatus } from "../lib/order-status";

/**
 * StatusBadge maps the exact five-state vocabulary to an icon + text
 * badge (never color alone). Unknown backend values render an honest
 * "unknown" badge instead of guessing.
 */
export function StatusBadge({ status }: { status: string }) {
  if (!isOrderStatus(status)) {
    return (
      <p className="badge badge-unknown" role="status">
        <span aria-hidden="true">? </span>unknown
      </p>
    );
  }
  const copy = ORDER_STATUS_COPY[status];
  return (
    <p className={`badge badge-status-${status}`} role="status">
      <span aria-hidden="true">{copy.icon} </span>
      {copy.label}
    </p>
  );
}

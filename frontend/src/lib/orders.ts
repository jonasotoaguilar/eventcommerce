import type { ApiClient } from "./api-client";
import type { OrderStatus } from "./order-status";

/**
 * Order reads over the shopper contract:
 * GET /api/v1/orders/{id}          -> order detail (owner or operator)
 * GET /api/v1/orders/{id}/timeline -> chronological domain events
 *
 * Reads never leak existence: missing and forbidden both surface as a
 * 404 "Order not found" from the backend.
 */
export interface OrderItem {
  product_id: string;
  quantity: number;
}

export interface Order {
  order_id: string;
  customer_id: string;
  status: OrderStatus;
  cancel_reason: string | null;
  items: OrderItem[];
  created_at: string | null;
  updated_at: string | null;
}

export interface TimelineEvent {
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export function createOrdersApi(api: ApiClient) {
  return {
    /** Fetch one order by id. 404 when missing or not owned. */
    get(orderId: string): Promise<Order> {
      return api.get<Order>(`/orders/${encodeURIComponent(orderId)}`);
    },
    /** Fetch the order timeline (server returns chronological events). */
    timeline(orderId: string): Promise<TimelineEvent[]> {
      return api.get<TimelineEvent[]>(`/orders/${encodeURIComponent(orderId)}/timeline`);
    },
  };
}

export type OrdersApi = ReturnType<typeof createOrdersApi>;

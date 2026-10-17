import { describe, expect, it } from "vitest";
import {
  formatOccurredAt,
  isOrderStatus,
  isTerminalStatus,
  sortTimelineEvents,
  statusDescription,
  statusLabel,
} from "./order-status";
import type { TimelineEvent } from "./orders";

function event(type: string, at: string): TimelineEvent {
  return { event_type: type, occurred_at: at, payload: {} };
}

describe("order status vocabulary", () => {
  it("accepts exactly the five canonical statuses", () => {
    for (const status of [
      "pending",
      "inventory_reserved",
      "payment_authorized",
      "confirmed",
      "cancelled",
    ]) {
      expect(isOrderStatus(status)).toBe(true);
    }
    expect(isOrderStatus("shipped")).toBe(false);
    expect(isOrderStatus("CONFIRMED")).toBe(false);
    expect(isOrderStatus(null)).toBe(false);
  });

  it("maps every status to its exact DESIGN.md copy", () => {
    expect(statusLabel("pending")).toBe("pending");
    expect(statusDescription("pending")).toBe("Order submitted, no reservation result yet.");
    expect(statusDescription("inventory_reserved")).toBe("Inventory held for the order.");
    expect(statusDescription("payment_authorized")).toBe(
      "Payment authorized, awaiting confirmation.",
    );
    expect(statusDescription("confirmed")).toBe("Order reached a successful terminal state.");
    expect(statusDescription("cancelled")).toBe(
      "Order reached a terminal cancelled state with a reason.",
    );
  });

  it("stays honest about unknown statuses", () => {
    expect(statusLabel("shipped")).toBe("unknown");
    expect(statusDescription("shipped")).toContain("shipped");
  });

  it("marks only confirmed and cancelled as terminal", () => {
    expect(isTerminalStatus("confirmed")).toBe(true);
    expect(isTerminalStatus("cancelled")).toBe(true);
    expect(isTerminalStatus("pending")).toBe(false);
    expect(isTerminalStatus("inventory_reserved")).toBe(false);
    expect(isTerminalStatus("payment_authorized")).toBe(false);
  });
});

describe("sortTimelineEvents", () => {
  it("orders events oldest-first", () => {
    const sorted = sortTimelineEvents([
      event("b", "2026-01-03T00:00:00Z"),
      event("a", "2026-01-01T00:00:00Z"),
      event("c", "2026-01-02T00:00:00Z"),
    ]);
    expect(sorted.map((e) => e.event_type)).toEqual(["a", "c", "b"]);
  });

  it("keeps unparseable timestamps at the end without reordering them", () => {
    const sorted = sortTimelineEvents([
      event("bad", "not-a-date"),
      event("good", "2026-01-01T00:00:00Z"),
    ]);
    expect(sorted.map((e) => e.event_type)).toEqual(["good", "bad"]);
  });

  it("does not mutate the input array", () => {
    const input: TimelineEvent[] = [event("b", "2026-01-03T00:00:00Z")];
    sortTimelineEvents(input);
    expect(input.map((e) => e.event_type)).toEqual(["b"]);
  });
});

describe("formatOccurredAt", () => {
  it("formats ISO timestamps and passes raw values through", () => {
    expect(formatOccurredAt("2026-01-05T15:04:00Z")).toContain("2026");
    expect(formatOccurredAt("not-a-date")).toBe("not-a-date");
  });
});

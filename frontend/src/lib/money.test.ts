import { describe, expect, it } from "vitest";
import { formatMoney, toNumber } from "./money";

describe("toNumber", () => {
  it("passes numbers through", () => {
    expect(toNumber(12.5)).toBe(12.5);
  });

  it("parses numeric strings", () => {
    expect(toNumber("12.50")).toBe(12.5);
    expect(toNumber("0")).toBe(0);
  });

  it("returns NaN for non-numeric strings", () => {
    expect(toNumber("not-money")).toBeNaN();
  });
});

describe("formatMoney", () => {
  it("formats numbers and numeric strings with the currency", () => {
    expect(formatMoney(12.5, "USD")).toBe("$12.50");
    expect(formatMoney("12.50", "USD")).toBe("$12.50");
  });

  it("ignores malformed currency codes instead of rendering them", () => {
    expect(formatMoney("7.5", "XX1")).toBe("7.50");
    expect(formatMoney(7.5, null)).toBe("7.50");
  });

  it("never renders a bare NaN", () => {
    expect(formatMoney("nope", "USD")).toBe("USD \u2014");
    expect(formatMoney("nope", null)).toBe("\u2014");
  });
});

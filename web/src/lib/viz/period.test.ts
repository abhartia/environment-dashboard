import { describe, expect, it } from "vitest";

import { periodToYear } from "./period";

describe("periodToYear", () => {
  it("places periods at their middle", () => {
    expect(periodToYear("2025")).toBe(2025.5);
    expect(periodToYear("2026-01")).toBeCloseTo(2026 + 1 / 24);
    expect(periodToYear("2026-12")).toBeCloseTo(2026 + 23 / 24);
    expect(periodToYear("2012/2021")).toBe(2017);
  });
  it("orders days within a month", () => {
    expect(periodToYear("2026-10-01")).toBeLessThan(periodToYear("2026-10-02"));
    expect(periodToYear("2026-10-31")).toBeLessThan(periodToYear("2026-11-01"));
  });
  it("rejects non-periods", () => {
    expect(() => periodToYear("Aug 2026")).toThrow();
  });
});

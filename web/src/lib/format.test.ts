import { describe, expect, it } from "vitest";

import { formatPeriod, formatSigned, formatValue } from "./format";

describe("formatValue", () => {
  it("rounds to the indicator's decimals", () => {
    expect(formatValue(427.554, 2)).toBe("427.55");
    expect(formatValue(1.5470001, 2)).toBe("1.55");
    expect(formatValue(54149.17, 0)).toBe("54,149");
  });
  it("uses a true minus and never shows negative zero", () => {
    expect(formatValue(-0.36, 2)).toBe("−0.36");
    expect(formatValue(-0.004, 2)).toBe("0.00");
  });
  it("refuses values it cannot format honestly", () => {
    expect(() => formatValue(Number.NaN, 2)).toThrow();
    expect(() => formatValue(1, 7)).toThrow();
  });
});

describe("formatSigned", () => {
  it("adds a plus sign to positive changes only", () => {
    expect(formatSigned(1.433, 2)).toBe("+1.43");
    expect(formatSigned(-0.2, 2)).toBe("−0.20");
    expect(formatSigned(0.001, 2)).toBe("0.00");
  });
});

describe("formatPeriod", () => {
  it("reads ISO periods as words", () => {
    expect(formatPeriod("2026-08")).toBe("August 2026");
    expect(formatPeriod("2025")).toBe("2025");
    expect(formatPeriod("2026-10-02")).toBe("2 October 2026");
    expect(formatPeriod("2012/2021")).toBe("2012–2021");
  });
  it("rejects anything that is not a period", () => {
    expect(() => formatPeriod("Aug 2026")).toThrow();
    expect(() => formatPeriod("2026-13")).toThrow();
  });
});

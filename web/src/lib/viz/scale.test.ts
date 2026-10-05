import { describe, expect, it } from "vitest";

import { linePath, linear, r1 } from "./scale";

describe("linear", () => {
  it("maps domain to range, including inverted ranges", () => {
    const x = linear([0, 10], [0, 200]);
    expect(x(0)).toBe(0);
    expect(x(5)).toBe(100);
    expect(x(10)).toBe(200);
    const y = linear([0, 1], [100, 0]);
    expect(y(0.25)).toBe(75);
    expect(y.invert(75)).toBe(0.25);
  });

  it("makes round ticks inside the domain", () => {
    expect(linear([0, 10], [0, 1]).ticks(5)).toEqual([0, 2, 4, 6, 8, 10]);
    expect(linear([4, 15], [0, 1]).ticks(5)).toEqual([4, 6, 8, 10, 12, 14]);
    expect(linear([0, 0.35], [0, 1]).ticks(4)).toEqual([0, 0.1, 0.2, 0.3]);
    expect(linear([1.1, 2.05], [0, 1]).ticks(5)).toEqual([1.2, 1.4, 1.6, 1.8, 2]);
  });

  it("handles a degenerate domain", () => {
    const s = linear([3, 3], [0, 100]);
    expect(s(3)).toBe(50);
    expect(s.ticks()).toEqual([3]);
  });
});

describe("r1", () => {
  it("rounds to one decimal place", () => {
    expect(r1(1.25)).toBe(1.3);
    expect(r1(-0.04)).toBe(-0);
    expect(r1(12.3456)).toBe(12.3);
  });
});

describe("linePath", () => {
  it("draws segments and breaks at nulls", () => {
    expect(linePath([[0, 0], [1.26, 2], null, [3, 4], [5, 6.04]])).toBe("M0 0L1.3 2M3 4L5 6");
    expect(linePath([null, null])).toBe("");
    expect(linePath([[1, 1]])).toBe("M1 1");
  });
});

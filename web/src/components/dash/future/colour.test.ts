import { describe, expect, it } from "vitest";

import { scaleFor } from "@/components/dash/future/colour";

describe("map colour scale", () => {
  it("places counts on a square-root scale from zero", () => {
    const s = scaleFor({ ramp: "warm", spread: "sqrt", min: 0, max: 400 });
    expect(s.position(0)).toBe(0);
    expect(s.position(400)).toBe(1);
    // A quarter of the largest count sits halfway along the ramp.
    expect(s.position(100)).toBeCloseTo(0.5);
    expect(s.ticks[0]).toBe(0);
    expect(s.ticks.at(-1)!).toBeLessThanOrEqual(400);
  });

  it("places temperatures linearly between the smallest and largest value", () => {
    const s = scaleFor({ ramp: "warm", spread: "linear", min: 10, max: 50 });
    expect(s.position(30)).toBeCloseTo(0.5);
    expect(s.ticks[0]).toBeGreaterThanOrEqual(10);
  });

  it("keeps values outside the range at its ends, and gives each ramp its own colours", () => {
    const s = scaleFor({ ramp: "warm", spread: "linear", min: 10, max: 50 });
    expect(s.colour(60)).toBe(s.colour(50));
    expect(scaleFor({ ramp: "wet", spread: "linear", min: 0, max: 1 }).colour(0)).not.toBe(scaleFor({ ramp: "dry", spread: "linear", min: 0, max: 1 }).colour(0));
  });
});

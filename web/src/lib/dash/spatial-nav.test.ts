import { describe, expect, it } from "vitest";

import { nextPlace, type NavPoint } from "@/lib/dash/spatial-nav";

// A small grid of places, as a map would place their centres (x grows right, y grows down).
const pts: NavPoint[] = [
  { id: "A", x: 0, y: 0 },
  { id: "B", x: 10, y: 0 },
  { id: "C", x: 20, y: 1 },
  { id: "D", x: 10, y: 10 },
  { id: "E", x: 30, y: 30 },
];

describe("nextPlace", () => {
  it("moves to the nearest place in the arrow's direction", () => {
    expect(nextPlace(pts, "A", "right")).toBe("B");
    expect(nextPlace(pts, "B", "right")).toBe("C");
    expect(nextPlace(pts, "B", "down")).toBe("D");
    expect(nextPlace(pts, "D", "up")).toBe("B");
  });

  it("stays put when nothing lies that way", () => {
    expect(nextPlace(pts, "A", "left")).toBe("A");
    expect(nextPlace(pts, "A", "up")).toBe("A");
  });

  it("ignores places further to the side than ahead", () => {
    // From A, E is ahead to the right by 30 but 30 down: on the cone's edge, still allowed; D is 10 right, 10 down.
    expect(nextPlace([pts[0], pts[3]], "A", "right")).toBe("D");
    expect(nextPlace([pts[0], { id: "F", x: 5, y: 20 }], "A", "right")).toBe("A");
  });

  it("starts at the place nearest the middle when nothing is focused", () => {
    expect(nextPlace(pts, null, "right")).toBe("D");
    expect(nextPlace([], null, "right")).toBeNull();
  });
});

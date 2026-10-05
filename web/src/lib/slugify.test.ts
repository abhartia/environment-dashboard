import { describe, expect, it } from "vitest";

import { slugify } from "./slugify";

describe("slugify", () => {
  it("lowercases and dashes", () => {
    expect(slugify("The three loops")).toBe("the-three-loops");
    expect(slugify("IPMVP options, and why Option B fits a chiller plant")).toBe(
      "ipmvp-options-and-why-option-b-fits-a-chiller-plant",
    );
  });

  it("spells out ampersands", () => {
    expect(slugify("Chillers & towers")).toBe("chillers-and-towers");
  });

  it("collapses and trims separators", () => {
    expect(slugify("  What a result requires (Table 8-1)  ")).toBe("what-a-result-requires-table-8-1");
    expect(slugify("Legionella testing: monthly, by an ELAP lab")).toBe("legionella-testing-monthly-by-an-elap-lab");
    expect(slugify("--Hello--")).toBe("hello");
  });
});

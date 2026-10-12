import { describe, expect, it } from "vitest";

import { RELATION_EYEBROW } from "@/lib/dash/relation";

describe("RELATION_EYEBROW", () => {
  it("names every relation in a few words, with no number", () => {
    for (const [relation, words] of Object.entries(RELATION_EYEBROW)) {
      expect(words, relation).toMatch(/^[A-Z][a-z ]+$/);
      expect(words.split(" ").length, relation).toBeLessThanOrEqual(4);
    }
  });

  it("claims the warming as a cause only for the attributed relation", () => {
    const claims = Object.entries(RELATION_EYEBROW).filter(([, words]) => /caused/i.test(words));
    expect(claims.map(([r]) => r)).toEqual(["caused"]);
  });
});

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import type { Indicator } from "@/gen/hey-api/types.gen";
import { evaluate } from "@/lib/claims";
import { SECTIONS } from "@/lib/sections";
import { STORIES } from "@/lib/stories";

/** Claims are checked against the public data/ (the same files the site renders). */
const DATA = path.resolve(__dirname, "../../../data/v1/indicators");
const load = (id: string): Indicator => JSON.parse(readFileSync(path.join(DATA, `${id}.json`), "utf8"));

const CONTENT = path.resolve(__dirname, "../content/stories");

describe("story claims hold against the current data", () => {
  for (const s of STORIES) {
    for (const c of s.claims) {
      it(`${s.section}/${s.slug}: ${c.text}`, () => {
        expect(evaluate(c, load)).toBeNull();
      });
    }
  }
});

describe("story registry", () => {
  it("every story has an MDX body, a listed question, and a description under 160 characters", () => {
    for (const s of STORIES) {
      const listed = SECTIONS.find((x) => x.href === `/${s.section}`)?.stories.find((x) => x.slug === s.slug);
      expect(listed, `${s.section}/${s.slug} is not in lib/sections.ts`).toBeTruthy();
      expect(listed!.ready).toBe(true);
      readFileSync(path.join(CONTENT, s.section, `${s.slug}.mdx`), "utf8");
      expect(s.description.length).toBeLessThan(160);
    }
  });
});

/**
 * A number with a unit in story prose must come from data/ through <Num>, never be typed (pattern from wadecv's
 * stated-prices test). Years, list numbers and the baseline label "1850–1900" are allowed.
 */
const UNIT = /(?<![\w./-])\d[\d,.]*\s?(?:%|°C|ppm|ppb|Gt|Mt|GtCO|tonnes|W\/m|watts|mm|cm|km|°)(?![\w])/;
const IMPERATIVE = /\byou (?:should|must|need to|have to)\b/i;

describe("story prose", () => {
  for (const section of readdirSync(CONTENT)) {
    for (const file of readdirSync(path.join(CONTENT, section))) {
      const raw = readFileSync(path.join(CONTENT, section, file), "utf8");
      // Text outside JSX attribute values and component tags.
      const prose = raw.replace(/<[A-Z][\s\S]*?\/>/g, " ").replace(/\{[^{}]*\}/g, " ");
      it(`${section}/${file}: no typed numbers with units`, () => {
        const hit = prose.match(UNIT);
        expect(hit?.[0] ?? null, "use <Num id=…/> for data numbers").toBeNull();
      });
      it(`${section}/${file}: options are not given as instructions`, () => {
        expect(prose.match(IMPERATIVE)?.[0] ?? null).toBeNull();
      });
    }
  }
});

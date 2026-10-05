/**
 * The story registry: metadata for every story page (the body is MDX in src/content/stories/<section>/<slug>.mdx).
 * Dates are real per-page dates, never the build date. Claims are checked against the data in stories.test.ts.
 */
import type { Claim } from "@/lib/claims";
import { SECTIONS } from "@/lib/sections";

export type StoryMeta = {
  section: "causes" | "consequences" | "action";
  slug: string;
  /** The page's one-sentence answer, also its meta description (under 160 characters). */
  description: string;
  published: string;
  updated: string;
  /** Source ids in citation order: <Cite id> numbers follow this list, and the page lists them at the end. */
  sources: string[];
  claims: Claim[];
};

export const STORIES: StoryMeta[] = [
  {
    section: "causes",
    slug: "greenhouse-gases",
    description:
      "Carbon dioxide is above anything in 2,000 years of Antarctic ice, and human activity now holds in about 3 watts per square metre of extra heat.",
    published: "2026-10-05",
    updated: "2026-10-05",
    sources: ["noaa-gml-trends", "scripps-co2", "law-dome-2k", "noaa-gml-trends-ch4-n2o-sf6", "igcc-2025", "gcb-2025-global"],
    claims: [
      {
        text: "the global average has risen every year since NOAA's record began in 1979",
        check: { kind: "rising-every-period", series: { indicator: "co2.noaa-gml.annual-global" }, from: "1979" },
      },
      {
        text: "today's level is higher than any year in the Law Dome record",
        check: { kind: "exceeds-series", a: { indicator: "co2.noaa-gml.annual-global" }, series: { indicator: "co2.law-dome.2k" } },
      },
      {
        text: "aerosol pollution offsets part of the heating",
        check: { kind: "between", ref: { indicator: "forcing.igcc-2025.erf-by-agent", dims: { agent: "aerosol" } }, min: -5, max: 0 },
      },
      {
        text: "about 3 watts per square metre (meta description)",
        check: { kind: "between", ref: { indicator: "forcing.igcc-2025.erf-by-agent", dims: { agent: "anthropogenic" } }, min: 2.75, max: 3.25 },
      },
    ],
  },
];

export function story(section: string, slug: string): StoryMeta & { title: string; question: string } {
  const meta = STORIES.find((s) => s.section === section && s.slug === slug);
  const listed = SECTIONS.find((s) => s.href === `/${section}`)?.stories.find((s) => s.slug === slug);
  if (!meta || !listed) throw new Error(`Unknown story ${section}/${slug}`);
  return { ...meta, title: listed.title, question: listed.question };
}

import "server-only";

import { indicator } from "@/lib/data";
import { FUELS } from "@/lib/dash/emissions-tree";
import { credit, headline, matches, periodToX, points, type Dims } from "@/lib/dash/kit";
import type { Credit, Headline, SeriesPoint } from "@/lib/dash/types";

/**
 * The home page's story: six instruments on one time axis, in causal order. We burn fuel; carbon dioxide builds up in
 * the air; the world warms; the seas rise; the Arctic ice shrinks; and the switch to clean power. Each row is one
 * published series (or two, joined where one record ends and the next begins, each value keeping its own source).
 */

const BY_FUEL = "emissions.gcp-2025.fossil-co2-by-fuel";
const FOSSIL = "emissions.gcp-2025.fossil-co2-by-country";
const LAW_DOME = "co2.law-dome.2k";
const MLO = "co2.noaa-gml.monthly-mlo";
const HADCRUT = "temp.hadcrut5.annual-1850-1900";
const GMSL = "gmsl.aviso.monthly";
const SEA_ICE = "sea-ice-extent.nsidc.arctic-september";
const CLEAN = "electricity.ember.clean-share-world";

export const STORY_FROM = 1850;

/** One value a row's number can show: a published observation, with what is needed to trace it. */
export type StoryValue = { x: number; value: number; period: string; indicator: string; entity: string };

export type StoryRow = {
  key: string;
  href: string;
  /** The row's step in the story, in a few words. */
  phrase: string;
  unitLabel: string;
  decimals: number;
  kind: "stacked" | "line" | "stripes";
  series: { key: string; label: string; colour: string; points: SeriesPoint[] }[];
  /** The series the row's number reads from, oldest first. */
  values: StoryValue[];
  headline: Headline;
  credit: Credit[];
};

function values(id: string, entity: string, dims: Dims = {}, from = STORY_FROM, before = Number.POSITIVE_INFINITY): StoryValue[] {
  points(id, entity, dims); // the licence check: only redistributable values reach the page
  return indicator(id)
    .observations.filter((o) => matches(o, entity, dims) && o.value !== null && o.period !== null)
    .map((o) => ({ x: periodToX(o), value: o.value as number, period: o.period as string, indicator: id, entity }))
    .filter((v) => v.x >= from && v.x < before)
    .sort((a, b) => a.x - b.x);
}

function unit(id: string) {
  const ind = indicator(id);
  return { unitLabel: ind.unit.label, decimals: ind.display.decimals };
}

export function storyRows(): StoryRow[] {
  const mlo = values(MLO, "MLO");
  return [
    {
      key: "emissions",
      href: "/emissions",
      phrase: "We burn coal, oil and gas",
      ...unit(FOSSIL),
      decimals: 0,
      kind: "stacked",
      series: FUELS.map((f) => ({ key: f.id, label: f.label, colour: f.colour, points: points(BY_FUEL, "WLD", { fuel: f.id }, STORY_FROM) })).sort(
        (a, b) => (a.points.find((p) => p[1] !== null)?.[0] ?? Infinity) - (b.points.find((p) => p[1] !== null)?.[0] ?? Infinity),
      ),
      values: values(FOSSIL, "WLD"),
      headline: headline(FOSSIL, "WLD"),
      credit: credit(BY_FUEL, FOSSIL),
    },
    {
      key: "air",
      href: "/air",
      phrase: "Carbon dioxide builds up in the air",
      ...unit(MLO),
      kind: "line",
      series: [
        { key: "ice", label: "Law Dome ice cores", colour: "#4393c3", points: points(LAW_DOME, "LAWDOME", {}, STORY_FROM).filter((p) => p[0] < mlo[0].x) },
        { key: "mlo", label: "Mauna Loa", colour: "#b2182b", points: points(MLO, "MLO") },
      ],
      // Air from the ice until the measurements at Mauna Loa begin, then the measurements; each value keeps its source.
      values: [...values(LAW_DOME, "LAWDOME", {}, STORY_FROM, mlo[0].x), ...mlo],
      headline: headline(MLO, "MLO"),
      credit: credit(LAW_DOME, MLO),
    },
    {
      key: "heat",
      href: "/heat",
      phrase: "The world warms",
      ...unit(HADCRUT),
      kind: "stripes",
      series: [{ key: "hadcrut", label: "HadCRUT5, above 1850–1900", colour: "#b2182b", points: points(HADCRUT, "WLD") }],
      values: values(HADCRUT, "WLD"),
      headline: headline(HADCRUT, "WLD"),
      credit: credit(HADCRUT),
    },
    {
      key: "seas",
      href: "/oceans",
      phrase: "The seas rise",
      ...unit(GMSL),
      kind: "line",
      series: [{ key: "gmsl", label: "Global mean sea level, from 1993", colour: "#2166ac", points: points(GMSL, "WLD") }],
      values: values(GMSL, "WLD"),
      headline: headline(GMSL, "WLD"),
      credit: credit(GMSL),
    },
    {
      key: "ice",
      href: "/oceans?v=sea-ice",
      phrase: "The Arctic ice shrinks",
      ...unit(SEA_ICE),
      kind: "line",
      series: [{ key: "ice", label: "Arctic sea ice in September", colour: "#4393c3", points: points(SEA_ICE, "NH") }],
      values: values(SEA_ICE, "NH"),
      headline: headline(SEA_ICE, "NH"),
      credit: credit(SEA_ICE),
    },
    {
      key: "clean",
      href: "/energy",
      phrase: "We can switch to clean power",
      ...unit(CLEAN),
      kind: "line",
      series: [{ key: "clean", label: "Clean share of electricity", colour: "#1b7837", points: points(CLEAN, "WLD") }],
      values: values(CLEAN, "WLD"),
      headline: headline(CLEAN, "WLD"),
      credit: credit(CLEAN),
    },
  ];
}

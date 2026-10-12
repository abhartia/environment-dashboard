import "server-only";

import { indicator } from "@/lib/data";
import { CHAPTERS } from "@/lib/dash/chapters";
import { FUELS } from "@/lib/dash/emissions-tree";
import { baseline, credit, headline, matches, periodToX, points, type Dims } from "@/lib/dash/kit";
import type { Credit, Headline, SeriesPoint } from "@/lib/dash/types";

/**
 * The home page's story: seven instruments on one time axis, in causal order. We burn fuel; carbon dioxide builds up
 * in the air; the world warms; its hottest days get hotter; ice on land melts; the seas rise; and the switch to clean
 * power. Each row is one published series (or two, joined where one record ends and the next begins, each value
 * keeping its own source), and under each chart a band says what that change means for people: another view's own
 * traced headline, copied here and checked against it, never computed.
 */

const BY_FUEL = "emissions.gcp-2025.fossil-co2-by-fuel";
const FOSSIL = "emissions.gcp-2025.fossil-co2-by-country";
const LAW_DOME = "co2.law-dome.2k";
const MLO = "co2.noaa-gml.monthly-mlo";
const HADCRUT = "temp.hadcrut5.annual-1850-1900";
const HUMAN = "warming.igcc-2025.human-induced";
const TXX = "extremes.igcc-2025.txx-land";
const TXX_ENTITY = "WLD";
const GLACIERS = "glacier-mass.wgms-amce.cumulative";
const GREENLAND = "ice-sheet-mass.imbie-2026.greenland";
const ANTARCTICA = "ice-sheet-mass.imbie-2026.antarctica";
const GMSL = "gmsl.aviso.monthly";
const CLEAN = "electricity.ember.clean-share-world";

export const STORY_FROM = 1850;

/** One value a number can show: a published observation, with what is needed to trace it and print it as published. */
export type StoryValue = {
  x: number;
  value: number;
  period: string;
  indicator: string;
  entity: string;
  decimals: number;
  status: Headline["status"];
};

/**
 * What a row's change means for people (or, for carbon dioxide, how unusual it is): the headline of the view it opens,
 * with that view's series on the same time axis. The words follow the number and carry no digit; "{year}" is the
 * shown value's own period.
 */
export type StoryBand = {
  key: string;
  href: string;
  words: string;
  /** Print the unit in words after the number (when the words do not already say it). */
  unit: boolean;
  unitLabel: string;
  /** The axis position from which the band shows: when its record starts, or the moment its claim became true. */
  from: number;
  /** Oldest first; the last is the target view's headline. A value with no time of its own sits at `from`. */
  values: StoryValue[];
  points: SeriesPoint[];
};

export type StoryRow = {
  key: string;
  href: string;
  /** The row's step in the story, in a few words. */
  phrase: string;
  unitLabel: string;
  /** What the number is measured against, from the producer's own baseline ("above 1850–1900"), or empty. */
  context: string;
  /** Names the grey context lines inside the chart, just before they begin, where a wider screen has room. */
  contextLabel?: string;
  kind: "stacked" | "line" | "stripes";
  /** `context` series are drawn grey behind the one the number reads, so colour marks only that one. */
  series: { key: string; label: string; colour: string; points: SeriesPoint[]; context?: boolean }[];
  /** The series the row's number reads from, oldest first. */
  values: StoryValue[];
  headline: Headline;
  band?: StoryBand;
  credit: Credit[];
};

function values(id: string, entity: string, dims: Dims = {}, from = STORY_FROM, before = Number.POSITIVE_INFINITY): StoryValue[] {
  points(id, entity, dims); // the licence check: only redistributable values reach the page
  const ind = indicator(id);
  return ind.observations
    .filter((o) => matches(o, entity, dims) && o.value !== null && o.period !== null)
    .map((o) => ({
      x: periodToX(o),
      value: o.value as number,
      period: o.period as string,
      indicator: id,
      entity,
      decimals: ind.display.decimals,
      status: o.status,
    }))
    .filter((v) => v.x >= from && v.x < before)
    .sort((a, b) => a.x - b.x);
}

/**
 * A band: what the change means, read from the view it opens (`chapter:node`), so it can never disagree with it.
 * `at` places a value with no time of its own (a maximum, a level of warming) on the axis where its claim became true.
 */
function band(key: string, to: `${string}:${string}`, words: string, opts: { unit?: boolean; at?: number } = {}): StoryBand {
  if (/\d/.test(words)) throw new Error(`story/${key}: the band's words carry a digit; numbers come from the data`);
  const [chapter, node] = to.split(":");
  const h = CHAPTERS[chapter].node(node).headline;
  // The target's own slice of its indicator (the same dims as its headline), or its one value placed at `at`.
  const series: StoryValue[] =
    opts.at === undefined
      ? values(h.indicator, h.entity, h.dims ?? {}, Number.NEGATIVE_INFINITY)
      : [{ x: opts.at, value: h.value, period: h.period, indicator: h.indicator, entity: h.entity, decimals: indicator(h.indicator).display.decimals, status: h.status }];
  const last = series.at(-1);
  if (!last || last.indicator !== h.indicator || last.entity !== h.entity || last.period !== h.period || last.value !== h.value) {
    throw new Error(`story/${key}: the band's latest value is not ${to}'s headline`);
  }
  return {
    key,
    href: node === "root" ? `/${chapter}` : `/${chapter}?v=${node}`,
    words,
    unit: opts.unit ?? false,
    unitLabel: h.unitLabel,
    from: series[0].x,
    values: series,
    points: opts.at === undefined ? series.map((v) => [v.x, v.value] as SeriesPoint) : [],
  };
}

/** The first published value above `level`, as an axis position (when a claim of "higher than" became true). */
function firstAbove(vs: StoryValue[], level: number, what: string): number {
  const v = vs.find((x) => x.value > level);
  if (!v) throw new Error(`story: ${what} never passes ${level}, so the band's claim does not hold`);
  return v.x;
}

export function storyRows(): StoryRow[] {
  const mlo = values(MLO, "MLO");
  const air = [...values(LAW_DOME, "LAWDOME", {}, STORY_FROM, mlo[0].x), ...mlo];

  // The highest level in the ice before industry: the band shows from the moment the air passed it.
  const iceMax = CHAPTERS.air.node("co2-800k-max").headline;
  const airBand = band("air", "air:co2-800k-max", "was the highest in Antarctic ice before industry", { unit: true, at: firstAbove(air, iceMax.value, "carbon dioxide") });

  // How often a once-a-decade hottest day comes at a level of warming the world has passed (the IPCC's models). "Already
  // passed" holds only while the warming people caused is at or above that level. A level of warming is not a year, so
  // the band is placed at the latest year of that warming and shows when the story comes to rest.
  const extremes = CHAPTERS.people.node("root").headline;
  const level = Number(extremes.dims?.level);
  if (!Number.isFinite(level)) throw new Error("story: people/root's headline names no level of warming");
  const human = values(HUMAN, "WLD");
  if (human.at(-1)!.value < level) throw new Error(`story: the warming people caused is below ${level} °C, so the extremes band cannot say "already passed"`);
  const extremesBand = band("extremes", "people:root", "times as often at warming already passed: a once-a-decade hottest day", { at: human.at(-1)!.x });

  const rows: StoryRow[] = [
    {
      key: "emissions",
      href: "/emissions?v=fuels",
      phrase: "We burn coal, oil and gas",
      unitLabel: indicator(FOSSIL).unit.label,
      context: "",
      kind: "stacked",
      series: FUELS.map((f) => ({ key: f.id, label: f.label, colour: f.colour, points: points(BY_FUEL, "WLD", { fuel: f.id }, STORY_FROM) })).sort(
        (a, b) => (a.points.find((p) => p[1] !== null)?.[0] ?? Infinity) - (b.points.find((p) => p[1] !== null)?.[0] ?? Infinity),
      ),
      values: values(FOSSIL, "WLD"),
      headline: headline(FOSSIL, "WLD"),
      band: band("emissions", "people:smoke", "estimated early deaths from breathing the smoke, {year}"),
      credit: credit(BY_FUEL, FOSSIL),
    },
    {
      key: "air",
      href: "/air",
      phrase: "Carbon dioxide builds up in the air",
      unitLabel: indicator(MLO).unit.label,
      context: "",
      kind: "line",
      series: [
        { key: "ice", label: "Law Dome ice cores", colour: "#4393c3", points: points(LAW_DOME, "LAWDOME", {}, STORY_FROM).filter((p) => p[0] < mlo[0].x) },
        { key: "mlo", label: "Mauna Loa", colour: "#b2182b", points: points(MLO, "MLO") },
      ],
      // Air from the ice until the measurements at Mauna Loa begin, then the measurements; each value keeps its source.
      values: air,
      headline: headline(MLO, "MLO"),
      band: airBand,
      credit: credit(LAW_DOME, MLO),
    },
    {
      key: "heat",
      href: "/heat",
      phrase: "The world warms",
      unitLabel: indicator(HADCRUT).unit.label,
      context: baseline(HADCRUT),
      kind: "stripes",
      series: [{ key: "hadcrut", label: "HadCRUT5, above 1850–1900", colour: "#b2182b", points: points(HADCRUT, "WLD") }],
      values: values(HADCRUT, "WLD"),
      headline: headline(HADCRUT, "WLD"),
      band: band("heat", "people:heatwaves", "heatwave days per person caused by the warming (modelled), {year}"),
      credit: credit(HADCRUT),
    },
    {
      key: "extremes",
      href: "/people?v=hottest-day",
      phrase: "The hottest days get hotter",
      unitLabel: indicator(TXX).unit.label,
      context: baseline(TXX),
      kind: "line",
      series: [{ key: "txx", label: "Hottest day of the year over land (ERA5)", colour: "#d6604d", points: points(TXX, TXX_ENTITY) }],
      values: values(TXX, TXX_ENTITY),
      headline: headline(TXX, TXX_ENTITY),
      band: extremesBand,
      credit: credit(TXX),
    },
    {
      key: "ice",
      href: "/oceans?v=sources",
      phrase: "Ice on land melts",
      unitLabel: indicator(GLACIERS).unit.label,
      context: `of glacier ice ${baseline(GLACIERS)}`,
      contextLabel: "Greenland and Antarctic ice sheets",
      kind: "line",
      series: [
        { key: "greenland", label: "Greenland Ice Sheet", colour: "#4393c3", points: points(GREENLAND, "GRL"), context: true },
        { key: "antarctica", label: "Antarctic Ice Sheet", colour: "#053061", points: points(ANTARCTICA, "ATA"), context: true },
        { key: "glaciers", label: "Mountain glaciers", colour: "#7b5ea7", points: points(GLACIERS, "WLD") },
      ],
      values: values(GLACIERS, "WLD"),
      headline: headline(GLACIERS, "WLD"),
      band: band("ice", "oceans:sources", "of the sea's rise came from melting glaciers by {year}", { unit: true }),
      credit: credit(GLACIERS, GREENLAND, ANTARCTICA),
    },
    {
      key: "seas",
      href: "/oceans",
      phrase: "The seas rise",
      unitLabel: indicator(GMSL).unit.label,
      context: baseline(GMSL),
      kind: "line",
      series: [{ key: "gmsl", label: "Global mean sea level, from 1993", colour: "#2166ac", points: points(GMSL, "WLD") }],
      values: values(GMSL, "WLD"),
      headline: headline(GMSL, "WLD"),
      band: band("seas", "people:coasts", "lived on land below high tide in {year} (modelled)", { unit: true }),
      credit: credit(GMSL),
    },
    {
      key: "clean",
      href: "/energy",
      phrase: "We can switch to clean power",
      unitLabel: indicator(CLEAN).unit.label,
      context: "",
      kind: "line",
      series: [{ key: "clean", label: "Clean share of electricity", colour: "#1b7837", points: points(CLEAN, "WLD") }],
      values: values(CLEAN, "WLD"),
      headline: headline(CLEAN, "WLD"),
      band: band("clean", "people:smoke-power", "estimated early deaths from coal power stations' smoke, {year}"),
      credit: credit(CLEAN),
    },
  ];
  // Each band's source is credited on the page that shows its number.
  return rows.map((r) => (r.band ? { ...r, credit: [...r.credit, ...credit(r.band.values.at(-1)!.indicator).filter((c) => !r.credit.some((x) => x.indicator === c.indicator))] } : r));
}

import "server-only";

import { indicator } from "@/lib/data";
import { emissions } from "@/lib/dash/emissions-tree";
import { energy } from "@/lib/dash/energy-tree";
import { entityName } from "@/lib/dash/entities";
import { food } from "@/lib/dash/food-tree";
import { area, bars, type Built, credit, crossDrill, dimLabel, headline, latestPeriod, points, ranking } from "@/lib/dash/kit";
import type { Drill } from "@/lib/dash/types";

/**
 * Where the world's emissions come from, in the five activities Gates groups them into (making things, plugging in,
 * growing things, getting around, keeping warm and cool), from Climate TRACE grouped in the pipeline the way Rhodium
 * Group grouped Gates's own numbers. Each subsector carries its activity in the data, so this file only selects.
 */

const BY_ACTIVITY = "ghg.climate-trace.by-activity";
const SHARE = "ghg.climate-trace.by-activity-share";
const TOTAL = "ghg.climate-trace.five-activities-total";
const BY_SUBSECTOR = "ghg.climate-trace.by-subsector";

const TOP = 15;

/** Gates's five, in his order, with the colours the action chapter uses for the same sectors. */
const ACTIVITIES: { id: string; colour: string; drills: Drill[] }[] = [
  {
    id: "making-things",
    colour: "#5f5f5f",
    drills: [
      { label: "The extra cost of clean steel and cement", to: "premium-materials" },
      { label: "Cement with capture", to: "premium-cement" },
      { label: "Capture what is left", to: "capture" },
    ],
  },
  {
    id: "plugging-in",
    colour: "#b8860b",
    drills: [
      { label: "What new power plants cost", to: "premium-electricity" },
      { label: "How much space", to: "space" },
      { label: "How much power", to: "power" },
    ],
  },
  {
    id: "growing-things",
    colour: "#1b7837",
    drills: [
      { label: "Fertiliser made clean", to: "premium-ammonia" },
      { label: "Meat and its alternatives", to: "premium-meat" },
      { label: "Adapt", to: "adapt" },
    ],
  },
  {
    id: "getting-around",
    colour: "#2166ac",
    drills: [
      { label: "Cars", to: "premium-cars" },
      { label: "Lorries", to: "premium-trucks" },
      { label: "Jet fuel", to: "premium-jet-fuel" },
    ],
  },
  {
    id: "keeping-warm-and-cool",
    colour: "#c75400",
    drills: [
      { label: "Heating a home", to: "premium-heating" },
      { label: "Electrify", to: "electrify" },
    ],
  },
];

/** What is not one of the five, shown against the same total but never inside it. */
const BANDS: { id: string; colour: string }[] = [
  { id: "wildfires", colour: "#d6604d" },
  { id: "land-uptake", colour: "#7fbc41" },
  { id: "reservoirs", colour: "#67a9cf" },
];

function activity(id: string) {
  const a = ACTIVITIES.find((x) => x.id === id);
  if (!a) throw new Error(`zero: unknown activity ${id}`);
  return a;
}

function label(id: string): string {
  return dimLabel(BY_ACTIVITY, "activity", id);
}

/** Every activity and band the indicator publishes must be one this file knows (a new one fails the build). */
function checkGroups(): void {
  const published = indicator(BY_ACTIVITY).dimensions.find((d) => d.id === "activity")!.values.map((v) => v.id);
  const known = [...ACTIVITIES.map((a) => a.id), ...BANDS.map((b) => b.id)];
  const unknown = published.filter((p) => !known.includes(p));
  if (unknown.length) throw new Error(`zero: activities without a colour or place: ${unknown.join(", ")}`);
}

/** The five ranked by their value in a year, largest first (ties by id), so "largest" follows the data. */
function ranked(id: string, period: string): { id: string; value: number }[] {
  return ACTIVITIES.map((a) => ({ id: a.id, value: indicator(id).observations.find((o) => o.entity === "WLD" && o.period === period && o.dims.activity === a.id)?.value ?? null }))
    .filter((r): r is { id: string; value: number } => r.value !== null)
    .sort((a, b) => b.value - a.value || a.id.localeCompare(b.id));
}

export function rootNode(drills: Drill[]): Built {
  checkGroups();
  const h = headline(TOTAL, "WLD");
  const ind = indicator(BY_ACTIVITY);
  return {
    id: "root",
    parent: null,
    crumb: "Getting to zero",
    kicker: "Every activity that emits, on the way to zero",
    headline: h,
    sentence: `of greenhouse gases in ${h.period}, by Climate TRACE, from the five activities Bill Gates groups them into: making things, plugging in, growing things, getting around, and keeping warm and cool. Getting to zero means all five. Each band opens one; the cards ask his five questions.`,
    chart: area(
      ACTIVITIES.map((a) => ({ key: a.id, label: label(a.id), colour: a.colour, points: points(BY_ACTIVITY, "WLD", { activity: a.id }), drill: `activity-${a.id}` })),
      ind.unit.short,
      ind.display.decimals,
      true,
    ),
    drills: [...drills, crossDrill("All greenhouse gases by sector", "emissions", emissions.node("root"))],
    credit: credit(TOTAL, BY_ACTIVITY),
    indicators: [TOTAL, BY_ACTIVITY],
  };
}

export function sharesNode(): Built {
  checkGroups();
  const year = latestPeriod(SHARE);
  const rows = ranked(SHARE, year);
  const top = rows[0];
  const bands = BANDS.flatMap((b) => {
    const v = indicator(SHARE).observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.activity === b.id)?.value ?? null;
    return v === null ? [] : [{ ...b, value: v }];
  });
  const missingBands = BANDS.filter((b) => !bands.some((x) => x.id === b.id)).map((b) => label(b.id).replace(/^Not one of the five: /, ""));
  const ind = indicator(SHARE);
  return {
    id: "shares",
    parent: "root",
    crumb: "How much of the total",
    kicker: `${label(top.id)} is the largest share`,
    headline: headline(SHARE, "WLD", { activity: top.id }, year),
    sentence: `of the five activities' emissions in ${year} came from ${label(top.id).toLowerCase()}, by Climate TRACE. Gates's first question of any plan is how much of the total it is about. Wildfires and land taking carbon back up are measured against the same total but are not among the five.`,
    chart: bars(
      [
        ...rows.map((r) => ({ key: r.id, label: label(r.id), value: r.value, colour: activity(r.id).colour, drill: `activity-${r.id}` })),
        ...bands.map((b) => ({ key: b.id, label: label(b.id), value: b.value, colour: b.colour })),
      ],
      ind.unit.short,
      ind.display.decimals,
      year,
      `Shares of the five together, which add up to 100; the bands after them are outside the 100.${missingBands.length ? ` No ${year} value yet for ${missingBands.join(", ")}.` : ""}`,
    ),
    drills: ACTIVITIES.map((a) => ({ label: label(a.id), to: `activity-${a.id}` })),
    credit: credit(SHARE),
    indicators: [SHARE],
  };
}

function activityNode(id: string): Built {
  const a = activity(id);
  const year = latestPeriod(BY_SUBSECTOR);
  const subs = indicator(BY_SUBSECTOR)
    .observations.filter((o) => o.entity === "WLD" && o.period === year && o.dims.activity === id)
    .map((o) => ({ subsector: o.dims.subsector, value: o.value }));
  const shown = subs.filter((s): s is { subsector: string; value: number } => s.value !== null).sort((x, y) => y.value - x.value || x.subsector.localeCompare(y.subsector));
  const missing = subs.filter((s) => s.value === null).map((s) => dimLabel(BY_SUBSECTOR, "subsector", s.subsector));
  const largest = shown[0];
  const order = ranked(BY_ACTIVITY, year);
  const place = order.findIndex((r) => r.id === id);
  const placeWords = place === 0 ? "the largest of the five" : place === order.length - 1 ? "the smallest of the five" : null;
  const ind = indicator(BY_SUBSECTOR);
  const h = headline(BY_ACTIVITY, "WLD", { activity: id }, year);
  return {
    id: `activity-${id}`,
    parent: "root",
    crumb: label(id),
    kicker: `${label(id)}: where its emissions come from`,
    headline: h,
    sentence: `of greenhouse gases from ${label(id).toLowerCase()} in ${year}, by Climate TRACE${placeWords ? `, ${placeWords}` : ""}. ${dimLabel(BY_SUBSECTOR, "subsector", largest.subsector)} is its largest part.`,
    chart: bars(
      shown.slice(0, TOP).map((s) => ({ key: s.subsector, label: dimLabel(BY_SUBSECTOR, "subsector", s.subsector), value: s.value, colour: a.colour })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${Math.min(TOP, shown.length)} largest of the ${shown.length} parts with a ${year} value.${missing.length ? ` No ${year} value for ${missing.join(", ")}.` : ""}`,
    ),
    drills: [{ label: "Which countries", to: `activity-${id}-countries` }, ...a.drills, ...(id === "growing-things" ? [crossDrill("Food and land", "food", food.node("root"))] : []), ...(id === "plugging-in" ? [crossDrill("Clean electricity", "energy", energy.node("root"))] : [])],
    credit: credit(BY_ACTIVITY, BY_SUBSECTOR),
    indicators: [BY_ACTIVITY, BY_SUBSECTOR],
  };
}

function activityCountries(id: string): Built {
  const a = activity(id);
  const year = latestPeriod(BY_ACTIVITY);
  const rows = ranking(BY_ACTIVITY, year, { activity: id }).slice(0, TOP);
  const top = rows[0];
  const ind = indicator(BY_ACTIVITY);
  return {
    id: `activity-${id}-countries`,
    parent: `activity-${id}`,
    crumb: "Which countries",
    kicker: `${label(id)}: which countries emit the most`,
    headline: headline(BY_ACTIVITY, top.entity, { activity: id }, year),
    sentence: `of greenhouse gases from ${label(id).toLowerCase()} in ${entityName(top.entity)} in ${year}, the most of any country, by Climate TRACE.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: a.colour })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${rows.length} largest in ${year}; countries and territories only.`,
    ),
    drills: ACTIVITIES.filter((x) => x.id !== id).map((x) => ({ label: label(x.id), to: `activity-${x.id}-countries` })),
    credit: credit(BY_ACTIVITY),
    indicators: [BY_ACTIVITY],
  };
}

export function activityIds(): string[] {
  return ACTIVITIES.flatMap((a) => [`activity-${a.id}`, `activity-${a.id}-countries`]);
}

export function isActivityNode(id: string): boolean {
  return activityIds().includes(id);
}

export function buildActivity(id: string): Built {
  const m = id.match(/^activity-(.+?)(-countries)?$/);
  if (!m) throw new Error(`zero: not an activity node ${id}`);
  return m[2] ? activityCountries(m[1]) : activityNode(m[1]);
}

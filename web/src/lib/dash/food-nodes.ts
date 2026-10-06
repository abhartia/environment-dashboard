import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { area, bars, type Built, credit, headline, latestPeriod, points, ranking } from "@/lib/dash/kit";
import type { Drill, Series } from "@/lib/dash/types";

/**
 * Where food's emissions come from, from FAOSTAT: by stage (on the farm, clearing land for farming, before and after
 * the farm), by process within each stage, by food (farm-gate emissions of 14 commodities, and per kilogram), and
 * methane by animal. Each stack is made of parts FAO publishes that add up to the total it publishes.
 */

const STAGES = "food.faostat.agrifood-emissions-by-stage";
const PROCESSES = "food.faostat.agrifood-emissions-by-process";
const COMMODITY = "food.faostat.commodity-emissions";
const INTENSITY = "food.faostat.commodity-intensity";
const ANIMALS = "food.faostat.livestock-ch4-by-animal";

const TOP = 15;
const STAGE_COLOURS: Record<string, string> = { "farm-gate": "#8c510a", "land-use-change": "#1b7837", "pre-post-production": "#2166ac" };
const PALETTE = [
  "#8c510a", "#2166ac", "#1b7837", "#c75400", "#7b5ea7", "#b8860b", "#5f5f5f", "#a8447f",
  "#053061", "#7f3b08", "#006d5b", "#946200", "#4393c3", "#b2182b", "#8b8b86", "#e08214",
];
/** The node id of each stage's process view. */
const STAGE_NODE: Record<string, string> = { "farm-gate": "farm", "land-use-change": "land-clearing", "pre-post-production": "after-farm" };
/** Choices a stage's view offers besides the other stages: clearing land for farming leads on to the trees lost. */
const STAGE_LINKS: Record<string, Drill[]> = { "land-use-change": [{ label: "Tree cover lost each year", to: "tree-loss" }] };

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

export function dimValues(id: string, dim: string): { id: string; label: string }[] {
  const d = indicator(id).dimensions.find((x) => x.id === dim);
  if (!d) throw new Error(`${id}: no dimension ${dim}`);
  return d.values;
}

function stageSeries(entity: string, withDrills: boolean): Series[] {
  return dimValues(STAGES, "stage")
    .map((v) => ({
      key: v.id,
      label: v.label,
      colour: STAGE_COLOURS[v.id] ?? "#5f5f5f",
      points: points(STAGES, entity, { stage: v.id }),
      ...(withDrills && STAGE_NODE[v.id] ? { drill: STAGE_NODE[v.id] } : {}),
    }))
    .filter((s) => s.points.some((p) => p[1] !== null));
}

export function stages(): Built {
  const { short, decimals } = u(STAGES);
  const year = latestPeriod(STAGES);
  const rows = dimValues(STAGES, "stage")
    .map((v) => ({ v, h: headline(STAGES, "WLD", { stage: v.id }, year) }))
    .sort((a, b) => b.h.value - a.h.value);
  return {
    id: "stages",
    parent: "root",
    crumb: "By stage",
    kicker: "Where food's emissions come from",
    headline: rows[0].h,
    sentence: `${rows[0].v.label.toLowerCase()} in ${year}, the largest of FAO's three stages: ${dimValues(STAGES, "stage").map((v) => v.label.toLowerCase()).join(", ").replace(/, ([^,]*)$/, " and $1")}. Select a stage to see what is inside it.`,
    chart: area(stageSeries("WLD", true), short, decimals, true),
    drills: dimValues(STAGES, "stage")
      .filter((v) => STAGE_NODE[v.id])
      .map((v) => ({ label: v.label, to: STAGE_NODE[v.id] })),
    credit: credit(STAGES),
    indicators: [STAGES],
  };
}

/** The processes FAO groups under one stage, in the order they appear in the data. */
function processesOf(stage: string): { id: string; label: string }[] {
  const ids = new Set(indicator(PROCESSES).observations.filter((o) => o.dims.stage === stage).map((o) => o.dims.process));
  return dimValues(PROCESSES, "process").filter((v) => ids.has(v.id));
}

export function stageProcesses(stage: string): Built {
  const { short, decimals } = u(PROCESSES);
  const year = latestPeriod(PROCESSES);
  const procs = processesOf(stage)
    .map((v) => ({ v, latest: indicator(PROCESSES).observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.stage === stage && o.dims.process === v.id)?.value ?? null }))
    .sort((a, b) => (b.latest ?? -Infinity) - (a.latest ?? -Infinity));
  const top = procs.find((p) => p.latest !== null);
  if (!top) throw new Error(`food/${STAGE_NODE[stage]}: no ${year} value`);
  const stageLabel = dimValues(STAGES, "stage").find((v) => v.id === stage)?.label ?? stage;
  return {
    id: STAGE_NODE[stage],
    parent: "stages",
    crumb: stageLabel,
    kicker: `${stageLabel}: ${top.v.label.toLowerCase()} is the largest part`,
    headline: headline(PROCESSES, "WLD", { stage, process: top.v.id }, year),
    sentence: `from ${top.v.label.toLowerCase()} worldwide in ${year} (FAO). The bands add up to the stage's total.`,
    chart: area(
      procs.map((p, i) => ({ key: p.v.id, label: p.v.label, colour: PALETTE[i % PALETTE.length], points: points(PROCESSES, "WLD", { stage, process: p.v.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [
      ...Object.entries(STAGE_NODE)
        .filter(([s]) => s !== stage)
        .map(([s, node]) => ({ label: dimValues(STAGES, "stage").find((v) => v.id === s)?.label ?? s, to: node })),
      ...(STAGE_LINKS[stage] ?? []),
    ],
    credit: credit(PROCESSES),
    indicators: [PROCESSES],
  };
}

function commodities(): { id: string; label: string }[] {
  return dimValues(COMMODITY, "commodity");
}

export function foods(): Built {
  const ind = indicator(COMMODITY);
  const year = latestPeriod(COMMODITY);
  const rows = commodities()
    .map((v) => ({ v, value: ind.observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.commodity === v.id)?.value ?? null }))
    .filter((r): r is { v: { id: string; label: string }; value: number } => r.value !== null)
    .sort((a, b) => b.value - a.value);
  const top = rows[0];
  return {
    id: "foods",
    parent: "root",
    crumb: "By food",
    kicker: "Which foods emit the most on the farm",
    headline: headline(COMMODITY, "WLD", { commodity: top.v.id }, year),
    sentence: `on farms worldwide in ${year} from ${top.v.label.toLowerCase()}: the animals' digestion and manure, and fertiliser and rice paddies for crops (FAO). Farm energy, clearing land and everything after the farm are not counted, and soy, palm oil, fruit, vegetables, sugar and fish are not covered.`,
    chart: bars(
      rows.map((r) => ({ key: r.v.id, label: r.v.label, value: r.value, colour: "#8c510a", drill: `food-${r.v.id}` })),
      ind.unit.short,
      ind.display.decimals,
      year,
      "Farm-gate emissions of the 14 foods FAO covers; not comparable with whole-life footprints.",
    ),
    drills: [{ label: "Per kilogram", to: "per-kg" }],
    credit: credit(COMMODITY),
    indicators: [COMMODITY],
  };
}

export function foodItem(code: string): Built {
  const { short, decimals } = u(COMMODITY);
  const label = commodities().find((v) => v.id === code)?.label;
  if (!label) throw new Error(`food: unknown commodity ${code}`);
  const h = headline(COMMODITY, "WLD", { commodity: code });
  return {
    id: `food-${code}`,
    parent: "foods",
    crumb: label,
    kicker: `${label}: emissions on the farm`,
    headline: h,
    sentence: `on farms worldwide in ${h.period} (FAO, farm gate only).`,
    chart: area([{ key: code, label, colour: "#8c510a", points: points(COMMODITY, "WLD", { commodity: code }) }], short, decimals, false),
    drills: [{ label: "Which countries", to: `food-${code}-countries` }],
    credit: credit(COMMODITY),
    indicators: [COMMODITY],
  };
}

export function foodItemCountries(code: string): Built {
  const ind = indicator(COMMODITY);
  const label = commodities().find((v) => v.id === code)?.label ?? code;
  const year = latestPeriod(COMMODITY);
  const ranked = ranking(COMMODITY, year, { commodity: code });
  const top = ranked.slice(0, TOP);
  return {
    id: `food-${code}-countries`,
    parent: `food-${code}`,
    crumb: "By country",
    kicker: `Where ${label.toLowerCase()} emits the most`,
    headline: headline(COMMODITY, top[0].entity, { commodity: code }, year),
    sentence: `on farms in ${entityName(top[0].entity)} in ${year}, the most of any country (FAO, farm gate only).`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: "#8c510a" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, ranked by emissions (not per kilogram).`,
    ),
    drills: [],
    credit: credit(COMMODITY),
    indicators: [COMMODITY],
  };
}

export function perKg(): Built {
  const ind = indicator(INTENSITY);
  const year = latestPeriod(INTENSITY);
  const rows = dimValues(INTENSITY, "commodity")
    .map((v) => ({ v, value: ind.observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.commodity === v.id)?.value ?? null }))
    .filter((r): r is { v: { id: string; label: string }; value: number } => r.value !== null)
    .sort((a, b) => b.value - a.value);
  const top = rows[0];
  return {
    id: "per-kg",
    parent: "foods",
    crumb: "Per kilogram",
    kicker: "Emissions per kilogram, on the farm",
    headline: headline(INTENSITY, "WLD", { commodity: top.v.id }, year),
    sentence: `for each kilogram of ${top.v.label.toLowerCase()} produced worldwide in ${year}, counting only what happens on the farm (FAO). Raw weight, not protein; feed, land clearing and processing are left out.`,
    chart: bars(
      rows.map((r) => ({ key: r.v.id, label: r.v.label, value: r.value, colour: "#8c510a" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      "World averages per kilogram of product at the farm gate; not comparable with whole-life footprints.",
    ),
    drills: [{ label: "Which foods emit the most", to: "foods" }],
    credit: credit(INTENSITY),
    indicators: [INTENSITY],
  };
}

export function animals(): Built {
  const { short, decimals } = u(ANIMALS);
  const year = latestPeriod(ANIMALS);
  const ranked = dimValues(ANIMALS, "animal")
    .map((v) => ({ v, value: indicator(ANIMALS).observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.animal === v.id)?.value ?? -Infinity }))
    .sort((a, b) => b.value - a.value);
  const top = ranked[0];
  return {
    id: "animals",
    parent: "root",
    crumb: "Farm animals",
    kicker: "Methane from farm animals, by animal",
    headline: headline(ANIMALS, "WLD", { animal: top.v.id }, year),
    sentence: `of methane from ${top.v.label.toLowerCase()} worldwide in ${year}, the most of any animal: their digestion and their manure (FAO). The bands add up to all farm animals.`,
    chart: area(
      ranked.map((r, i) => ({ key: r.v.id, label: r.v.label, colour: PALETTE[i % PALETTE.length], points: points(ANIMALS, "WLD", { animal: r.v.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "Which foods emit the most", to: "foods" }],
    credit: credit(ANIMALS),
    indicators: [ANIMALS],
  };
}

/** A country's agrifood emissions by stage (replaces the single total band). */
export function countryStages(iso: string, totalId: string): Built {
  const { short, decimals } = u(STAGES);
  const name = entityName(iso);
  const h = headline(totalId, iso);
  return {
    id: `c-${iso}`,
    parent: "countries",
    crumb: name,
    kicker: `${name}: food and farming emissions, by stage`,
    headline: h,
    sentence: `from ${name}'s food and farming system in ${h.period} (FAO): on farms, from clearing land for farming, and before and after the farm.`,
    chart: area(stageSeries(iso, false), short, decimals, true),
    drills: [],
    credit: credit(totalId, STAGES),
    indicators: [totalId, STAGES],
  };
}

export function foodNodeIds(): string[] {
  const out = ["stages", ...Object.values(STAGE_NODE), "foods", "per-kg", "animals"];
  for (const c of commodities()) {
    out.push(`food-${c.id}`);
    if (ranking(COMMODITY, latestPeriod(COMMODITY), { commodity: c.id }).length > 0) out.push(`food-${c.id}-countries`);
  }
  return out;
}

export function buildFood(id: string): Built | null {
  if (id === "stages") return stages();
  const stage = Object.entries(STAGE_NODE).find(([, node]) => node === id)?.[0];
  if (stage) return stageProcesses(stage);
  if (id === "foods") return foods();
  if (id === "per-kg") return perKg();
  if (id === "animals") return animals();
  const fc = id.match(/^food-(.+)-countries$/);
  if (fc) return foodItemCountries(fc[1]);
  const f = id.match(/^food-(.+)$/);
  if (f) return foodItem(f[1]);
  return null;
}

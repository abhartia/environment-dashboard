import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { food } from "@/lib/dash/food-tree";
import { area, bars, type Built, credit, crossDrill, dimLabel, headline, latestPeriod, line, points, ranking } from "@/lib/dash/kit";
import type { Drill } from "@/lib/dash/types";

/**
 * The top of the emissions chapter: all greenhouse gases, from FAOSTAT's emissions totals. FAO's six IPCC sectors do
 * not overlap and add up to its all-sector total including land use, the same total behind its share of emissions
 * that come from food. Food is not a seventh band: its emissions run through the energy, industry, farming, land and
 * waste bands, so it has its own view. Carbon dioxide alone (Global Carbon Project) is one level down, on its own
 * basis; the two are never added or subtracted. One person's footprint (Sweden) leads to the UK's by use, then to UK
 * households' own spending by product group.
 */

export const GHG_TOTAL = "ghg.faostat.total";
const GHG_SECTOR = "ghg.faostat.by-sector";
const GHG_GAS = "ghg.faostat.by-gas";
const GHG_PER_CAPITA = "ghg.faostat.per-capita";
const CH4_SHARE = "ghg.faostat.ch4-share-by-sector";
const FOOD_SHARE = "food.faostat.agrifood-emissions-world.share";
const STAGES = "food.faostat.agrifood-emissions-by-stage";
const SE_BY_AREA = "footprint.naturvardsverket.per-person-by-area";
const SE_TOTAL = "footprint.naturvardsverket.per-person-total";
const UK_PER_CAPITA = "footprint.defra.per-capita";
const UK_BY_USE = "footprint.defra.by-end-use";
const UK_HOUSEHOLDS = "footprint.defra.households-by-product";

const TOP = 15;
/** UK households' product groups drawn as lines: the largest few in the latest year, so the chart stays readable. */
const UK_LINES = 5;

/** Sector colours: energy dark, industry grey, farming brown, land green (it can be a net sink), waste purple. */
const SECTOR_COLOURS: Record<string, string> = {
  energy: "#3d3d3d",
  industry: "#8b8b86",
  agriculture: "#8c510a",
  "land-use": "#1b7837",
  waste: "#7b5ea7",
  other: "#c75400",
};
const GAS_COLOURS: Record<string, string> = { co2: "#b2182b", ch4: "#c75400", n2o: "#7b5ea7", "f-gases": "#2166ac" };
const STAGE_COLOURS: Record<string, string> = { "farm-gate": "#8c510a", "land-use-change": "#1b7837", "pre-post-production": "#2166ac" };
const AREA_COLOURS = ["#2166ac", "#8c510a", "#c75400", "#7b5ea7", "#8b8b86", "#5f5f5f", "#1b7837", "#b2182b"];

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

/** The values of one dimension, in the producer's order, with their labels. */
function dimValues(id: string, dim: string): { id: string; label: string }[] {
  const d = indicator(id).dimensions.find((x) => x.id === dim);
  if (!d) throw new Error(`${id}: no dimension ${dim}`);
  return d.values;
}

function sectorSeries(entity: string, drills: Record<string, string> = {}) {
  return dimValues(GHG_SECTOR, "sector")
    .map((v) => ({
      key: v.id,
      label: v.label,
      colour: SECTOR_COLOURS[v.id] ?? "#5f5f5f",
      points: points(GHG_SECTOR, entity, { sector: v.id }),
      ...(drills[v.id] ? { drill: drills[v.id] } : {}),
    }))
    .filter((s) => s.points.some((p) => p[1] !== null));
}

export function ghgRoot(): Built {
  const { short, decimals } = u(GHG_SECTOR);
  const h = headline(GHG_TOTAL, "WLD");
  const drills: Drill[] = [
    { label: "Food and farming", to: "food-system" },
    { label: "Which gases", to: "gases" },
    { label: "Carbon dioxide from fuel and land", to: "co2" },
    { label: "Which countries", to: "ghg-countries" },
    { label: "Each country's average per person", to: "ghg-per-person" },
    { label: "One person's footprint", to: "footprint" },
  ];
  return {
    id: "root",
    parent: null,
    crumb: "All greenhouse gases",
    kicker: "Greenhouse gases we put into the air",
    headline: h,
    sentence: `of all greenhouse gases in ${h.period}, counted as carbon dioxide equivalent, including land use (FAO, with PRIMAP-hist for energy, industry and waste). Food and farming run through several of these bands.`,
    chart: area(sectorSeries("WLD", { agriculture: "food-system", "land-use": "food-system", energy: "co2" }), short, decimals, true),
    drills,
    credit: credit(GHG_TOTAL, GHG_SECTOR),
    indicators: [GHG_TOTAL, GHG_SECTOR],
  };
}

export function foodSystem(): Built {
  const { short, decimals } = u(STAGES);
  const h = headline(FOOD_SHARE, "WLD");
  return {
    id: "food-system",
    parent: "root",
    crumb: "Food and farming",
    kicker: "Food and farming run through every sector",
    headline: h,
    sentence: `of all greenhouse gases came from producing and using food in ${h.period} (FAO): on farms, from clearing land for farming, and from processing, transport, shops, kitchens and waste. These emissions sit inside the energy, industry, farming, land and waste bands, not on top of them.`,
    chart: area(
      dimValues(STAGES, "stage").map((v) => ({ key: v.id, label: v.label, colour: STAGE_COLOURS[v.id] ?? "#5f5f5f", points: points(STAGES, "WLD", { stage: v.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [crossDrill("Where food's emissions come from", "food", food.node("stages")), crossDrill("Which foods", "food", food.node("foods"))],
    credit: credit(FOOD_SHARE, STAGES),
    indicators: [FOOD_SHARE, STAGES],
  };
}

export function gases(): Built {
  const { short, decimals } = u(GHG_GAS);
  const h = headline(GHG_GAS, "WLD", { gas: "co2" });
  const drill: Record<string, string> = { co2: "co2", ch4: "methane", n2o: "food-system" };
  return {
    id: "gases",
    parent: "root",
    crumb: "By gas",
    kicker: "Carbon dioxide, then methane",
    headline: h,
    sentence: `of the total in ${h.period} was carbon dioxide itself. The other gases are counted by how much heat they trap over a century compared with carbon dioxide (FAO, AR5).`,
    chart: area(
      dimValues(GHG_GAS, "gas").map((v) => ({
        key: v.id,
        label: v.label,
        colour: GAS_COLOURS[v.id] ?? "#5f5f5f",
        points: points(GHG_GAS, "WLD", { gas: v.id }),
        ...(drill[v.id] ? { drill: drill[v.id] } : {}),
      })),
      short,
      decimals,
      true,
    ),
    drills: [
      { label: "Where methane comes from", to: "methane" },
      { label: "Carbon dioxide from fuel and land", to: "co2" },
    ],
    credit: credit(GHG_GAS),
    indicators: [GHG_GAS],
  };
}

export function methane(): Built {
  const ind = indicator(CH4_SHARE);
  const year = latestPeriod(CH4_SHARE);
  const rows = dimValues(CH4_SHARE, "sector")
    .map((v) => ({ v, h: headline(CH4_SHARE, "WLD", { sector: v.id }, year) }))
    .sort((a, b) => b.h.value - a.h.value);
  const top = rows[0];
  return {
    id: "methane",
    parent: "gases",
    crumb: "Methane",
    kicker: `${top.v.label} is the largest source of methane`,
    headline: top.h,
    sentence: `of the world's methane came from ${top.v.label.toLowerCase()} in ${year}, as FAO counts it.`,
    chart: bars(
      rows.map((r) => ({ key: r.v.id, label: r.v.label, value: r.h.value, colour: SECTOR_COLOURS[r.v.id] ?? "#5f5f5f" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      "FAO's shares of all methane, by IPCC sector.",
    ),
    drills: [crossDrill("Methane from farm animals", "food", food.node("animals"))],
    credit: credit(CH4_SHARE),
    indicators: [CH4_SHARE],
  };
}

function ghgCountryCodes(): string[] {
  return ranking(GHG_TOTAL, latestPeriod(GHG_TOTAL))
    .slice(0, TOP)
    .map((r) => r.entity);
}

export function ghgCountries(): Built {
  const { short, decimals } = u(GHG_TOTAL);
  const year = latestPeriod(GHG_TOTAL);
  const ranked = ranking(GHG_TOTAL, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "ghg-countries",
    parent: "root",
    crumb: "By country",
    kicker: "Which countries emit the most greenhouse gases",
    headline: headline(GHG_TOTAL, top[0].entity, {}, year),
    sentence: `of all greenhouse gases from ${entityName(top[0].entity)} in ${year}, the most of any country, including land use (FAO). Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: "#3d3d3d", drill: `g-${r.entity}` })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, all greenhouse gases including land use.`,
    ),
    drills: [{ label: "Each country's average per person", to: "ghg-per-person" }],
    credit: credit(GHG_TOTAL),
    indicators: [GHG_TOTAL],
  };
}

/** `co2View` is true when the carbon dioxide part of the chapter has this country's view (c-<iso>). */
export function ghgCountry(iso: string, co2View: boolean): Built {
  const { short, decimals } = u(GHG_SECTOR);
  const name = entityName(iso);
  const h = headline(GHG_TOTAL, iso);
  return {
    id: `g-${iso}`,
    parent: "ghg-countries",
    crumb: name,
    kicker: `${name}: greenhouse gases by sector`,
    headline: h,
    sentence: `of all greenhouse gases from ${name} in ${h.period}, including land use (FAO). The bands add up to the total.`,
    chart: area(sectorSeries(iso), short, decimals, true),
    drills: co2View ? [{ label: "Its carbon dioxide, by fuel", to: `c-${iso}` }] : [],
    credit: credit(GHG_TOTAL, GHG_SECTOR),
    indicators: [GHG_TOTAL, GHG_SECTOR],
  };
}

export function ghgPerPerson(): Built {
  const ind = indicator(GHG_PER_CAPITA);
  const year = latestPeriod(GHG_PER_CAPITA);
  const largest = new Set(ghgCountryCodes());
  const rows = ranking(GHG_PER_CAPITA, year).filter((r) => largest.has(r.entity));
  const h = headline(GHG_PER_CAPITA, "WLD", {}, year);
  return {
    id: "ghg-per-person",
    parent: "root",
    crumb: "Average per person",
    kicker: "Each country's average per person",
    headline: h,
    sentence: `of greenhouse gases per person, the world average in ${year} (FAO). Each bar is a large emitter's national total divided by its people, not any one person's footprint.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: "#3d3d3d" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${rows.length} countries with the largest total greenhouse gas emissions, ranked by their national average per person.`,
    ),
    drills: [{ label: "One person's footprint", to: "footprint" }],
    credit: credit(GHG_PER_CAPITA),
    indicators: [GHG_PER_CAPITA],
  };
}

export function footprint(): Built {
  const { short, decimals } = u(SE_BY_AREA);
  const h = headline(SE_TOTAL, "SWE");
  const areas = dimValues(SE_BY_AREA, "area");
  return {
    id: "footprint",
    parent: "root",
    crumb: "One person's footprint",
    kicker: "What one person's footprint is made of: Sweden",
    headline: h,
    sentence: `per person in Sweden in ${h.period}, counting everything people there consume, wherever it was made (Naturvårdsverket). Food, transport, housing and other goods are household spending; public services and investment are shared. Flights abroad are undercounted.`,
    chart: area(
      areas.map((v, i) => ({ key: v.id, label: v.label, colour: AREA_COLOURS[i % AREA_COLOURS.length], points: points(SE_BY_AREA, "SWE", { area: v.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "The UK's footprint, by use", to: "footprint-uk" }, crossDrill("Where food's emissions come from", "food", food.node("stages"))],
    credit: credit(SE_TOTAL, SE_BY_AREA),
    indicators: [SE_TOTAL, SE_BY_AREA],
  };
}

export function footprintUk(): Built {
  const ind = indicator(UK_BY_USE);
  const year = latestPeriod(UK_BY_USE);
  const rows = dimValues(UK_BY_USE, "end_use")
    .map((v) => ({ v, h: headline(UK_BY_USE, "GBR", { end_use: v.id }, year) }))
    .sort((a, b) => b.h.value - a.h.value);
  const h = headline(UK_PER_CAPITA, "GBR");
  return {
    id: "footprint-uk",
    parent: "footprint",
    crumb: "United Kingdom",
    kicker: "The UK's footprint, by what it is used for",
    headline: h,
    sentence: `per person in the UK in ${h.period}, counting what UK residents consume wherever it was made (Defra and the University of Leeds). The bars split the whole UK footprint by use; food and drink excludes restaurants.`,
    chart: bars(
      rows.map((r) => ({ key: r.v.id, label: r.v.label, value: r.h.value, colour: "#2166ac" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      "The UK's whole consumption footprint, by end use. Flights are inside transport.",
    ),
    drills: [{ label: "Households' own spending, by product", to: "footprint-uk-households" }],
    credit: credit(UK_PER_CAPITA, UK_BY_USE),
    indicators: [UK_PER_CAPITA, UK_BY_USE],
  };
}

/**
 * UK households' footprint by product group: the largest few as separate lines, never stacked, since Defra publishes
 * no total of a chosen few and the rest are not lumped into a band of our own.
 */
export function footprintUkHouseholds(): Built {
  const { short, decimals } = u(UK_HOUSEHOLDS);
  const year = latestPeriod(UK_HOUSEHOLDS);
  const ranked = indicator(UK_HOUSEHOLDS)
    .observations.filter((o) => o.entity === "GBR" && o.period === year && o.value !== null)
    .map((o) => ({ product: o.dims.product, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.product.localeCompare(b.product));
  const top = ranked.slice(0, UK_LINES);
  const largest = dimLabel(UK_HOUSEHOLDS, "product", top[0].product);
  return {
    id: "footprint-uk-households",
    parent: "footprint-uk",
    crumb: "Households, by product",
    kicker: "What UK households' own spending emits",
    headline: headline(UK_HOUSEHOLDS, "GBR", { product: top[0].product }, year),
    sentence: `from UK households' ${largest.toLowerCase()} in ${year}, the largest of the ${ranked.length} product groups Defra publishes (Defra and the University of Leeds). The lines are the ${top.length} largest in ${year}. Government, investment and charities are not included, and Defra says its earliest years are less certain.`,
    chart: line(
      top.map((r, i) => ({
        key: r.product,
        label: dimLabel(UK_HOUSEHOLDS, "product", r.product),
        colour: AREA_COLOURS[i % AREA_COLOURS.length],
        points: points(UK_HOUSEHOLDS, "GBR", { product: r.product }),
      })),
      short,
      decimals,
    ),
    drills: [],
    credit: credit(UK_HOUSEHOLDS),
    indicators: [UK_HOUSEHOLDS],
  };
}

export function ghgIds(): string[] {
  return ["root", "food-system", "gases", "methane", "ghg-countries", ...ghgCountryCodes().map((c) => `g-${c}`), "ghg-per-person", "footprint", "footprint-uk", "footprint-uk-households"];
}

export function buildGhg(id: string, co2View: (iso: string) => boolean): Built | null {
  if (id === "root") return ghgRoot();
  if (id === "food-system") return foodSystem();
  if (id === "gases") return gases();
  if (id === "methane") return methane();
  if (id === "ghg-countries") return ghgCountries();
  if (id === "ghg-per-person") return ghgPerPerson();
  if (id === "footprint") return footprint();
  if (id === "footprint-uk") return footprintUk();
  if (id === "footprint-uk-households") return footprintUkHouseholds();
  const g = id.match(/^g-([A-Z0-9_]+)$/);
  if (g) return ghgCountry(g[1], co2View(g[1]));
  return null;
}

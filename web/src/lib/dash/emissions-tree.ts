import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { area, bars, type Built, chapter, credit, headline, latestPeriod, line, points as allPoints, ranking } from "@/lib/dash/kit";
import type { Dims } from "@/lib/dash/kit";
import { buildGhg, ghgIds } from "@/lib/dash/ghg-nodes";
import type { Drill, Series } from "@/lib/dash/types";

/**
 * The emissions chapter as a drill-down tree. Every node is one idea (one chart, one traced headline) and each
 * child is one more disaggregation. It opens on all greenhouse gases by sector (ghg-nodes.ts: food and farming, by
 * gas, by country, per person, one person's footprint); carbon dioxide alone ("co2", Global Carbon Project) then goes
 * by source → by fuel → one fuel → which countries → one country → its fuels, per person, or counting its imports;
 * to fossil fuels alone on the Global Carbon Budget's headline basis (its projection and the projected change); and
 * to everything emitted since the first year of the record → who emitted it.
 * Values are only selected and ordered here, never computed.
 */

const TOTAL = "emissions.gcb-2025.total-co2-global"; // fossil + land use, Gt CO2/yr, 1959–
const BUDGET = "emissions.gcb-2025.budget-global"; // GCB components, Gt CO2/yr
const FOSSIL_NET = "emissions.gcb-2025.fossil-net-global"; // GCB headline fossil value (net of cement carbonation), Gt CO2/yr, 1959–
const FOSSIL_PROJECTION = "emissions.gcb-2025.fossil-net-2025-projection"; // GCB projection for the year after the last final value
const FOSSIL_GROWTH = "emissions.gcb-2025.fossil-growth-2025-projection"; // GCB projected change from the year before, percent
const BY_FUEL = "emissions.gcp-2025.fossil-co2-by-fuel"; // Mt CO2/yr, 1750–, every country
const BY_COUNTRY = "emissions.gcp-2025.fossil-co2-by-country";
const PER_CAPITA = "emissions.gcp-2025.fossil-co2-per-capita";
const ACCOUNTING = "emissions.gcb-2025.territorial-vs-consumption";
const CUMULATIVE = "emissions.gcp-2025.fossil-co2-cumulative"; // running total since the file's first year, Gt CO2
const CUMULATIVE_SHARE = "emissions.gcp-2025.fossil-co2-cumulative-share"; // each country's running total over the world's, percent

const FROM = 1850;
const TOP = 15;
/** The window of the projected-change view: the recent decades, so the latest years' slope is visible (a display choice). */
const RECENT = 2000;
/** International aviation and shipping: the producer's own entities, which hold shares of the running total. */
const BUNKERS = ["INTL_AIR", "INTL_SEA"];

/** Fuel colours: distinct, colour-blind-safe in combination, each at least 3:1 on white. */
export const FUELS: { id: string; label: string; colour: string }[] = [
  { id: "coal", label: "Coal", colour: "#2b2b2b" },
  { id: "oil", label: "Oil", colour: "#8c510a" },
  { id: "gas", label: "Gas", colour: "#2166ac" },
  { id: "cement", label: "Cement", colour: "#6b6b6b" },
  { id: "flaring", label: "Flaring", colour: "#c75400" },
  { id: "other", label: "Other industry", colour: "#7b5ea7" },
];
const FOSSIL_COLOUR = "#b2182b";
const LAND_COLOUR = "#1b7837";
const WORLD_COLOUR = "#9aa0a6";
const COUNTRY_COLOUR = "#b2182b";

function latestYear(id: string): string {
  return latestPeriod(id);
}

/** Series from 1850 unless asked otherwise (the fuel series reach back to 1750, when the numbers are tiny). */
function points(id: string, entity: string, dims: Dims = {}, from = FROM) {
  return allPoints(id, entity, dims, from);
}

// --- nodes ---------------------------------------------------------------------------------------------------

/** Carbon dioxide alone, on the Global Carbon Project's basis: one level under all greenhouse gases (ghg-nodes.ts). */
function co2(): Built {
  const ind = indicator(TOTAL);
  const year = latestYear(TOTAL);
  return {
    id: "co2",
    parent: "root",
    crumb: "Carbon dioxide",
    kicker: "Carbon dioxide from fuel and from clearing land",
    headline: headline(TOTAL, "WLD"),
    sentence: `from fossil fuels, cement and clearing land in ${year} (Global Carbon Budget). It counts land use differently from FAO's total one level up, so the two are never added together.`,
    chart: area([{ key: "total", label: "Fossil fuels, cement and land use", colour: FOSSIL_COLOUR, points: points(TOTAL, "WLD", {}, 0), drill: "sources" }], ind.unit.short, ind.display.decimals, false),
    drills: [
      { label: "Split by source", to: "sources" },
      { label: "Fossil fuels alone", to: "co2-fossil" },
      { label: "Split by country", to: "countries" },
      { label: "Per person", to: "per-person" },
      { label: `Everything since ${cumulativeSince()}`, to: "cumulative" },
    ],
    credit: credit(TOTAL),
    indicators: [TOTAL],
  };
}

/**
 * A Global Carbon Budget projection for the year after its last final value. Once the series has a value for that
 * year the projection is out of date, and the build fails rather than show it as the newest number.
 */
function projection(id: string) {
  const h = headline(id, "WLD");
  if (h.status !== "projection") throw new Error(`${id}: expected a projection, the value is ${h.status}`);
  if (indicator(FOSSIL_NET).observations.some((o) => o.entity === "WLD" && o.period === h.period && o.value !== null)) {
    throw new Error(`${id}: ${FOSSIL_NET} now has a value for ${h.period}, so the projection for it is out of date`);
  }
  return h;
}

/** Fossil carbon dioxide alone, on the Global Carbon Budget's headline basis, led by its projection. */
function co2Fossil(): Built {
  const ind = indicator(FOSSIL_NET);
  const h = projection(FOSSIL_PROJECTION);
  const last = latestYear(FOSSIL_NET);
  return {
    id: "co2-fossil",
    parent: "co2",
    crumb: "Fossil fuels alone",
    kicker: `Fossil carbon dioxide projected for ${h.period}`,
    headline: h,
    sentence: `projected for ${h.period} by the Global Carbon Budget from data for part of that year: fossil fuels, cement and other industry, less the carbon dioxide cement takes back up as it ages. The line shows each year up to ${last}.`,
    chart: area([{ key: "fossil-net", label: "Fossil fuels and industry", colour: FOSSIL_COLOUR, points: points(FOSSIL_NET, "WLD", {}, 0), drill: "co2-fossil-growth" }], ind.unit.short, ind.display.decimals, false),
    drills: [{ label: "Change from the year before", to: "co2-fossil-growth" }],
    credit: credit(FOSSIL_PROJECTION, FOSSIL_NET),
    indicators: [FOSSIL_PROJECTION, FOSSIL_NET],
  };
}

/** The projected change from the year before; the direction in the kicker is the sign of the published value. */
function co2FossilGrowth(): Built {
  const ind = indicator(FOSSIL_NET);
  const h = projection(FOSSIL_GROWTH);
  const direction = h.value > 0 ? "rise" : h.value < 0 ? "fall" : "hold level";
  const pts = points(FOSSIL_NET, "WLD", {}, RECENT);
  return {
    id: "co2-fossil-growth",
    parent: "co2-fossil",
    crumb: "Change from the year before",
    kicker: `Fossil carbon dioxide projected to ${direction} in ${h.period}`,
    headline: h,
    sentence: `projected change from the year before, made from data for part of ${h.period} (Global Carbon Budget, which publishes a range around it). The line shows each year since ${pts[0][0]}.`,
    chart: area([{ key: "fossil-net", label: "Fossil fuels and industry", colour: FOSSIL_COLOUR, points: pts }], ind.unit.short, ind.display.decimals, false),
    drills: [{ label: "Split by fuel", to: "fuels" }],
    credit: credit(FOSSIL_GROWTH, FOSSIL_NET),
    indicators: [FOSSIL_GROWTH, FOSSIL_NET],
  };
}

/** The first year of the running totals: the world's first value in the file. */
function cumulativeSince(): number {
  const first = allPoints(CUMULATIVE, "WLD").find((p) => p[1] !== null);
  if (!first) throw new Error(`${CUMULATIVE}: no world value`);
  return first[0];
}

function cumulative(): Built {
  const ind = indicator(CUMULATIVE);
  const h = headline(CUMULATIVE, "WLD");
  const since = cumulativeSince();
  return {
    id: "cumulative",
    parent: "co2",
    crumb: `Since ${since}`,
    kicker: `All the fossil carbon dioxide emitted since ${since}`,
    headline: h,
    sentence: `from fossil fuels and cement from ${since} to ${h.period}: each year's Global Carbon Project value, added up by Environment Dashboard. Clearing land is not included.`,
    chart: area([{ key: "cumulative", label: "World, running total", colour: FOSSIL_COLOUR, points: allPoints(CUMULATIVE, "WLD"), drill: "cumulative-countries" }], ind.unit.short, ind.display.decimals, false),
    drills: [{ label: "Which countries emitted it", to: "cumulative-countries" }],
    credit: credit(CUMULATIVE),
    indicators: [CUMULATIVE],
  };
}

function cumulativeCountries(): Built {
  const ind = indicator(CUMULATIVE_SHARE);
  const year = latestYear(CUMULATIVE_SHARE);
  const since = cumulativeSince();
  const ranked = ranking(CUMULATIVE_SHARE, year);
  const top = ranked.slice(0, TOP);
  const name = entityName(top[0].entity);
  const withView = new Set(countryCodes());
  const bunkers = BUNKERS.every((e) => indicator(CUMULATIVE_SHARE).observations.some((o) => o.entity === e && o.period === year && o.value !== null));
  return {
    id: "cumulative-countries",
    parent: "cumulative",
    crumb: "By country",
    kicker: `${name} has emitted the most since ${since}`,
    headline: headline(CUMULATIVE_SHARE, top[0].entity, {}, year),
    sentence: `was ${name}'s share of all the fossil carbon dioxide emitted from ${since} to ${year}, the largest of any country. Each share is a running total over the world's, worked out by Environment Dashboard from Global Carbon Project data. Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: COUNTRY_COLOUR, ...(withView.has(r.entity) ? { drill: `c-${r.entity}` } : {}) })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories with data, by their share of all fossil carbon dioxide from ${since} to ${year}.${bunkers ? " International flights and shipping hold shares of their own." : ""}`,
    ),
    drills: [{ label: "Emitted each year instead", to: "countries" }],
    credit: credit(CUMULATIVE_SHARE),
    indicators: [CUMULATIVE_SHARE],
  };
}

function sources(): Built {
  const ind = indicator(BUDGET);
  const s: Series[] = [
    { key: "fossil", label: "Fossil fuels and industry", colour: FOSSIL_COLOUR, points: points(BUDGET, "WLD", { component: "fossil" }, 0), drill: "fuels" },
    { key: "land-use-change", label: "Land-use change", colour: LAND_COLOUR, points: points(BUDGET, "WLD", { component: "land-use-change" }, 0) },
  ];
  return {
    id: "sources",
    parent: "co2",
    crumb: "By source",
    kicker: "Carbon dioxide from burning fuel, or from clearing land",
    headline: headline(BUDGET, "WLD", { component: "fossil" }),
    sentence: `from fossil fuels and industry; the green band is clearing and burning land. The first view's total also subtracts the carbon cement takes back up as it ages.`,
    chart: area(s, ind.unit.short, ind.display.decimals, true),
    drills: [{ label: "Split fossil fuels by fuel", to: "fuels" }],
    credit: credit(BUDGET),
    indicators: [BUDGET],
  };
}

function fuels(): Built {
  const ind = indicator(BY_FUEL);
  const year = latestYear(BY_FUEL);
  const order = ranking(BY_FUEL, year, {}).length; // ensures data exists
  if (!order) throw new Error("no fuel data");
  const s: Series[] = FUELS.map((f) => ({ key: f.id, label: f.label, colour: f.colour, points: points(BY_FUEL, "WLD", { fuel: f.id }), drill: `fuel-${f.id}` }));
  const largest = FUELS.map((f) => ({ f, v: headline(BY_FUEL, "WLD", { fuel: f.id }, year).value })).sort((a, b) => b.v - a.v)[0].f;
  return {
    id: "fuels",
    parent: "sources",
    crumb: "By fuel",
    kicker: `${largest.label} is the largest source`,
    headline: headline(BY_FUEL, "WLD", { fuel: largest.id }, year),
    sentence: `from ${largest.label.toLowerCase()}, in ${year}. Select a fuel to follow it.`,
    chart: area(s, ind.unit.short, ind.display.decimals, true),
    drills: FUELS.map((f) => ({ label: f.label, to: `fuel-${f.id}` })),
    credit: credit(BY_FUEL),
    indicators: [BY_FUEL],
  };
}

function fuel(f: (typeof FUELS)[number]): Built {
  const ind = indicator(BY_FUEL);
  const year = latestYear(BY_FUEL);
  return {
    id: `fuel-${f.id}`,
    parent: "fuels",
    crumb: f.label,
    kicker: `${f.label}, worldwide`,
    headline: headline(BY_FUEL, "WLD", { fuel: f.id }, year),
    sentence: `from ${f.label.toLowerCase()} worldwide, in ${year}.`,
    chart: area([{ key: f.id, label: f.label, colour: f.colour, points: points(BY_FUEL, "WLD", { fuel: f.id }) }], ind.unit.short, ind.display.decimals, false),
    drills: [{ label: `Which countries?`, to: `fuel-${f.id}-countries` }],
    credit: credit(BY_FUEL),
    indicators: [BY_FUEL],
  };
}

function fuelCountries(f: (typeof FUELS)[number]): Built {
  const ind = indicator(BY_FUEL);
  const year = latestYear(BY_FUEL);
  const ranked = ranking(BY_FUEL, year, { fuel: f.id });
  const top = ranked.slice(0, TOP);
  return {
    id: `fuel-${f.id}-countries`,
    parent: `fuel-${f.id}`,
    crumb: "By country",
    kicker: `Which countries emit the most from ${f.label.toLowerCase()}`,
    headline: headline(BY_FUEL, top[0].entity, { fuel: f.id }, year),
    sentence: `from ${f.label.toLowerCase()} in ${entityName(top[0].entity)}, the largest, in ${year}. Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: f.colour, drill: `c-${r.entity}-fuels` })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories with data, in ${year}.`,
    ),
    drills: [],
    credit: credit(BY_FUEL),
    indicators: [BY_FUEL],
  };
}

function countries(): Built {
  const ind = indicator(BY_COUNTRY);
  const year = latestYear(BY_COUNTRY);
  const ranked = ranking(BY_COUNTRY, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "countries",
    parent: "co2",
    crumb: "By country",
    kicker: "Which countries emit the most carbon dioxide",
    headline: headline(BY_COUNTRY, top[0].entity, {}, year),
    sentence: `from fossil fuels in ${entityName(top[0].entity)}, the largest emitter, in ${year}. Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: COUNTRY_COLOUR, drill: `c-${r.entity}` })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories with data, in ${year}.`,
    ),
    drills: [
      { label: "Per person instead", to: "per-person" },
      { label: `Since ${cumulativeSince()} instead`, to: "cumulative-countries" },
    ],
    credit: credit(BY_COUNTRY),
    indicators: [BY_COUNTRY],
  };
}

function perPerson(): Built {
  const ind = indicator(PER_CAPITA);
  const year = latestYear(PER_CAPITA);
  const biggest = ranking(BY_COUNTRY, year).slice(0, TOP).map((r) => r.entity);
  const rows = ranking(PER_CAPITA, year).filter((r) => biggest.includes(r.entity));
  return {
    id: "per-person",
    parent: "co2",
    crumb: "Average per person",
    kicker: "Each country's average per person",
    headline: headline(PER_CAPITA, "WLD", {}, year),
    sentence: `from fossil fuels, the world average in ${year}. Each bar is a large emitter's national average: its total divided by its people, not any one person's footprint.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: COUNTRY_COLOUR, drill: `c-${r.entity}-per-person` })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `The ${TOP} countries with the largest total fossil carbon dioxide in ${year}, ranked by emissions per person.`,
    ),
    drills: [{ label: "Totals instead", to: "countries" }],
    credit: credit(PER_CAPITA, BY_COUNTRY),
    indicators: [PER_CAPITA, BY_COUNTRY],
  };
}

function country(iso: string): Built {
  const ind = indicator(BY_COUNTRY);
  const name = entityName(iso);
  const year = latestYear(BY_COUNTRY);
  const drills: Drill[] = [];
  if (fuelsIn(iso).length > 0) drills.push({ label: "Split by fuel", to: `c-${iso}-fuels` });
  if (hasPerCapita(iso)) drills.push({ label: "Per person", to: `c-${iso}-per-person` });
  if (hasAccounting(iso)) drills.push({ label: "Counting what it imports", to: `c-${iso}-consumption` });
  return {
    id: `c-${iso}`,
    parent: "countries",
    crumb: name,
    kicker: name,
    headline: headline(BY_COUNTRY, iso, {}, year),
    sentence: `from fossil fuels in ${name}, in ${year}.`,
    chart: area([{ key: iso, label: name, colour: COUNTRY_COLOUR, points: points(BY_COUNTRY, iso) }], ind.unit.short, ind.display.decimals, false),
    drills,
    credit: credit(BY_COUNTRY),
    indicators: [BY_COUNTRY],
  };
}

function countryFuels(iso: string): Built {
  const ind = indicator(BY_FUEL);
  const name = entityName(iso);
  const year = latestYear(BY_FUEL);
  const present = fuelsIn(iso);
  const largest = present.sort((a, b) => b.value - a.value || a.fuel.id.localeCompare(b.fuel.id))[0].fuel;
  return {
    id: `c-${iso}-fuels`,
    parent: `c-${iso}`,
    crumb: "By fuel",
    kicker: `${name}: ${largest.label.toLowerCase()} is the largest source`,
    headline: headline(BY_FUEL, iso, { fuel: largest.id }, year),
    sentence: `from ${largest.label.toLowerCase()} in ${name}, in ${year}.`,
    chart: area(
      present.map(({ fuel: f }) => ({ key: f.id, label: f.label, colour: f.colour, points: points(BY_FUEL, iso, { fuel: f.id }) })),
      ind.unit.short,
      ind.display.decimals,
      true,
    ),
    drills: hasPerCapita(iso) ? [{ label: "Per person", to: `c-${iso}-per-person` }] : [],
    credit: credit(BY_FUEL),
    indicators: [BY_FUEL],
  };
}

function countryPerPerson(iso: string): Built {
  const ind = indicator(PER_CAPITA);
  const name = entityName(iso);
  return {
    id: `c-${iso}-per-person`,
    parent: `c-${iso}`,
    crumb: "Average per person",
    kicker: `${name}: the average per person, against the world`,
    headline: headline(PER_CAPITA, iso),
    sentence: `from fossil fuels, ${name}'s national average in ${headline(PER_CAPITA, iso).period}: its total divided by its people. The grey line is the world average.`,
    chart: line(
      [
        { key: iso, label: name, colour: COUNTRY_COLOUR, points: points(PER_CAPITA, iso) },
        { key: "WLD", label: "World average", colour: WORLD_COLOUR, points: points(PER_CAPITA, "WLD") },
      ],
      ind.unit.short,
      ind.display.decimals,
    ),
    drills: [{ label: "Back to the total", to: `c-${iso}` }],
    credit: credit(PER_CAPITA),
    indicators: [PER_CAPITA],
  };
}

/** The fuels with a value for the country in the latest year (a fuel the producer has no row for is not shown). */
function fuelsIn(iso: string): { fuel: (typeof FUELS)[number]; value: number }[] {
  const year = latestYear(BY_FUEL);
  const obs = indicator(BY_FUEL).observations.filter((o) => o.entity === iso && o.period === year && o.value !== null);
  return FUELS.flatMap((fuel) => {
    const o = obs.find((x) => x.dims.fuel === fuel.id);
    return o ? [{ fuel, value: o.value as number }] : [];
  });
}

function hasPerCapita(iso: string): boolean {
  return indicator(PER_CAPITA).observations.some((o) => o.entity === iso && o.value !== null);
}

function hasAccounting(iso: string): boolean {
  return indicator(ACCOUNTING).observations.some((o) => o.entity === iso && o.dims.accounting === "consumption" && o.value !== null);
}

function countryConsumption(iso: string): Built {
  const ind = indicator(ACCOUNTING);
  const name = entityName(iso);
  return {
    id: `c-${iso}-consumption`,
    parent: `c-${iso}`,
    crumb: "Counting imports",
    kicker: `${name}: produced at home, or consumed at home`,
    headline: headline(ACCOUNTING, iso, { accounting: "consumption" }),
    sentence: `in everything ${name} consumes, including goods made abroad, in ${headline(ACCOUNTING, iso, { accounting: "consumption" }).period}.`,
    chart: line(
      [
        { key: "territorial", label: "Emitted within its borders", colour: COUNTRY_COLOUR, points: points(ACCOUNTING, iso, { accounting: "territorial" }, 0) },
        { key: "consumption", label: "In what it consumes", colour: "#2166ac", points: points(ACCOUNTING, iso, { accounting: "consumption" }, 0) },
      ],
      ind.unit.short,
      ind.display.decimals,
    ),
    drills: [{ label: "Back to the total", to: `c-${iso}` }],
    credit: credit(ACCOUNTING),
    indicators: [ACCOUNTING],
  };
}

// --- the tree ------------------------------------------------------------------------------------------------

/** Every country or territory with a fossil CO2 value in the latest year. */
function countryCodes(): string[] {
  return ranking(BY_COUNTRY, latestYear(BY_COUNTRY)).map((r) => r.entity);
}

function ids(): string[] {
  const out = [...ghgIds(), "co2", "co2-fossil", "co2-fossil-growth", "sources", "fuels", "countries", "per-person", "cumulative", "cumulative-countries"];
  for (const f of FUELS) out.push(`fuel-${f.id}`, `fuel-${f.id}-countries`);
  for (const iso of countryCodes()) {
    out.push(`c-${iso}`);
    if (fuelsIn(iso).length > 0) out.push(`c-${iso}-fuels`);
    if (hasPerCapita(iso)) out.push(`c-${iso}-per-person`);
    if (hasAccounting(iso)) out.push(`c-${iso}-consumption`);
  }
  return out;
}

function build(id: string): Built {
  const ghg = buildGhg(id, (iso) => countryCodes().includes(iso));
  if (ghg) return ghg;
  if (id === "co2") return co2();
  if (id === "co2-fossil") return co2Fossil();
  if (id === "co2-fossil-growth") return co2FossilGrowth();
  if (id === "cumulative") return cumulative();
  if (id === "cumulative-countries") return cumulativeCountries();
  if (id === "sources") return sources();
  if (id === "fuels") return fuels();
  if (id === "countries") return countries();
  if (id === "per-person") return perPerson();
  const fm = id.match(/^fuel-([a-z]+)(-countries)?$/);
  if (fm) {
    const f = FUELS.find((x) => x.id === fm[1]);
    if (!f) throw new Error(`unknown fuel node ${id}`);
    return fm[2] ? fuelCountries(f) : fuel(f);
  }
  const cm = id.match(/^c-([A-Z0-9_]+)(-fuels|-per-person|-consumption)?$/);
  if (cm) {
    const [, iso, kind] = cm;
    if (!kind) return country(iso);
    if (kind === "-fuels") return countryFuels(iso);
    if (kind === "-per-person") return countryPerPerson(iso);
    return countryConsumption(iso);
  }
  throw new Error(`unknown emissions node ${id}`);
}

export const emissions = chapter(ids, build);

import "server-only";

import type { Observation } from "@/gen/hey-api/types.gen";
import { indicator } from "@/lib/data";
import { action } from "@/lib/dash/action-tree";
import { energy } from "@/lib/dash/energy-tree";
import { entityName, isPlace } from "@/lib/dash/entities";
import { food } from "@/lib/dash/food-tree";
import { area, bars, type Built, chapter, credit, crossDrill, type Dims, dimLabel, headline, latestPeriod, line, matches, points, ranking } from "@/lib/dash/kit";
import type { Bar, Drill } from "@/lib/dash/types";
import { formatPeriod, formatReadable } from "@/lib/format";
import { activityIds, buildActivity, isActivityNode, rootNode, sharesNode } from "@/lib/dash/zero-activities";

/**
 * Getting to zero: the frameworks of Bill Gates's "How to Avoid a Climate Disaster" (2021), each shown from primary
 * producers (his own figures are Rhodium Group's and Breakthrough Energy's, which cannot be republished). It opens on
 * the world's emissions grouped into his five activities (zero-activities.ts), and its cards are his five questions:
 * how much of the total, the plan for cement (making things), how much power, how much space, and how much it costs
 * (the Green Premium). Then the strategy: net-zero targets, electrifying, capturing what is left, research budgets
 * and adapting. Values are only selected and labelled here, never computed; a comparison word ("more", "less") is
 * derived from the two published values it compares.
 */

// --- indicators ------------------------------------------------------------------------------------------------

const POWER_WORLD = "power-scale.ember.world-electricity";
const POWER_WORLD_ENERGY = "power-scale.eia.world-primary-energy";
const DEMAND_WORLD = "electricity-demand.ember.world";
const POWER_LONDON = "power-scale.desnz.london";
const USE_LONDON = "electricity-use.desnz.london";
const VOGTLE = "capacity.eia.vogtle";
const POWER_HOME_US = "power-scale.eia-recs-2020.us-household";
const POWER_HOME_GB = "power-scale.desnz.gb-household";
const USE_HOME_US = "electricity-use.eia-recs-2020.us-household";
const USE_HOME_GB = "electricity-use.desnz.gb-household";

const LAND = "land-use-intensity.lovering-2022.by-source";
const DENSITY = "power-density.noland-2022.by-source";

const GP_STEEL = "green-premium.iea-etp-2026.steel";
const GP_CEMENT = "green-premium.iea-etp-2026.cement";
const GP_STEEL_USD = "green-premium.iea-etp-2026.steel-usd";
const GP_CEMENT_USD = "green-premium.iea-etp-2026.cement-usd";
const GP_UREA = "green-premium.iea-etp-2026.urea";
const GP_AMMONIA_IEA = "green-premium.iea-ghr-2025.ammonia";
const GP_METHANOL = "green-premium.iea-ghr-2025.methanol";
const GP_STEEL_H2 = "green-premium.iea-ghr-2025.steel";
const GP_SHIPPING = "green-premium.iea-efuels-2023.shipping";
const GP_CLINKER = "green-premium.cemcap-2019.clinker";
const CLINKER_COST = "clinker-cost.cemcap-2019.by-technology";
const LCOE_US = "lcoe.eia-aeo-2026.new-plants-us";
const LCOE_UK = "lcoe.desnz-2025.new-plants-uk";
const GP_AMMONIA = "green-premium.arnaiz-del-pozo-2022.ammonia";
const GP_HEAT_GB = "green-premium.rosenow-2025.heating";
const GP_HEAT_WORLD = "green-premium.drawdown-explorer.heating";
const GP_CARS_KM = "green-premium.furch-2022.cars-per-km";
const GP_CARS_LIFE = "green-premium.furch-2022.cars-lifetime";
const GP_TRUCKS = "green-premium.rajalehto-helo-2025.trucks";
const GP_JET = "green-premium.sacchi-2023.jet-fuel";
const GP_MEAT = "green-premium.falkenberg-2023.meat";
const GP_MEAT_RATIO = "green-premium.siegrist-2024.meat-substitutes";

const NZ_COUNTS = "net-zero.nzt-2025.countries-by-status";
const NZ_COUNTRY = "net-zero.nzt-2025.target-by-country";
/** All greenhouse gases by country, including land use (FAO): only used to pick and order the largest emitters. */
const GHG = "ghg.faostat.total";

const ELEC_SHARE = "electricity.eurostat.share-of-final-energy";
const CCS_OPERATING = "ccus.iea.operating-capture-capacity";
const CCS_STATUS = "ccus.iea.capture-capacity-by-status";
const CCS_PROJECTS = "ccus.iea.capture-projects-by-status";
const CDR_NOVEL = "cdr.socdr-3.novel-by-method";
const CDR_FOREST = "cdr.socdr-3.conventional-forest";
const RD_OECD = "rd-budget.oecd.energy";
const RD_EU = "rd-budget.eurostat.energy";

const FARMS = "farms.faostat-wcad.holdings";
const FARMS_BY_SIZE = "farms.faostat-wcad.holdings-by-land-size";
const FARM_AREA_BY_SIZE = "farms.faostat-wcad.area-by-land-size";

// --- colours ---------------------------------------------------------------------------------------------------

const CLEAN = "#1b7837";
const FOSSIL = "#8b8b86";
const CAPTURE = "#2166ac";
const PREMIUM = "#b2182b";
const NEUTRAL = "#2166ac";
/** The two sides of a Green Premium, and fossil with its carbon dioxide captured between them. */
const SIDE_COLOUR: Record<string, string> = { conventional: FOSSIL, "conventional-with-capture": CAPTURE, "low-carbon": CLEAN };
/** Net Zero Tracker's statuses, from firmest to none. */
const STATUS_COLOUR: Record<string, string> = {
  "achieved-self-declared": "#00441b",
  "in-law": "#1b7837",
  "in-policy-document": "#5aae61",
  "declaration-pledge": "#a6dba0",
  "proposed-in-discussion": "#d9f0d3",
  "other-end-target": "#f4a582",
  "no-target": "#b2182b",
};
const CCS_STATUS_COLOUR: Record<string, string> = { operational: CAPTURE, "under-construction": "#67a9cf", planned: "#d1e5f0" };

const TOP = 15;

// --- helpers ---------------------------------------------------------------------------------------------------

function u(id: string): { short: string; decimals: number; label: string } {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals, label: ind.unit.label };
}

/** The one observation for an entity, a dimension slice and (optionally) a period; two would be an error. */
function obs(id: string, entity: string, dims: Dims = {}, period?: string): Observation | undefined {
  const rows = indicator(id).observations.filter((o) => matches(o, entity, dims) && (period === undefined || o.period === period));
  if (rows.length > 1) throw new Error(`${id}: ${rows.length} observations for ${entity} ${JSON.stringify(dims)} ${period ?? ""}`);
  return rows[0];
}

function value(id: string, entity: string, dims: Dims = {}, period?: string): number | null {
  return obs(id, entity, dims, period)?.value ?? null;
}

function must(id: string, entity: string, dims: Dims = {}, period?: string): number {
  const v = value(id, entity, dims, period);
  if (v === null) throw new Error(`${id}: no value for ${entity} ${JSON.stringify(dims)} ${period ?? ""}`);
  return v;
}

function only(id: string): Observation {
  const rows = indicator(id).observations;
  if (rows.length !== 1 || rows[0].value === null) throw new Error(`${id}: expected exactly one published value`);
  return rows[0];
}

/** Words for a published cost against one or more published costs on the same basis: never a computed difference. */
function against(clean: number, others: number[]): "more than" | "less than" | "the same as" | "between" {
  if (others.every((o) => clean > o)) return "more than";
  if (others.every((o) => clean < o)) return "less than";
  if (others.every((o) => clean === o)) return "the same as";
  return "between";
}

function sideColour(side: string): string {
  const c = SIDE_COLOUR[side];
  if (!c) throw new Error(`zero: no colour for side ${side}`);
  return c;
}

const SIDE_LEGEND = [
  { label: "Fossil", colour: FOSSIL },
  { label: "Fossil with carbon capture", colour: CAPTURE },
  { label: "Low-carbon", colour: CLEAN },
];

function legendFor(sides: string[]): { label: string; colour: string }[] {
  const keys = ["conventional", "conventional-with-capture", "low-carbon"];
  return SIDE_LEGEND.filter((_, i) => sides.includes(keys[i]));
}

/** A published range as low end inside high end (the producer's two numbers), or one stated value. */
function rangeBar(key: string, label: string, low: number | null, high: number, drill?: string): Bar {
  return { key, label: low !== null && low !== high ? `${label} (from ${formatReadable(low, 0)})` : label, value: high, ...(low !== null && low !== high ? { inner: low } : {}), colour: PREMIUM, ...(drill ? { drill } : {}) };
}

// --- the five questions: how much power -----------------------------------------------------------------------

function power(): Built {
  const elec = headline(POWER_WORLD, "WLD");
  const { short, decimals } = u(POWER_WORLD);
  if (u(POWER_WORLD_ENERGY).short !== short) throw new Error("zero/power: the two world series are not in the same unit");
  return {
    id: "power",
    parent: "root",
    crumb: "How much power",
    kicker: "How much power: the whole world",
    headline: elec,
    sentence: `of electricity, on average through ${elec.period}: the world's electricity use (Ember) spread over every hour of the year. The upper line is all the energy the world uses, as the US EIA counts it. A terawatt is a billion kilowatts.`,
    chart: line(
      [
        { key: "electricity", label: "Electricity (Ember)", colour: CAPTURE, points: points(POWER_WORLD, "WLD"), drill: "power-world-year" },
        { key: "energy", label: "All energy (US EIA)", colour: FOSSIL, points: points(POWER_WORLD_ENERGY, "WLD") },
      ],
      short,
      decimals,
    ),
    drills: [
      { label: "A city", to: "power-city" },
      { label: "In a year", to: "power-world-year" },
    ],
    credit: credit(POWER_WORLD, POWER_WORLD_ENERGY),
    indicators: [POWER_WORLD, POWER_WORLD_ENERGY],
  };
}

function powerWorldYear(): Built {
  const h = headline(DEMAND_WORLD, "WLD");
  const { short, decimals } = u(DEMAND_WORLD);
  return {
    id: "power-world-year",
    parent: "power",
    crumb: "In a year",
    kicker: "The world's electricity in a year",
    headline: h,
    sentence: `of electricity used worldwide in ${h.period}, by Ember. Divided by the hours in the year, it is the average power one level up.`,
    chart: area([{ key: "demand", label: "World electricity demand", colour: CAPTURE, points: points(DEMAND_WORLD, "WLD") }], short, decimals, false),
    drills: [{ label: "A city", to: "power-city" }],
    credit: credit(DEMAND_WORLD),
    indicators: [DEMAND_WORLD],
  };
}

function powerCity(): Built {
  const london = headline(POWER_LONDON, "GBR_LONDON");
  const plant = only(VOGTLE);
  const { short, decimals } = u(POWER_LONDON);
  if (u(VOGTLE).short !== short) throw new Error("zero/power-city: London and Vogtle are not in the same unit");
  return {
    id: "power-city",
    parent: "power",
    crumb: "A city",
    kicker: "How much power: a city and a power station",
    headline: london,
    sentence: `of electricity, on average through ${london.period}, for London (UK government). The second bar is the capacity of Vogtle, the largest US nuclear plant (US EIA): the most it can make at once, not what it averages.`,
    chart: bars(
      [
        { key: "london", label: `London, average through ${london.period}`, value: london.value, colour: CAPTURE, drill: "power-city-year" },
        { key: "vogtle", label: `Vogtle nuclear plant, capacity (${formatPeriod(plant.period ?? "")})`, value: plant.value as number, colour: FOSSIL },
      ],
      short,
      decimals,
      london.period,
      "An average is a year's electricity divided by its hours; a capacity is a plant's maximum output.",
    ),
    drills: [
      { label: "A home", to: "power-home" },
      { label: "London in a year", to: "power-city-year" },
    ],
    credit: credit(POWER_LONDON, VOGTLE),
    indicators: [POWER_LONDON, VOGTLE],
  };
}

function powerCityYear(): Built {
  const h = headline(USE_LONDON, "GBR_LONDON");
  const { short, decimals } = u(USE_LONDON);
  return {
    id: "power-city-year",
    parent: "power-city",
    crumb: "In a year",
    kicker: "London's electricity in a year",
    headline: h,
    sentence: `of electricity used in London in ${h.period}, by the UK government's meter readings. Divided by the hours in the year, it is the average power one level up.`,
    chart: bars([{ key: "london", label: `London, ${h.period}`, value: h.value, colour: CAPTURE }], short, decimals, h.period, "Homes and businesses together, from meter readings."),
    drills: [{ label: "A home", to: "power-home" }],
    credit: credit(USE_LONDON),
    indicators: [USE_LONDON],
  };
}

function powerHome(): Built {
  const us = headline(POWER_HOME_US, "USA");
  const gb = headline(POWER_HOME_GB, "GBR_GB");
  const { short, decimals } = u(POWER_HOME_US);
  if (u(POWER_HOME_GB).short !== short) throw new Error("zero/power-home: the two homes are not in the same unit");
  return {
    id: "power-home",
    parent: "power-city",
    crumb: "A home",
    kicker: "How much power: one home",
    headline: us,
    sentence: `of electricity, on average through ${us.period}, for the average US home (US EIA). The average home in Great Britain (UK government, ${gb.period}) is the second bar. Many homes heat with gas or oil, which is not counted here.`,
    chart: bars(
      [
        { key: "us", label: `United States, ${us.period}`, value: us.value, colour: CAPTURE, drill: "power-home-year" },
        { key: "gb", label: `Great Britain, ${gb.period}`, value: gb.value, colour: CAPTURE, drill: "power-home-year" },
      ],
      short,
      decimals,
      us.period,
      "A year's electricity divided by the hours in that year.",
    ),
    drills: [{ label: "In a year", to: "power-home-year" }],
    credit: credit(POWER_HOME_US, POWER_HOME_GB),
    indicators: [POWER_HOME_US, POWER_HOME_GB],
  };
}

function powerHomeYear(): Built {
  const us = headline(USE_HOME_US, "USA");
  const gb = headline(USE_HOME_GB, "GBR_GB");
  const { short, decimals } = u(USE_HOME_US);
  if (u(USE_HOME_GB).short !== short) throw new Error("zero/power-home-year: the two homes are not in the same unit");
  return {
    id: "power-home-year",
    parent: "power-home",
    crumb: "In a year",
    kicker: "A home's electricity in a year",
    headline: us,
    sentence: `of electricity used by the average US home in ${us.period} (US EIA's household survey). The second bar is the average home in Great Britain in ${gb.period}, from meter readings.`,
    chart: bars(
      [
        { key: "us", label: `United States, ${us.period}`, value: us.value, colour: CAPTURE },
        { key: "gb", label: `Great Britain, ${gb.period}`, value: gb.value, colour: CAPTURE },
      ],
      short,
      decimals,
      us.period,
      "Electricity only, per home, as each producer publishes it.",
    ),
    drills: [],
    credit: credit(USE_HOME_US, USE_HOME_GB),
    indicators: [USE_HOME_US, USE_HOME_GB],
  };
}

// --- the five questions: how much space -----------------------------------------------------------------------

type LandRow = { source: string; area: string; statistic: string; value: number };

function landRows(): LandRow[] {
  return indicator(LAND)
    .observations.filter((o) => o.value !== null && (o.dims.statistic === "median" || o.dims.statistic === "assigned"))
    .map((o) => ({ source: o.dims.source, area: o.dims.area, statistic: o.dims.statistic, value: o.value as number }));
}

function landLabel(r: LandRow): string {
  const name = dimLabel(LAND, "source", r.source);
  if (r.area === "footprint") return `${name}, footprint only`;
  if (r.area === "spacing") return `${name}, whole area`;
  return r.statistic === "assigned" ? `${name} (assigned zero)` : name;
}

function space(): Built {
  const rows = landRows().sort((a, b) => b.value - a.value || a.source.localeCompare(b.source));
  // The least land of any measured source: the lowest median (an assigned zero is the authors' assumption, not a
  // measurement, so it is not "the least").
  const measured = rows.filter((r) => r.statistic === "median");
  const least = [...measured].sort((a, b) => a.value - b.value || a.source.localeCompare(b.source))[0];
  const most = measured[0];
  const h = headline(LAND, "WLD", { source: least.source, area: least.area, statistic: "median" });
  const { short, decimals } = u(LAND);
  return {
    id: "space",
    parent: "root",
    crumb: "How much space",
    kicker: "How much space: land per unit of electricity",
    headline: h,
    sentence: `of land for each terawatt-hour a year from ${landLabel(least).toLowerCase()}, the least of the ways of making electricity Lovering and colleagues reviewed; ${landLabel(most).toLowerCase()} needs the most. Coal, gas and nuclear include the land that supplies their fuel.`,
    chart: bars(
      rows.map((r) => ({ key: `${r.source}-${r.area}`, label: landLabel(r), value: r.value, colour: ["nuclear", "geothermal", "wind", "hydro", "solar-csp", "ground-pv", "rooftop-pv"].includes(r.source) ? CLEAN : FOSSIL })),
      short,
      decimals,
      h.period,
      "Medians across the studies reviewed. Wind and gas are shown both ways: the land the equipment occupies, and the whole area of the farm or field.",
      [
        { label: "Low-carbon", colour: CLEAN },
        { label: "Fossil or burned fuel", colour: FOSSIL },
      ],
    ),
    drills: [{ label: "Power per square metre", to: "space-density" }],
    credit: credit(LAND),
    indicators: [LAND],
  };
}

function spaceDensity(): Built {
  const rows = indicator(DENSITY)
    .observations.filter((o) => o.value !== null && o.dims.statistic === "median")
    .map((o) => ({ source: o.dims.source, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.source.localeCompare(b.source));
  const top = rows[0];
  const h = headline(DENSITY, "WLD", { source: top.source, statistic: "median" });
  const { short, decimals } = u(DENSITY);
  return {
    id: "space-density",
    parent: "space",
    crumb: "Power per square metre",
    kicker: "Power from each square metre",
    headline: h,
    sentence: `from each square metre of ${dimLabel(DENSITY, "source", top.source).toLowerCase()}, the most of the ways of making electricity Nøland and colleagues measured. Their areas are drawn differently from the review one level up, so the two are never combined.`,
    chart: bars(
      rows.map((r) => ({ key: r.source, label: dimLabel(DENSITY, "source", r.source), value: r.value, colour: CLEAN })),
      short,
      decimals,
      h.period,
      "Medians across sites. Natural gas and biomass are left out: their values rest on figures under other terms.",
    ),
    drills: [],
    credit: credit(DENSITY),
    indicators: [DENSITY],
  };
}

// --- the five questions: how much it costs (the Green Premium) -----------------------------------------------

type Stated = { key: string; label: string; ind: string; entity: string; dims: Dims; low: number | null; high: number; drill?: string };

/** One stated premium: its two ends where the producer gives a range, or its one value. */
function stated(key: string, label: string, ind: string, entity: string, dims: Dims, drill?: string): Stated {
  const bounds = indicator(ind).dimensions.find((d) => d.id === "bound")?.values.map((v) => v.id) ?? [];
  const base = { key, label, ind, entity, ...(drill ? { drill } : {}) };
  if (bounds.length === 0) return { ...base, dims, low: null, high: must(ind, entity, dims) };
  const point = bounds.includes("point") ? value(ind, entity, { ...dims, bound: "point" }) : null;
  if (point !== null) return { ...base, dims: { ...dims, bound: "point" }, low: null, high: point };
  return { ...base, dims: { ...dims, bound: "high" }, low: must(ind, entity, { ...dims, bound: "low" }), high: must(ind, entity, { ...dims, bound: "high" }) };
}

function premiumRows(): Stated[] {
  // Each stated premium is for one year, which its label names.
  const y = (id: string, entity: string) => {
    const periods = [...new Set(indicator(id).observations.filter((o) => o.entity === entity).map((o) => o.period))];
    if (periods.length !== 1 || !periods[0]) throw new Error(`${id}: expected one period for ${entity}`);
    return periods[0];
  };
  return [
    stated("steel", `Steel, world, ${y(GP_STEEL, "WLD")}`, GP_STEEL, "WLD", {}, "premium-materials"),
    stated("cement", `Cement, world, ${y(GP_CEMENT, "WLD")}`, GP_CEMENT, "WLD", {}, "premium-materials"),
    stated("steel-h2-bf", `Steel from hydrogen, against blast furnaces, ${y(GP_STEEL_H2, "WLD")}`, GP_STEEL_H2, "WLD", { comparator: "blast-furnace" }),
    stated("steel-h2-dri", `Steel from hydrogen, against iron made with gas, ${y(GP_STEEL_H2, "WLD")}`, GP_STEEL_H2, "WLD", { comparator: "unabated-gas-dri" }),
    stated("ammonia-electrolysis", `Ammonia from electrolysis, EU, ${y(GP_AMMONIA_IEA, "EU27")}, no carbon price`, GP_AMMONIA_IEA, "EU27", { route: "electrolysis", co2_cost: "none" }, "premium-ammonia"),
    stated("ammonia-electrolysis-co2", `Ammonia from electrolysis, EU, ${y(GP_AMMONIA_IEA, "EU27")}, carbon priced`, GP_AMMONIA_IEA, "EU27", { route: "electrolysis", co2_cost: "usd-100" }, "premium-ammonia"),
    stated("ammonia-ccus", `Ammonia from gas with capture, EU, ${y(GP_AMMONIA_IEA, "EU27")}, no carbon price`, GP_AMMONIA_IEA, "EU27", { route: "ccus", co2_cost: "none" }, "premium-ammonia"),
    stated("ammonia-ccus-co2", `Ammonia from gas with capture, EU, ${y(GP_AMMONIA_IEA, "EU27")}, carbon priced`, GP_AMMONIA_IEA, "EU27", { route: "ccus", co2_cost: "usd-100" }, "premium-ammonia"),
    stated("methanol-chn-e", `Methanol from electrolysis, China, ${y(GP_METHANOL, "CHN")}, against coal`, GP_METHANOL, "CHN", { route: "electrolysis", comparator: "unabated-coal" }),
    stated("methanol-chn-c", `Methanol with capture, China, ${y(GP_METHANOL, "CHN")}, against coal`, GP_METHANOL, "CHN", { route: "ccus", comparator: "unabated-coal" }),
    stated("methanol-ind", `Methanol from electrolysis, India, ${y(GP_METHANOL, "IND")}, against gas`, GP_METHANOL, "IND", { route: "electrolysis", comparator: "unabated-gas" }),
    stated("urea-domestic", `Fertiliser (urea), Japan, made at home, ${y(GP_UREA, "JPN")}`, GP_UREA, "JPN", { supply: "domestic" }),
    stated("urea-imported", `Fertiliser (urea), Japan, imported ammonia, ${y(GP_UREA, "JPN")}`, GP_UREA, "JPN", { supply: "imported-ammonia" }),
    stated("shipping", `A container ship on e-fuels, ${y(GP_SHIPPING, "WLD")}`, GP_SHIPPING, "WLD", {}),
    stated("clinker", "Cement clinker with capture (one modelled plant)", GP_CLINKER, "CEMCAP_REF", {}, "premium-cement"),
  ].sort((a, b) => b.high - a.high || a.key.localeCompare(b.key));
}

function premium(): Built {
  const rows = premiumRows();
  const top = rows[0];
  const h = headline(top.ind, top.entity, top.dims);
  const ids = [...new Set(rows.map((r) => r.ind))];
  return {
    id: "premium",
    parent: "root",
    crumb: "How much it costs",
    kicker: "The Green Premium: the extra cost of making it clean",
    headline: h,
    sentence: `more for ${top.label.charAt(0).toLowerCase()}${top.label.slice(1)}, the largest premium the producers here state. A Green Premium is how much more the zero-carbon way costs than the fossil way. Each bar names where and when; a range shows its low end inside its high end. No open source compares plastics.`,
    chart: bars(
      rows.map((r) => rangeBar(r.key, r.label, r.low, r.high, r.drill)),
      u(GP_CEMENT).short,
      0,
      h.period,
      "As each producer states it: the IEA's reports (2023 to 2026) and one modelled cement plant (CEMCAP). The urea figures include carbon pricing; the others leave it out unless marked.",
      [
        { label: "Low end of a range", colour: PREMIUM },
        { label: "High end, or a single value", colour: `${PREMIUM}59` },
      ],
    ),
    drills: [
      { label: "Electricity", to: "premium-electricity" },
      { label: "Steel and cement per tonne", to: "premium-materials" },
      { label: "Cement with capture", to: "premium-cement" },
      { label: "Fertiliser", to: "premium-ammonia" },
      { label: "Heating a home", to: "premium-heating" },
      { label: "Cars", to: "premium-cars" },
      { label: "Lorries", to: "premium-trucks" },
      { label: "Jet fuel", to: "premium-jet-fuel" },
      { label: "Meat and its alternatives", to: "premium-meat" },
    ],
    credit: credit(...ids),
    indicators: ids,
  };
}

/** EIA's technologies, as low-carbon or fossil (an unknown one fails the build). */
const US_TECH_SIDE: Record<string, string> = {
  "advanced-nuclear": "low-carbon",
  biomass: "low-carbon",
  "gas-combined-cycle": "conventional",
  "gas-combined-cycle-ccs": "conventional-with-capture",
  geothermal: "low-carbon",
  "offshore-wind": "low-carbon",
  hydroelectric: "low-carbon",
  "solar-pv-battery": "low-carbon",
  "solar-pv": "low-carbon",
  "onshore-wind": "low-carbon",
  "combustion-turbine": "conventional",
  "battery-storage": "low-carbon",
};

function premiumElectricity(): Built {
  const ind = indicator(LCOE_US);
  const basis = { cost_basis: "before-tax-credits", average: "simple-average" };
  const rows = ind.observations
    .filter((o) => o.value !== null && matches(o, "USA", basis) && o.dims.technology !== "battery-storage")
    .map((o) => {
      const side = US_TECH_SIDE[o.dims.technology];
      if (!side) throw new Error(`zero/premium-electricity: no side for ${o.dims.technology}`);
      return { tech: o.dims.technology, side, value: o.value as number, period: o.period as string };
    })
    .sort((a, b) => a.value - b.value || a.tech.localeCompare(b.tech));
  const cheapest = rows[0];
  const gas = rows.find((r) => r.tech === "gas-combined-cycle");
  if (!gas) throw new Error("zero/premium-electricity: no gas combined-cycle value");
  const h = headline(LCOE_US, "USA", { ...basis, technology: cheapest.tech });
  return {
    id: "premium-electricity",
    parent: "premium",
    crumb: "Electricity",
    kicker: cheapest.side === "low-carbon" ? "For new power plants, clean electricity can cost less" : "What electricity from new power plants costs",
    headline: h,
    sentence: `per megawatt-hour from new ${dimLabel(LCOE_US, "technology", cheapest.tech).toLowerCase()} plants entering service in ${cheapest.period}, the lowest of the plants the US EIA costs, ${against(cheapest.value, [gas.value])} gas combined-cycle plants. Before tax credits; it leaves out the cost of fitting variable power into the grid.`,
    chart: bars(
      rows.map((r) => ({ key: r.tech, label: dimLabel(LCOE_US, "technology", r.tech), value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      cheapest.period,
      "US average of the 25 supply regions, before tax credits; a projection for plants entering service in that year.",
      legendFor([...new Set(rows.map((r) => r.side))]),
    ),
    drills: [
      { label: "In the UK", to: "premium-electricity-uk" },
      crossDrill("Renewables' costs over time", "energy", energy.node("capacity-cost")),
    ],
    credit: credit(LCOE_US),
    indicators: [LCOE_US],
  };
}

const UK_TECHS: { id: string; side: string }[] = [
  { id: "large-scale-solar", side: "low-carbon" },
  { id: "onshore-wind", side: "low-carbon" },
  { id: "offshore-wind-fixed", side: "low-carbon" },
  { id: "gas-ccgt-93pc-load", side: "conventional" },
  { id: "gas-ccgt-30pc-load", side: "conventional" },
];

function premiumElectricityUk(): Built {
  const ind = indicator(LCOE_UK);
  const year = [...new Set(ind.observations.map((o) => o.period as string))].sort()[0];
  const rows = UK_TECHS.flatMap((t) => {
    const v = value(LCOE_UK, "GBR", { technology: t.id, estimate: "unmarked", component: "total" }, year);
    return v === null ? [] : [{ ...t, value: v }];
  }).sort((a, b) => a.value - b.value || a.id.localeCompare(b.id));
  const missing = UK_TECHS.filter((t) => !rows.some((r) => r.id === t.id)).map((t) => dimLabel(LCOE_UK, "technology", t.id));
  const cheapest = rows[0];
  const gas = rows.filter((r) => r.side === "conventional").map((r) => r.value);
  const h = headline(LCOE_UK, "GBR", { technology: cheapest.id, estimate: "unmarked", component: "total" }, year);
  return {
    id: "premium-electricity-uk",
    parent: "premium-electricity",
    crumb: "In the UK",
    kicker: "What new power plants' electricity costs in the UK",
    headline: h,
    sentence: `per megawatt-hour from ${dimLabel(LCOE_UK, "technology", cheapest.id).toLowerCase()} starting in ${year}, the UK government estimates, ${against(cheapest.value, gas)} gas plants. Its totals include the UK carbon price as one of their parts.`,
    chart: bars(
      rows.map((r) => ({ key: r.id, label: dimLabel(LCOE_UK, "technology", r.id), value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `Total levelised cost for plants starting in ${year}, 2024 prices.${missing.length ? ` No value for ${missing.join(", ")}.` : ""}`,
      legendFor([...new Set(rows.map((r) => r.side))]),
    ),
    drills: [],
    credit: credit(LCOE_UK),
    indicators: [LCOE_UK],
  };
}

function premiumMaterials(): Built {
  const steel = stated("steel", `Steel, world`, GP_STEEL_USD, "WLD", {});
  const cement = stated("cement", `Cement, world`, GP_CEMENT_USD, "WLD", {});
  if (u(GP_STEEL_USD).short.split("/")[0] !== u(GP_CEMENT_USD).short.split("/")[0]) throw new Error("zero/premium-materials: steel and cement are not in the same currency");
  const h = headline(GP_STEEL_USD, "WLD", { bound: "high" });
  return {
    id: "premium-materials",
    parent: "premium",
    crumb: "Steel and cement",
    kicker: "The extra cost of clean steel and cement, per tonne",
    headline: h,
    sentence: `more for each tonne of near-zero emissions steel in ${h.period}, at the high end of the IEA's range; cement is the second bar. Steel and cement are at the heart of making things.`,
    chart: bars(
      [
        { ...rangeBar("steel", `${steel.label} (${u(GP_STEEL_USD).short})`, steel.low, steel.high) },
        { ...rangeBar("cement", `${cement.label} (${u(GP_CEMENT_USD).short})`, cement.low, cement.high) },
      ],
      "US$ (2024) per tonne",
      0,
      h.period,
      "The IEA's stated ranges for 2035, in 2024 US dollars per tonne of each material.",
      [
        { label: "Low end", colour: PREMIUM },
        { label: "High end", colour: `${PREMIUM}59` },
      ],
    ),
    drills: [{ label: "Cement with capture", to: "premium-cement" }],
    credit: credit(GP_STEEL_USD, GP_CEMENT_USD),
    indicators: [GP_STEEL_USD, GP_CEMENT_USD],
  };
}

function premiumCement(): Built {
  const ind = indicator(CLINKER_COST);
  const rows = ind.observations
    .filter((o) => o.value !== null)
    .map((o) => ({ tech: o.dims.technology, value: o.value as number }))
    .sort((a, b) => a.value - b.value || a.tech.localeCompare(b.tech));
  const ref = rows.find((r) => r.tech === "reference");
  if (!ref) throw new Error("zero/premium-cement: no reference plant");
  const captured = rows.filter((r) => r.tech !== "reference");
  const cheapest = captured[0];
  const h = headline(CLINKER_COST, "CEMCAP_REF", { technology: cheapest.tech });
  return {
    id: "premium-cement",
    parent: "premium",
    crumb: "Cement with capture",
    kicker: "Cement clinker with its carbon dioxide captured",
    headline: h,
    sentence: `per tonne of clinker (the part of cement that releases carbon dioxide when made) ${dimLabel(CLINKER_COST, "technology", cheapest.tech).toLowerCase()}, the cheapest capture route CEMCAP modelled, ${against(cheapest.value, [ref.value])} the same plant without capture. One modelled European plant, at 2014 prices.`,
    chart: bars(
      rows.map((r) => ({ key: r.tech, label: dimLabel(CLINKER_COST, "technology", r.tech), value: r.value, colour: r.tech === "reference" ? FOSSIL : CAPTURE })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "CEMCAP's reference cement plant, with each capture technology costed on the same basis.",
      legendFor(["conventional", "conventional-with-capture"]),
    ),
    drills: [crossDrill("Capturing what is left", "zero", capture())],
    credit: credit(CLINKER_COST),
    indicators: [CLINKER_COST],
  };
}

function sideRows(id: string, filter: Dims, labelOf: (o: Observation) => string): { key: string; label: string; side: string; value: number }[] {
  return indicator(id)
    .observations.filter((o) => o.value !== null && Object.entries(filter).every(([k, v]) => o.dims[k] === v))
    .map((o) => ({ key: `${o.entity}-${Object.values(o.dims).join("-")}-${o.period}`, label: labelOf(o), side: o.dims.side, value: o.value as number }));
}

function premiumAmmonia(): Built {
  const ind = indicator(GP_AMMONIA);
  const label = (o: Observation) => `${dimLabel(GP_AMMONIA, "option", o.dims.option)}, ${dimLabel(GP_AMMONIA, "setting", o.dims.setting).replace(/ \(.*$/, "")}`;
  const rows = sideRows(GP_AMMONIA, {}, label).sort((a, b) => b.value - a.value || a.key.localeCompare(b.key));
  const green = rows.filter((r) => r.side === "low-carbon").sort((a, b) => a.value - b.value);
  const fossil = must(GP_AMMONIA, "EUR_STUDY", { option: "kbr-without-capture" });
  const cheapestGreen = ind.observations.find((o) => o.dims.side === "low-carbon" && o.value === green[0].value)!;
  const h = headline(GP_AMMONIA, cheapestGreen.entity, cheapestGreen.dims);
  return {
    id: "premium-ammonia",
    parent: "premium",
    crumb: "Fertiliser",
    kicker: "Ammonia, the base of most fertiliser, made clean",
    headline: h,
    sentence: `per tonne of green ammonia made with wind and solar power in ${entityName(cheapestGreen.entity)}, the cheapest green case Arnaiz del Pozo and Cloete costed, ${against(h.value, [fossil])} ammonia from natural gas at European prices with its carbon dioxide released (which they charge a carbon tax). Green ammonia uses technology costs expected by 2050.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "One study, one cost method for every plant; 2020 euros.",
      legendFor([...new Set(rows.map((r) => r.side))]),
    ),
    drills: [crossDrill("What food emits", "food", food.node("root"))],
    credit: credit(GP_AMMONIA),
    indicators: [GP_AMMONIA],
  };
}

function premiumHeating(): Built {
  const ind = indicator(GP_HEAT_GB);
  const cases = ind.dimensions.find((d) => d.id === "case")!.values.map((v) => v.id);
  const rows: Bar[] = cases.flatMap((c) =>
    (["conventional", "low-carbon"] as const).flatMap((side) => {
      const o = ind.observations.find((x) => x.dims.case === c && x.dims.side === side && x.value !== null);
      return o ? [{ key: `${c}-${side}`, label: `${dimLabel(GP_HEAT_GB, "case", c)}: ${dimLabel(GP_HEAT_GB, "side", side).toLowerCase()}`, value: o.value as number, colour: sideColour(side) }] : [];
    }),
  );
  const pump = must(GP_HEAT_GB, "GBR", { case: "central", side: "low-carbon" });
  const boiler = must(GP_HEAT_GB, "GBR", { case: "central", side: "conventional" });
  const h = headline(GP_HEAT_GB, "GBR", { case: "central", side: "low-carbon", option: "heat-pump" });
  return {
    id: "premium-heating",
    parent: "premium",
    crumb: "Heating a home",
    kicker: "A heat pump against a gas boiler",
    headline: h,
    sentence: `to buy and run a heat pump over its life in an average British home in Rosenow and colleagues' central case, ${against(pump, [boiler])} a gas boiler. The central case counts the government's installation grant; each other case changes one assumption.`,
    chart: bars(rows, ind.unit.short, ind.display.decimals, h.period, "Lifetime cost of owning each system, as published for each case.", legendFor(["conventional", "low-carbon"])),
    drills: [{ label: "Worldwide", to: "premium-heating-world" }],
    credit: credit(GP_HEAT_GB),
    indicators: [GP_HEAT_GB],
  };
}

function premiumHeatingWorld(): Built {
  const ind = indicator(GP_HEAT_WORLD);
  const rows = sideRows(GP_HEAT_WORLD, {}, (o) => `${dimLabel(GP_HEAT_WORLD, "side", o.dims.side)}: ${dimLabel(GP_HEAT_WORLD, "cost", o.dims.cost).replace(/ \(.*$/, "").toLowerCase()}`);
  const pump = must(GP_HEAT_WORLD, "WLD", { side: "low-carbon", cost: "net" });
  const base = must(GP_HEAT_WORLD, "WLD", { side: "conventional", cost: "net" });
  const h = headline(GP_HEAT_WORLD, "WLD", { side: "low-carbon", cost: "net", option: "heat-pump" });
  return {
    id: "premium-heating-world",
    parent: "premium-heating",
    crumb: "Worldwide",
    kicker: "Heat pumps against today's heating, worldwide",
    headline: h,
    sentence: `a year for a heat pump system, its purchase spread over its life plus running it, by Project Drawdown, ${against(pump, [base])} the mix of heating equipment in use today.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "World averages in 2023 US dollars per system per year.",
      legendFor(["conventional", "low-carbon"]),
    ),
    drills: [],
    credit: credit(GP_HEAT_WORLD),
    indicators: [GP_HEAT_WORLD],
  };
}

function premiumCars(): Built {
  const ind = indicator(GP_CARS_KM);
  const rows = sideRows(GP_CARS_KM, {}, (o) => dimLabel(GP_CARS_KM, "option", o.dims.option).replace(/ \(.*$/, "")).sort((a, b) => b.value - a.value);
  const ev = must(GP_CARS_KM, "CZE", { option: "electric" });
  const fossil = rows.filter((r) => r.side === "conventional").map((r) => r.value);
  const h = headline(GP_CARS_KM, "CZE", { option: "electric", side: "low-carbon" });
  return {
    id: "premium-cars",
    parent: "premium",
    crumb: "Cars",
    kicker: "An electric car against petrol and diesel, per kilometre",
    headline: h,
    sentence: `per kilometre to own and run a battery electric car in Czechia over its life, by Furch and colleagues, ${against(ev, fossil)} the petrol and diesel cars they costed. One market and one set of prices.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Life cycle cost per kilometre in Czechia, as published.",
      legendFor(["conventional", "low-carbon"]),
    ),
    drills: [
      { label: "Over the car's life", to: "premium-cars-life" },
      crossDrill("What each car emits", "action", action.node("cars")),
    ],
    credit: credit(GP_CARS_KM),
    indicators: [GP_CARS_KM],
  };
}

function premiumCarsLife(): Built {
  const ind = indicator(GP_CARS_LIFE);
  const rows = sideRows(GP_CARS_LIFE, {}, (o) => dimLabel(GP_CARS_LIFE, "option", o.dims.option).replace(/ \(.*$/, "")).sort((a, b) => b.value - a.value);
  const h = headline(GP_CARS_LIFE, "CZE", { option: "electric", side: "low-carbon" });
  return {
    id: "premium-cars-life",
    parent: "premium-cars",
    crumb: "Over the car's life",
    kicker: "What each car costs over its whole life",
    headline: h,
    sentence: "to buy, run and maintain a battery electric car over its life in Czechia, by Furch and colleagues; petrol and diesel are the other bars. The paper notes its electric total may not include replacing the battery.",
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Life cycle cost over the car's life, as published.",
      legendFor(["conventional", "low-carbon"]),
    ),
    drills: [],
    credit: credit(GP_CARS_LIFE),
    indicators: [GP_CARS_LIFE],
  };
}

function premiumTrucks(): Built {
  const ind = indicator(GP_TRUCKS);
  const rows = sideRows(GP_TRUCKS, { statistic: "mean" }, (o) => dimLabel(GP_TRUCKS, "option", o.dims.option).replace(/ \(.*$/, "")).sort((a, b) => b.value - a.value);
  const ev = must(GP_TRUCKS, "FIN", { option: "ev", statistic: "mean" });
  const diesel = must(GP_TRUCKS, "FIN", { option: "diesel", statistic: "mean" });
  const h = headline(GP_TRUCKS, "FIN", { option: "ev", side: "low-carbon", statistic: "mean" });
  return {
    id: "premium-trucks",
    parent: "premium",
    crumb: "Lorries",
    kicker: "An electric lorry against a diesel one",
    headline: h,
    sentence: `a month to own and run a battery electric lorry in one Finnish food-delivery fleet, by Rajalehto and Helo, ${against(ev, [diesel])} a diesel lorry doing the same work. One company's trucks, in ${formatPeriod(h.period)}.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Mean of the authors' simulations of each truck's monthly cost.",
      legendFor(["conventional", "low-carbon"]),
    ),
    drills: [],
    credit: credit(GP_TRUCKS),
    indicators: [GP_TRUCKS],
  };
}

function premiumJetFuel(): Built {
  const ind = indicator(GP_JET);
  const rows = ind.observations
    .filter((o) => o.dims.side === "low-carbon" && o.value !== null)
    .map((o) => ({ key: `${o.dims.scenario}-${o.period}`, label: `Synthetic jet fuel, ${o.period}, ${dimLabel(GP_JET, "scenario", o.dims.scenario).replace(/ \(.*$/, "")}`, value: o.value as number, period: o.period as string }))
    .sort((a, b) => a.label.localeCompare(b.label));
  const fossilMissing = ind.observations.filter((o) => o.dims.side === "conventional").every((o) => o.value === null);
  if (!fossilMissing) throw new Error("zero/premium-jet-fuel: the sentence says there is no fossil comparator, but one is now published");
  const latest = [...rows].sort((a, b) => b.period.localeCompare(a.period) || a.key.localeCompare(b.key)).find((r) => r.key.startsWith("2c"))!;
  const h = headline(GP_JET, "EUR_STUDY", { side: "low-carbon", scenario: "2c", option: "synthetic-jet-fuel" }, latest.period);
  return {
    id: "premium-jet-fuel",
    parent: "premium",
    crumb: "Jet fuel",
    kicker: "What clean jet fuel could cost",
    headline: h,
    sentence: `per kilogram of synthetic jet fuel, made from hydrogen and captured carbon dioxide, for European flights in ${latest.period}, by Sacchi and colleagues. No fossil comparator: the study's fossil price comes from another source, so it is left out.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: CLEAN })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Projected production cost in each climate scenario. No data for fossil jet fuel in Sacchi et al.",
    ),
    drills: [crossDrill("What a flight emits", "action", action.node("flights"))],
    credit: credit(GP_JET),
    indicators: [GP_JET],
  };
}

function premiumMeat(): Built {
  const ind = indicator(GP_MEAT);
  const rows = sideRows(GP_MEAT, { statistic: "mean" }, (o) => `${dimLabel(GP_MEAT, "product", o.dims.product)}: ${dimLabel(GP_MEAT, "side", o.dims.side).toLowerCase()}`);
  const plant = must(GP_MEAT, "AUT", { product: "mince", side: "low-carbon", statistic: "mean" });
  const meat = must(GP_MEAT, "AUT", { product: "mince", side: "conventional", statistic: "mean" });
  const h = headline(GP_MEAT, "AUT", { product: "mince", side: "low-carbon", statistic: "mean" });
  return {
    id: "premium-meat",
    parent: "premium",
    crumb: "Meat",
    kicker: "Plant-based mince and sausages against meat",
    headline: h,
    sentence: `per kilogram for plant-based mince on Vienna's shop shelves in ${formatPeriod(h.period)}, by Falkenberg and colleagues, ${against(plant, [meat])} meat mince. Shop prices, not the cost of making it; no open study compares lab-grown meat on one basis.`,
    chart: bars(
      rows.map((r) => ({ key: r.key, label: r.label, value: r.value, colour: sideColour(r.side) })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Mean shelf price of the products surveyed in Vienna.",
      legendFor(["conventional", "low-carbon"]),
    ),
    drills: [
      { label: "In Germany and Spain", to: "premium-meat-ratio" },
      crossDrill("What each food emits", "food", food.node("foods")),
    ],
    credit: credit(GP_MEAT),
    indicators: [GP_MEAT],
  };
}

function premiumMeatRatio(): Built {
  const ind = indicator(GP_MEAT_RATIO);
  const rows = ind.observations
    .filter((o) => o.value !== null)
    .map((o) => ({ entity: o.entity, value: o.value as number, period: o.period as string }))
    .sort((a, b) => b.value - a.value || a.entity.localeCompare(b.entity));
  const top = rows[0];
  const h = headline(GP_MEAT_RATIO, top.entity, {}, top.period);
  return {
    id: "premium-meat-ratio",
    parent: "premium-meat",
    crumb: "Germany and Spain",
    kicker: "How much more meat substitutes cost, by country",
    headline: h,
    sentence: `times the price of meat, per kilogram, for meat substitutes in ${entityName(top.entity)}'s online shops, by Siegrist and colleagues; a ratio of one would be the same price.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: CLEAN })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Price per kilogram of meat substitutes divided by that of meat, as published for each country.",
    ),
    drills: [],
    credit: credit(GP_MEAT_RATIO),
    indicators: [GP_MEAT_RATIO],
  };
}

// --- the strategy: get to zero, electrify, capture, innovate, adapt ------------------------------------------

function netZero(): Built {
  const ind = indicator(NZ_COUNTS);
  const h = headline(NZ_COUNTS, "WLD", { status: "any-net-zero-target" });
  const statuses = ind.dimensions.find((d) => d.id === "status")!.values.map((v) => v.id).filter((s) => s !== "any-net-zero-target");
  return {
    id: "net-zero",
    parent: "root",
    crumb: "Net zero targets",
    kicker: "Governments with a net zero target",
    headline: h,
    sentence: `national governments had a net zero target when the Net Zero Tracker collected its data, ${formatPeriod(h.period)}. Each bar counts governments at one status, from achieved and in law to none.`,
    chart: bars(
      statuses.map((s) => {
        const colour = STATUS_COLOUR[s];
        if (!colour) throw new Error(`zero/net-zero: no colour for status ${s}`);
        return { key: s, label: dimLabel(NZ_COUNTS, "status", s), value: must(NZ_COUNTS, "WLD", { status: s }), colour };
      }),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "National governments by the status of their end target, as the Net Zero Tracker codes them. Achieved is the government's own claim.",
    ),
    drills: [
      { label: "The largest emitters", to: "net-zero-emitters" },
      crossDrill("Countries' new climate plans", "action", action.node("ndc")),
    ],
    credit: credit(NZ_COUNTS),
    indicators: [NZ_COUNTS],
  };
}

function netZeroEmitters(): Built {
  const ind = indicator(NZ_COUNTRY);
  const period = latestPeriod(GHG);
  const largest = ranking(GHG, period)
    .slice(0, TOP)
    .map((r) => r.entity);
  const rows = largest.flatMap((iso) => {
    const o = ind.observations.find((x) => x.entity === iso);
    return o && o.value !== null ? [{ iso, value: o.value, status: o.dims.status }] : [];
  });
  const without = largest.filter((iso) => !rows.some((r) => r.iso === iso));
  const reason = (iso: string) => {
    const o = ind.observations.find((x) => x.entity === iso);
    return o ? `${entityName(iso)} (${dimLabel(NZ_COUNTRY, "status", o.dims.status).toLowerCase()})` : `${entityName(iso)} (not in the Tracker)`;
  };
  const first = rows[0];
  const h = headline(NZ_COUNTRY, first.iso, { status: first.status });
  return {
    id: "net-zero-emitters",
    parent: "net-zero",
    crumb: "Largest emitters",
    kicker: "The largest emitters' net zero years",
    headline: h,
    sentence: `for net zero in ${entityName(first.iso)} (${dimLabel(NZ_COUNTRY, "status", first.status).toLowerCase()}), the largest emitter with a target. Each bar is a country's target year, coloured by how firm it is.`,
    chart: bars(
      rows.map((r) => {
        const colour = STATUS_COLOUR[r.status];
        if (!colour) throw new Error(`zero/net-zero-emitters: no colour for status ${r.status}`);
        return { key: r.iso, label: `${entityName(r.iso)}, ${dimLabel(NZ_COUNTRY, "status", r.status).toLowerCase()}`, value: r.value, colour };
      }),
      "target year",
      0,
      h.period,
      `The largest greenhouse gas emitters in ${period} (FAO), largest first.${without.length ? ` No net zero target: ${without.map(reason).join(", ")}.` : ""}`,
    ),
    drills: [],
    credit: credit(NZ_COUNTRY, GHG),
    indicators: [NZ_COUNTRY, GHG],
  };
}

function electrify(): Built {
  const h = headline(ELEC_SHARE, "EU27");
  const { short, decimals } = u(ELEC_SHARE);
  return {
    id: "electrify",
    parent: "root",
    crumb: "Electrify",
    kicker: "How much of the energy we use is electricity",
    headline: h,
    sentence: `of the energy used in the European Union in ${h.period} was electricity, by Eurostat. Electrifying cars, heating and industry, while the electricity itself turns clean, is the core of the plan. No open source publishes this for the world.`,
    chart: area([{ key: "eu", label: "Electricity's share of final energy, EU", colour: CAPTURE, points: points(ELEC_SHARE, "EU27"), drill: "electrify-countries" }], short, decimals, false),
    drills: [
      { label: "By country", to: "electrify-countries" },
      crossDrill("Clean electricity", "energy", energy.node("root")),
      crossDrill("Electric cars", "energy", energy.node("ev")),
    ],
    credit: credit(ELEC_SHARE),
    indicators: [ELEC_SHARE],
  };
}

function electrifyCountries(): Built {
  const { short, decimals } = u(ELEC_SHARE);
  const year = latestPeriod(ELEC_SHARE);
  const rows = ranking(ELEC_SHARE, year).slice(0, TOP);
  const top = rows[0];
  return {
    id: "electrify-countries",
    parent: "electrify",
    crumb: "By country",
    kicker: `${entityName(top.entity)} runs most on electricity of the countries Eurostat reports`,
    headline: headline(ELEC_SHARE, top.entity, {}, year),
    sentence: `of the energy used in ${entityName(top.entity)} in ${year} was electricity, the highest share among the countries Eurostat reports.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: CAPTURE })),
      short,
      decimals,
      year,
      `The ${rows.length} highest shares in ${year}, EU, EFTA and candidate countries.`,
    ),
    drills: [],
    credit: credit(ELEC_SHARE),
    indicators: [ELEC_SHARE],
  };
}

function capture(): Built {
  const ind = indicator(CCS_OPERATING);
  const h = headline(CCS_OPERATING, "WLD", { sector: "all" });
  const rows = ind.observations
    .filter((o) => o.value !== null && o.dims.sector !== "all")
    .map((o) => ({ sector: o.dims.sector, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.sector.localeCompare(b.sector));
  const missing = ind.dimensions.find((d) => d.id === "sector")!.values.filter((v) => v.id !== "all" && !rows.some((r) => r.sector === v.id));
  return {
    id: "capture",
    parent: "root",
    crumb: "Capture what is left",
    kicker: "Carbon capture in operation",
    headline: h,
    sentence: `a year of carbon dioxide capture capacity in projects operating on ${formatPeriod(h.period)}, by the IEA's project database: a capacity announced by each project, not what it captured. ${dimLabel(CCS_OPERATING, "sector", rows[0].sector)} holds the most.`,
    chart: bars(
      rows.map((r) => ({ key: r.sector, label: dimLabel(CCS_OPERATING, "sector", r.sector), value: r.value, colour: CAPTURE })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `Operating capture capacity by sector, counted as the IEA's explorer counts it.${missing.length ? ` No operating capacity listed for: ${missing.map((v) => v.label).join(", ")}.` : ""}`,
    ),
    drills: [
      { label: "Being built and planned", to: "capture-pipeline" },
      { label: "Taking carbon back out", to: "removal" },
    ],
    credit: credit(CCS_OPERATING),
    indicators: [CCS_OPERATING],
  };
}

function capturePipeline(): Built {
  const ind = indicator(CCS_STATUS);
  const statuses = ind.dimensions.find((d) => d.id === "status")!.values.map((v) => v.id);
  const last = latestPeriod(CCS_STATUS);
  const h = headline(CCS_STATUS, "WLD", { status: "planned" }, last);
  return {
    id: "capture-pipeline",
    parent: "capture",
    crumb: "Built and planned",
    kicker: "Carbon capture being built and planned",
    headline: h,
    sentence: `a year of capture capacity planned to be running by ${last}, on top of what is operating and being built, by the IEA's project database. Plans are announcements; many are never built.`,
    chart: area(
      statuses.map((s) => ({ key: s, label: dimLabel(CCS_STATUS, "status", s), colour: CCS_STATUS_COLOUR[s] ?? CAPTURE, points: points(CCS_STATUS, "WLD", { status: s }) })),
      ind.unit.short,
      ind.display.decimals,
      true,
    ),
    drills: [{ label: "Number of projects", to: "capture-projects" }],
    credit: credit(CCS_STATUS),
    indicators: [CCS_STATUS],
  };
}

function captureProjects(): Built {
  const ind = indicator(CCS_PROJECTS);
  const statuses = ind.dimensions.find((d) => d.id === "status")!.values.map((v) => v.id);
  const last = latestPeriod(CCS_PROJECTS);
  const h = headline(CCS_PROJECTS, "WLD", { status: "operational" }, last);
  return {
    id: "capture-projects",
    parent: "capture-pipeline",
    crumb: "Projects",
    kicker: "Carbon capture projects, operating and planned",
    headline: h,
    sentence: `carbon capture projects are operating, by the IEA's project database; the bands above add those being built and planned, by the year each is due.`,
    chart: area(
      statuses.map((s) => ({ key: s, label: dimLabel(CCS_PROJECTS, "status", s), colour: CCS_STATUS_COLOUR[s] ?? CAPTURE, points: points(CCS_PROJECTS, "WLD", { status: s }) })),
      ind.unit.short,
      ind.display.decimals,
      true,
    ),
    drills: [],
    credit: credit(CCS_PROJECTS),
    indicators: [CCS_PROJECTS],
  };
}

const CDR_COLOURS = ["#1b7837", "#5aae61", "#a6dba0", "#2166ac", "#67a9cf", "#d1e5f0", "#762a83", "#c2a5cf", "#8c510a", "#bf812d"];

function removal(): Built {
  const ind = indicator(CDR_NOVEL);
  const methods = ind.dimensions.find((d) => d.id === "method")!.values.map((v) => v.id).filter((m) => m !== "all");
  const h = headline(CDR_NOVEL, "WLD", { method: "all" });
  return {
    id: "removal",
    parent: "capture",
    crumb: "Taking carbon back out",
    kicker: "Carbon dioxide removed by new methods",
    headline: h,
    sentence: `of carbon dioxide taken out of the air and stored durably by novel methods in ${h.period}, by The State of Carbon Dioxide Removal. Each band is one method.`,
    chart: area(
      methods.map((m, i) => ({ key: m, label: dimLabel(CDR_NOVEL, "method", m), colour: CDR_COLOURS[i % CDR_COLOURS.length], points: points(CDR_NOVEL, "WLD", { method: m }) })),
      ind.unit.short,
      ind.display.decimals,
      true,
    ),
    drills: [{ label: "Removal by forests", to: "removal-forest" }],
    credit: credit(CDR_NOVEL),
    indicators: [CDR_NOVEL],
  };
}

function removalForest(): Built {
  const ind = indicator(CDR_FOREST);
  const models = ind.dimensions.find((d) => d.id === "model")!.values.map((v) => v.id);
  const h = headline(CDR_FOREST, "WLD", { model: "mean" });
  const novel = headline(CDR_NOVEL, "WLD", { method: "all" });
  // The sentence says forests remove far more than the novel methods: checked, so a refresh that falsifies it fails.
  if (u(CDR_NOVEL).short !== ind.unit.short || h.value <= 10 * novel.value) throw new Error("zero/removal-forest: forests no longer remove far more than novel methods");
  return {
    id: "removal-forest",
    parent: "removal",
    crumb: "Forests",
    kicker: "Carbon dioxide removed by managed forests",
    headline: h,
    sentence: `of carbon dioxide removed by new and managed forests in ${h.period}, the mean of three models in The State of Carbon Dioxide Removal: far more than the novel methods one level up. The thin lines are the three models it averages, which differ.`,
    chart: line(
      models.map((m) => ({ key: m, label: dimLabel(CDR_FOREST, "model", m), colour: m === "mean" ? CLEAN : "#a6dba0", points: points(CDR_FOREST, "WLD", { model: m }) })),
      ind.unit.short,
      ind.display.decimals,
    ),
    drills: [],
    credit: credit(CDR_FOREST),
    indicators: [CDR_FOREST],
  };
}

function innovate(): Built {
  const ind = indicator(RD_OECD);
  // Each country's latest published year: reporting thins out in the latest years, so one common year would be stale.
  const rows = latestPerEntity(RD_OECD)
    .filter((r) => isPlace(r.entity))
    .sort((a, b) => b.value - a.value || a.entity.localeCompare(b.entity))
    .slice(0, TOP);
  const top = rows[0];
  const h = headline(RD_OECD, top.entity, {}, top.period);
  return {
    id: "innovate",
    parent: "root",
    crumb: "Innovate",
    kicker: "What governments budget for energy research",
    headline: h,
    sentence: `budgeted by the government of ${entityName(top.entity)} for energy research and development in ${top.period}${h.status !== "final" ? " (provisional)" : ""}, the most of the countries the OECD reports, each in its latest year. This counts all energy research, fossil and nuclear included.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: `${entityName(r.entity)} (${r.period})`, value: r.value, colour: NEUTRAL })),
      ind.unit.short,
      ind.display.decimals,
      top.period,
      "Government budgets for energy R&D in constant 2020 dollars at purchasing power parity, each country in its latest published year.",
    ),
    drills: [{ label: "The European Union", to: "innovate-eu" }],
    credit: credit(RD_OECD),
    indicators: [RD_OECD],
  };
}

function innovateEu(): Built {
  const ind = indicator(RD_EU);
  const h = headline(RD_EU, "EU27");
  return {
    id: "innovate-eu",
    parent: "innovate",
    crumb: "European Union",
    kicker: "The EU's government budgets for energy research",
    headline: h,
    sentence: `budgeted by EU governments for energy research and development in ${h.period}, by Eurostat${h.status !== "final" ? " (provisional)" : ""}, in current euros. All energy research, fossil and nuclear included.`,
    chart: area([{ key: "eu", label: "EU governments, energy R&D budgets", colour: NEUTRAL, points: points(RD_EU, "EU27") }], ind.unit.short, ind.display.decimals, false),
    drills: [],
    credit: credit(RD_EU),
    indicators: [RD_EU],
  };
}

/** Each entity's latest published value (FAO's censuses fall in different years, so they are never added or compared as one year). */
function latestPerEntity(id: string, dims: Dims = {}): { entity: string; period: string; value: number }[] {
  const by = new Map<string, Observation>();
  for (const o of indicator(id).observations) {
    if (o.value === null || !o.period || !Object.entries(dims).every(([k, v]) => o.dims[k] === v)) continue;
    const prev = by.get(o.entity);
    if (!prev || (prev.period as string) < o.period) by.set(o.entity, o);
  }
  return [...by.values()].map((o) => ({ entity: o.entity, period: o.period as string, value: o.value as number }));
}

function adapt(): Built {
  const rows = latestPerEntity(FARMS).sort((a, b) => b.value - a.value || a.entity.localeCompare(b.entity)).slice(0, TOP);
  const top = rows[0];
  const ind = indicator(FARMS);
  return {
    id: "adapt",
    parent: "root",
    crumb: "Adapt",
    kicker: "Adapting starts with the world's small farms",
    headline: headline(FARMS, top.entity, {}, top.period),
    sentence: `farms in ${entityName(top.entity)} at its ${top.period} census, the most in FAO's census tables (China's census is not included). Gates's chapter on adapting starts with the world's small farmers; the largest country opens how big its farms are.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: `${entityName(r.entity)} (${r.period})`, value: r.value, colour: CLEAN, drill: r.entity === top.entity ? "adapt-sizes" : undefined })),
      ind.unit.short,
      ind.display.decimals,
      top.period,
      "Each country's latest agricultural census, with its year; censuses fall in different years and are never added.",
    ),
    drills: [
      { label: "How big the farms are", to: "adapt-sizes" },
      crossDrill("Food and land", "food", food.node("root")),
    ],
    credit: credit(FARMS),
    indicators: [FARMS],
  };
}

/** FAO's size classes for one country's census, as published (some countries publish broader classes than others). */
function sizeRows(id: string, entity: string, period: string): { size: string; value: number }[] {
  const order = indicator(id).dimensions.find((d) => d.id === "land-size")!.values.map((v) => v.id);
  return indicator(id)
    .observations.filter((o) => o.entity === entity && o.period === period && o.value !== null)
    .map((o) => ({ size: o.dims["land-size"], value: o.value as number }))
    .sort((a, b) => order.indexOf(a.size) - order.indexOf(b.size));
}

function adaptCountry(): { entity: string; period: string } {
  const top = latestPerEntity(FARMS).sort((a, b) => b.value - a.value || a.entity.localeCompare(b.entity))[0];
  return { entity: top.entity, period: top.period };
}

function adaptSizes(): Built {
  const { entity, period } = adaptCountry();
  const rows = sizeRows(FARMS_BY_SIZE, entity, period);
  if (rows.length === 0) throw new Error(`zero/adapt-sizes: no size classes for ${entity} ${period}`);
  const first = rows[0];
  const ind = indicator(FARMS_BY_SIZE);
  return {
    id: "adapt-sizes",
    parent: "adapt",
    crumb: "Farm sizes",
    kicker: `${entityName(entity)}'s farms by size`,
    headline: headline(FARMS_BY_SIZE, entity, { "land-size": first.size }, period),
    sentence: `of ${entityName(entity)}'s farms at its ${period} census were in FAO's smallest size class, ${dimLabel(FARMS_BY_SIZE, "land-size", first.size).toLowerCase()}. Each bar is one of FAO's classes, as the census publishes them.`,
    chart: bars(
      rows.map((r) => ({ key: r.size, label: dimLabel(FARMS_BY_SIZE, "land-size", r.size), value: r.value, colour: CLEAN })),
      ind.unit.short,
      ind.display.decimals,
      period,
      "Number of farms in each of FAO's land-size classes, in the order FAO lists them.",
    ),
    drills: [{ label: "The land they farm", to: "adapt-area" }],
    credit: credit(FARMS_BY_SIZE),
    indicators: [FARMS_BY_SIZE],
  };
}

function adaptArea(): Built {
  const { entity, period } = adaptCountry();
  const rows = sizeRows(FARM_AREA_BY_SIZE, entity, period);
  if (rows.length === 0) throw new Error(`zero/adapt-area: no size classes for ${entity} ${period}`);
  const largest = [...rows].sort((a, b) => b.value - a.value || a.size.localeCompare(b.size))[0];
  const ind = indicator(FARM_AREA_BY_SIZE);
  return {
    id: "adapt-area",
    parent: "adapt-sizes",
    crumb: "Their land",
    kicker: `The land ${entityName(entity)}'s farms hold, by size`,
    headline: headline(FARM_AREA_BY_SIZE, entity, { "land-size": largest.size }, period),
    sentence: `of farmland in ${entityName(entity)} at its ${period} census is held by farms in the ${dimLabel(FARM_AREA_BY_SIZE, "land-size", largest.size).toLowerCase()} class, the most of any class.`,
    chart: bars(
      rows.map((r) => ({ key: r.size, label: dimLabel(FARM_AREA_BY_SIZE, "land-size", r.size), value: r.value, colour: CLEAN })),
      ind.unit.short,
      ind.display.decimals,
      period,
      "Area of the farms in each of FAO's land-size classes, in the order FAO lists them.",
    ),
    drills: [],
    credit: credit(FARM_AREA_BY_SIZE),
    indicators: [FARM_AREA_BY_SIZE],
  };
}

// --- the chapter -----------------------------------------------------------------------------------------------

/** The cards under the root: Gates's five questions, then the strategy. Activities open from their bands. */
export function rootDrills(): Drill[] {
  return [
    { label: "How much of the total", to: "shares" },
    { label: "How much it costs", to: "premium" },
    { label: "How much power", to: "power" },
    { label: "How much space", to: "space" },
    { label: "Net zero targets", to: "net-zero" },
    { label: "Electrify", to: "electrify" },
    { label: "Capture what is left", to: "capture" },
    { label: "Innovate", to: "innovate" },
    { label: "Adapt", to: "adapt" },
  ];
}

const NODES: Record<string, () => Built> = {
  power,
  "power-world-year": powerWorldYear,
  "power-city": powerCity,
  "power-city-year": powerCityYear,
  "power-home": powerHome,
  "power-home-year": powerHomeYear,
  space,
  "space-density": spaceDensity,
  premium,
  "premium-electricity": premiumElectricity,
  "premium-electricity-uk": premiumElectricityUk,
  "premium-materials": premiumMaterials,
  "premium-cement": premiumCement,
  "premium-ammonia": premiumAmmonia,
  "premium-heating": premiumHeating,
  "premium-heating-world": premiumHeatingWorld,
  "premium-cars": premiumCars,
  "premium-cars-life": premiumCarsLife,
  "premium-trucks": premiumTrucks,
  "premium-jet-fuel": premiumJetFuel,
  "premium-meat": premiumMeat,
  "premium-meat-ratio": premiumMeatRatio,
  "net-zero": netZero,
  "net-zero-emitters": netZeroEmitters,
  electrify,
  "electrify-countries": electrifyCountries,
  capture,
  "capture-pipeline": capturePipeline,
  "capture-projects": captureProjects,
  removal,
  "removal-forest": removalForest,
  innovate,
  "innovate-eu": innovateEu,
  adapt,
  "adapt-sizes": adaptSizes,
  "adapt-area": adaptArea,
};

function ids(): string[] {
  return ["root", "shares", ...activityIds(), ...Object.keys(NODES)];
}

function build(id: string): Built {
  if (id === "root") return rootNode(rootDrills());
  if (id === "shares") return sharesNode();
  if (isActivityNode(id)) return buildActivity(id);
  const f = NODES[id];
  if (!f) throw new Error(`unknown zero node ${id}`);
  return f();
}

export const zero = chapter(ids, build);

/**
 * The opening view before its cards are resolved, for a card in another chapter: resolving them would build views that
 * link back to that chapter (zero → action → zero), without end.
 */
export function zeroRoot(): Built {
  return build("root");
}

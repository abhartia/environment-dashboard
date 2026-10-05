import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { area, bars, type Built, chapter, credit, dimLabel, headline, latestPeriod, line, points } from "@/lib/dash/kit";

/**
 * The people chapter: what heat is doing to people. Deaths from heat → heatwave days, with and without the warming
 * people caused → working hours lost to heat, by sector. All modelled by the Lancet Countdown, and labelled so.
 */

const DEATHS = "heat.lancet-2025.deaths-global";
const BURNED = "burned-area.gwis.annual-by-land-cover";
const EFFIS = "burned-area.effis.europe-annual";
const HEATWAVE = "heat.lancet-2025.heatwave-days-global";
const LABOUR = "heat.lancet-2025.labour-hours-global";

const WARM = "#b2182b";
const GREY = "#9aa0a6";

const SECTORS: { id: string; colour: string }[] = [
  { id: "agriculture", colour: "#1b7837" },
  { id: "construction", colour: "#c75400" },
  { id: "manufacturing", colour: "#5f5f5f" },
  { id: "services", colour: "#2166ac" },
];

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

function root(): Built {
  const { short, decimals } = u(DEATHS);
  return {
    id: "root",
    parent: null,
    crumb: "Heat deaths",
    kicker: "People killed by heat",
    headline: headline(DEATHS, "WLD"),
    sentence: `from heat worldwide in ${latestPeriod(DEATHS)}, as estimated by the Lancet Countdown from temperatures and death records. A model, not a count.`,
    chart: area([{ key: "deaths", label: "Heat-related deaths", colour: WARM, points: points(DEATHS, "WLD") }], short, decimals, false),
    drills: [
      { label: "Heatwaves people lived through", to: "heatwaves" },
      { label: "Work lost to heat", to: "labour" },
      { label: "Land burned by fire", to: "fires" },
    ],
    credit: credit(DEATHS),
    indicators: [DEATHS],
  };
}

function heatwaves(): Built {
  const ind = indicator(HEATWAVE);
  const year = latestPeriod(HEATWAVE);
  const value = (scenario: string) => headline(HEATWAVE, "WLD", { scenario }, year).value;
  return {
    id: "heatwaves",
    parent: "root",
    crumb: "Heatwave days",
    kicker: "Heatwave days caused by climate change",
    headline: headline(HEATWAVE, "WLD", { scenario: "attributable" }, year),
    sentence: `of heatwave in ${year} that would not have happened without human-caused warming, by the Lancet Countdown's models.`,
    chart: bars(
      [
        { key: "observed", label: dimLabel(HEATWAVE, "scenario", "observed"), value: value("observed"), colour: WARM },
        { key: "counterfactual", label: dimLabel(HEATWAVE, "scenario", "counterfactual"), value: value("counterfactual"), colour: GREY },
      ],
      ind.unit.short,
      ind.display.decimals,
      year,
      "Average heatwave days per person in the year, as observed and as modelled for a world without human-caused warming.",
    ),
    drills: [{ label: "Work lost to heat", to: "labour" }],
    credit: credit(HEATWAVE),
    indicators: [HEATWAVE],
  };
}

function labour(): Built {
  const { short, decimals } = u(LABOUR);
  return {
    id: "labour",
    parent: "root",
    crumb: "Work lost",
    kicker: "Working hours lost to heat",
    headline: headline(LABOUR, "WLD", { sector: "total" }),
    sentence: `of potential work lost to heat stress worldwide in ${latestPeriod(LABOUR)}, by the Lancet Countdown. The bands are the sectors.`,
    chart: area(
      SECTORS.map((s) => ({ key: s.id, label: dimLabel(LABOUR, "sector", s.id), colour: s.colour, points: points(LABOUR, "WLD", { sector: s.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [],
    credit: credit(LABOUR),
    indicators: [LABOUR],
  };
}

/** GWIS's land-cover classes; the five add up to its all-land total. */
const LAND_COVERS: { id: string; colour: string }[] = [
  { id: "forest", colour: "#1b7837" },
  { id: "savannas", colour: "#e08214" },
  { id: "shrublands-grasslands", colour: "#b8860b" },
  { id: "croplands", colour: "#7f3b08" },
  { id: "other", colour: "#8b8b86" },
];
const CONTINENTS = ["UN_AFR", "UN_AME", "UN_ASI", "UN_EUR", "UN_OCE"];

function fires(): Built {
  const { short, decimals } = u(BURNED);
  const h = headline(BURNED, "WLD", { land_cover: "total" });
  return {
    id: "fires",
    parent: "root",
    crumb: "Wildfires",
    kicker: "Land burned by fire each year",
    headline: h,
    sentence: `burned worldwide in ${h.period}, mapped from NASA's MODIS satellites by the Global Wildfire Information System. The bands are the kinds of land that burned.`,
    chart: area(
      LAND_COVERS.map((c) => ({ key: c.id, label: dimLabel(BURNED, "land_cover", c.id), colour: c.colour, points: points(BURNED, "WLD", { land_cover: c.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [
      { label: "By continent", to: "fires-continents" },
      { label: "In Europe", to: "fires-europe" },
    ],
    credit: credit(BURNED),
    indicators: [BURNED],
  };
}

function firesContinents(): Built {
  const ind = indicator(BURNED);
  const year = latestPeriod(BURNED);
  const rows = CONTINENTS.map((c) => ({ entity: c, h: headline(BURNED, c, { land_cover: "total" }, year) })).sort((a, b) => b.h.value - a.h.value);
  return {
    id: "fires-continents",
    parent: "fires",
    crumb: "By continent",
    kicker: `${entityName(rows[0].entity).replace(/ \(as grouped by GWIS\)$/, "")} burns the most`,
    headline: rows[0].h,
    sentence: `burned in ${entityName(rows[0].entity)} in ${year}, the most of any continent.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.h.value, colour: "#c75400" })),
      ind.unit.short,
      ind.display.decimals,
      year,
      `Hectares burned in ${year}, by GWIS's grouping of countries into continents.`,
    ),
    drills: [{ label: "In Europe", to: "fires-europe" }],
    credit: credit(BURNED),
    indicators: [BURNED],
  };
}

function firesEurope(): Built {
  const { short, decimals } = u(EFFIS);
  const h = headline(EFFIS, "EU27");
  return {
    id: "fires-europe",
    parent: "fires",
    crumb: "Europe",
    kicker: "Land burned in Europe",
    headline: h,
    sentence: `burned in the EU in ${h.period}${h.status === "preliminary" ? " so far this year" : ""}, by fires of about 30 hectares or more, as mapped by the European Forest Fire Information System. The grey line is the wider group of countries in the EU Civil Protection Mechanism.`,
    chart: line(
      [
        { key: "EU27", label: entityName("EU27"), colour: "#c75400", points: points(EFFIS, "EU27") },
        { key: "UCPM", label: entityName("UCPM"), colour: GREY, points: points(EFFIS, "UCPM") },
      ],
      short,
      decimals,
    ),
    drills: [],
    credit: credit(EFFIS),
    indicators: [EFFIS],
  };
}

function ids(): string[] {
  return ["root", "heatwaves", "labour", "fires", "fires-continents", "fires-europe"];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "heatwaves") return heatwaves();
  if (id === "labour") return labour();
  if (id === "fires") return fires();
  if (id === "fires-continents") return firesContinents();
  if (id === "fires-europe") return firesEurope();
  throw new Error(`unknown people node ${id}`);
}

export const people = chapter(ids, build);

import "server-only";

import { indicator } from "@/lib/data";
import { area, bars, type Built, chapter, credit, dimLabel, headline, latestPeriod, points } from "@/lib/dash/kit";

/**
 * The people chapter: what heat is doing to people. Deaths from heat → heatwave days, with and without the warming
 * people caused → working hours lost to heat, by sector. All modelled by the Lancet Countdown, and labelled so.
 */

const DEATHS = "heat.lancet-2025.deaths-global";
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

function ids(): string[] {
  return ["root", "heatwaves", "labour"];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "heatwaves") return heatwaves();
  if (id === "labour") return labour();
  throw new Error(`unknown people node ${id}`);
}

export const people = chapter(ids, build);

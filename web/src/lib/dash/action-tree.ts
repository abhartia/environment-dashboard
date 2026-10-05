import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { bars, type Built, chapter, credit, dimLabel, headline, line, points } from "@/lib/dash/kit";
import type { Bar } from "@/lib/dash/types";

/**
 * The action chapter: what can be done, as measured. Household options ranked by the emissions they cut → one domain
 * at a time → who emits the most → how much carbon is left for 1.5 °C. Effects are described, never prescribed.
 */

const OPTIONS = "action.ivanova-2020.options";
const INEQUALITY = "co2-share.sei-inequality.income-groups-global";
const BUDGET_IGCC = "budget.igcc-2025.remaining-1p5";
const BUDGET_GCB = "emissions.gcb-2025.remaining-budget-1-5c";
const FLIGHTS = "travel.desnz-2026.flight-factors";
const CAR_BEV = "cars.icct-2025.lifecycle-bev-eu";
const CAR_PETROL = "cars.icct-2025.lifecycle-gasoline-eu";
const SOLUTIONS = "solutions.drawdown.climate-impact";
const POLICIES = "policy.stechemesser-2024.successful-interventions";

const SECTORS: { id: string; colour: string }[] = [
  { id: "electricity", colour: "#b8860b" },
  { id: "buildings", colour: "#c75400" },
  { id: "transport", colour: "#2166ac" },
  { id: "industry", colour: "#5f5f5f" },
];

const TOP = 15;
const DOMAINS: { id: string; colour: string }[] = [
  { id: "transport", colour: "#2166ac" },
  { id: "food", colour: "#1b7837" },
  { id: "housing", colour: "#c75400" },
];

type Option = { option: string; domain: string; value: number; statistic: "mean" | "median"; period: string };

/**
 * One value per option: the mean of the reviewed studies, or the median where the article states only a median
 * (the bar's label says which). Ivanova et al. state no value for some option and statistic pairs; those are absent.
 */
function options(domain?: string): Option[] {
  const obs = indicator(OPTIONS).observations.filter((o) => o.value !== null && (!domain || o.dims.domain === domain));
  const byOption = new Map<string, Option>();
  for (const o of obs) {
    const stat = o.dims.statistic as "mean" | "median";
    const prev = byOption.get(o.dims.option);
    if (prev && prev.statistic === "mean") continue;
    if (prev && stat === "median") continue;
    byOption.set(o.dims.option, { option: o.dims.option, domain: o.dims.domain, value: o.value as number, statistic: stat, period: o.period as string });
  }
  return [...byOption.values()].sort((a, b) => b.value - a.value || a.option.localeCompare(b.option));
}

function optionBars(rows: Option[]): Bar[] {
  return rows.map((r) => ({
    key: r.option,
    label: `${dimLabel(OPTIONS, "option", r.option)}${r.statistic === "median" ? " (median)" : ""}`,
    value: r.value,
    colour: DOMAINS.find((d) => d.id === r.domain)!.colour,
    drill: `domain-${r.domain}`,
  }));
}

function root(): Built {
  const ind = indicator(OPTIONS);
  const rows = options();
  const top = rows[0];
  return {
    id: "root",
    parent: null,
    crumb: "Household options",
    kicker: "What cuts a household's emissions most",
    headline: headline(OPTIONS, "WLD", { domain: top.domain, option: top.option, statistic: top.statistic }, top.period),
    sentence: `cut by ${dimLabel(OPTIONS, "option", top.option).toLowerCase()}, the ${top.statistic} across studies reviewed by Ivanova et al., mostly in high-income settings.`,
    chart: bars(
      optionBars(rows.slice(0, TOP)),
      ind.unit.short,
      ind.display.decimals,
      top.period,
      `The ${Math.min(TOP, rows.length)} largest of ${rows.length} options. Means of the reviewed studies unless marked.`,
      DOMAINS.map((d) => ({ label: dimLabel(OPTIONS, "domain", d.id), colour: d.colour })),
    ),
    drills: [
      ...DOMAINS.map((d) => ({ label: dimLabel(OPTIONS, "domain", d.id), to: `domain-${d.id}` })),
      { label: "What a flight emits", to: "flights" },
      { label: "Electric or petrol car", to: "cars" },
      { label: "Solutions at scale", to: "solutions" },
      { label: "Policies that worked", to: "policies" },
      { label: "Who emits the most", to: "inequality" },
      { label: "Carbon left for 1.5 °C", to: "budget" },
    ],
    credit: credit(OPTIONS),
    indicators: [OPTIONS],
  };
}

function domain(id: string): Built {
  const ind = indicator(OPTIONS);
  const rows = options(id);
  const top = rows[0];
  const name = dimLabel(OPTIONS, "domain", id);
  return {
    id: `domain-${id}`,
    parent: "root",
    crumb: name,
    kicker: `${name}: what cuts emissions most`,
    headline: headline(OPTIONS, "WLD", { domain: top.domain, option: top.option, statistic: top.statistic }, top.period),
    sentence: `cut by ${dimLabel(OPTIONS, "option", top.option).toLowerCase()}, the largest ${name.toLowerCase()} option in the studies Ivanova et al. reviewed.`,
    chart: bars(
      optionBars(rows).map((b) => ({ ...b, drill: undefined })),
      ind.unit.short,
      ind.display.decimals,
      top.period,
      `All ${rows.length} ${name.toLowerCase()} options with a stated value. Means of the reviewed studies unless marked.`,
    ),
    drills: DOMAINS.filter((d) => d.id !== id).map((d) => ({ label: dimLabel(OPTIONS, "domain", d.id), to: `domain-${d.id}` })),
    credit: credit(OPTIONS),
    indicators: [OPTIONS],
  };
}

function inequality(): Built {
  const ind = indicator(INEQUALITY);
  const groups: { id: string; colour: string }[] = [
    { id: "top-10", colour: "#b2182b" },
    { id: "top-1", colour: "#67001f" },
    { id: "bottom-50", colour: "#2166ac" },
  ];
  return {
    id: "inequality",
    parent: "root",
    crumb: "Who emits the most",
    kicker: "The richest tenth and everyone else",
    headline: headline(INEQUALITY, "WLD", { group: "top-10" }),
    sentence: `of the world's consumption emissions came from the richest 10% of people in ${headline(INEQUALITY, "WLD", { group: "top-10" }).period}, by the Stockholm Environment Institute.`,
    chart: line(
      groups.map((g) => ({ key: g.id, label: dimLabel(INEQUALITY, "group", g.id), colour: g.colour, points: points(INEQUALITY, "WLD", { group: g.id }) })),
      ind.unit.short,
      ind.display.decimals,
    ),
    drills: [],
    credit: credit(INEQUALITY),
    indicators: [INEQUALITY],
  };
}

function budget(): Built {
  const ind = indicator(BUDGET_IGCC);
  const igcc = headline(BUDGET_IGCC, "WLD");
  const gcb = headline(BUDGET_GCB, "WLD");
  if (igcc.period !== gcb.period || ind.unit.short !== indicator(BUDGET_GCB).unit.short) throw new Error("action/budget: the two estimates are not on the same basis");
  return {
    id: "budget",
    parent: "root",
    crumb: "Carbon left",
    kicker: "Carbon dioxide left for 1.5 °C",
    headline: igcc,
    sentence: "from the start of 2026 for an even chance of holding warming to 1.5 °C, by the Indicators of Global Climate Change. The Global Carbon Budget's estimate is the second bar.",
    chart: bars(
      [
        { key: "igcc", label: "Indicators of Global Climate Change 2025", value: igcc.value, colour: "#b2182b" },
        { key: "gcb", label: "Global Carbon Budget 2025", value: gcb.value, colour: "#9aa0a6" },
      ],
      ind.unit.short,
      ind.display.decimals,
      igcc.period,
      "Two assessments using different methods and data. Each counts from the start of 2026 with a 50% likelihood.",
    ),
    drills: [],
    credit: credit(BUDGET_IGCC, BUDGET_GCB),
    indicators: [BUDGET_IGCC, BUDGET_GCB],
  };
}

function flights(): Built {
  const ind = indicator(FLIGHTS);
  const rows = ind.observations
    .filter((o) => o.value !== null && o.dims.radiative_forcing === "with-rf")
    .map((o) => ({ haul: o.dims.haul, seat: o.dims.seat_class, value: o.value as number, period: o.period as string }))
    .sort((a, b) => b.value - a.value || a.haul.localeCompare(b.haul) || a.seat.localeCompare(b.seat));
  const h = headline(FLIGHTS, "GBR", { haul: "long-haul", seat_class: "economy", radiative_forcing: "with-rf" });
  return {
    id: "flights",
    parent: "root",
    crumb: "Flights",
    kicker: "What a flight emits, per passenger",
    headline: h,
    sentence:
      "for each kilometre a long-haul economy passenger flies, counting the extra warming from aircraft emissions at altitude (UK government conversion factors). Bigger seats carry more of the plane.",
    chart: bars(
      rows.map((r) => ({
        key: `${r.haul}-${r.seat}`,
        label: `${dimLabel(FLIGHTS, "haul", r.haul).replace(/, .*$/, "")}, ${dimLabel(FLIGHTS, "seat_class", r.seat).replace(/ class$/, "").toLowerCase()}`,
        value: r.value,
        colour: r.haul === "long-haul" && r.seat === "economy" ? "#b2182b" : "#2166ac",
      })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Per passenger-kilometre, with the extra warming at altitude; flights to or from the UK except the international row.",
    ),
    drills: [{ label: "Electric or petrol car", to: "cars" }],
    credit: credit(FLIGHTS),
    indicators: [FLIGHTS],
  };
}

function cars(): Built {
  const bev = headline(CAR_BEV, "EU27");
  const petrol = headline(CAR_PETROL, "EU27");
  if (bev.unit !== petrol.unit) throw new Error("action/cars: the two cars are not in the same unit");
  return {
    id: "cars",
    parent: "root",
    crumb: "Cars",
    kicker: "An electric car against a petrol one, over their whole lives",
    headline: bev,
    sentence:
      "per kilometre for a medium battery electric car sold in the EU, counting the car, its battery, the electricity it uses over its life and recycling (ICCT). The grey bar is a petrol car on the same basis.",
    chart: bars(
      [
        { key: "bev", label: "Battery electric", value: bev.value, colour: "#1b7837" },
        { key: "petrol", label: "Petrol", value: petrol.value, colour: "#8b8b86" },
      ],
      bev.unit,
      bev.decimals,
      bev.period,
      "Medium-size cars sold in the EU in 2025, on the EU's projected average electricity over the car's life.",
    ),
    drills: [{ label: "What a flight emits", to: "flights" }],
    credit: credit(CAR_BEV, CAR_PETROL),
    indicators: [CAR_BEV, CAR_PETROL],
  };
}

function solutions(): Built {
  const ind = indicator(SOLUTIONS);
  const at = (solution: string, level: string) =>
    ind.observations.find((o) => o.dims.solution === solution && o.dims.level === level && o.dims.basis === "gwp100" && o.value !== null)?.value ?? null;
  const rows = [...new Set(ind.observations.map((o) => o.dims.solution))]
    .map((solution) => ({ solution, high: at(solution, "achievable-high"), today: at(solution, "current") }))
    .filter((r): r is { solution: string; high: number; today: number | null } => r.high !== null)
    .sort((a, b) => b.high - a.high || a.solution.localeCompare(b.solution));
  const top = rows[0];
  const colour = "#1b7837";
  return {
    id: "solutions",
    parent: "root",
    crumb: "Solutions",
    kicker: "Which solutions could cut the most",
    headline: headline(SOLUTIONS, "WLD", { basis: "gwp100", level: "achievable-high", solution: top.solution }),
    sentence: `a year from ${dimLabel(SOLUTIONS, "solution", top.solution).toLowerCase()}, at the high end of what Project Drawdown finds achievable within decades. The dark part of each bar is the cut today. Solutions overlap, so they cannot be added up.`,
    chart: bars(
      rows.slice(0, TOP).map((r) => ({ key: r.solution, label: dimLabel(SOLUTIONS, "solution", r.solution), value: r.high, ...(r.today !== null ? { inner: r.today } : {}), colour })),
      ind.unit.short,
      ind.display.decimals,
      "2026",
      `The ${Math.min(TOP, rows.length)} largest of ${rows.length} solutions with an achievable range, on 100-year warming potentials.`,
      [
        { label: "Today", colour },
        { label: "Achievable, high end", colour: `${colour}59` },
      ],
    ),
    drills: [{ label: "Policies that worked", to: "policies" }],
    credit: credit(SOLUTIONS),
    indicators: [SOLUTIONS],
  };
}

function policies(): Built {
  const ind = indicator(POLICIES);
  const rows = ind.observations
    .filter((o) => o.value !== null)
    .map((o) => ({ entity: o.entity, sector: o.dims.sector, period: o.period as string, value: o.value as number }))
    .sort((a, b) => a.value - b.value || a.entity.localeCompare(b.entity));
  const top = rows[0];
  const colourOf = (sector: string) => SECTORS.find((x) => x.id === sector)?.colour ?? "#5f5f5f";
  return {
    id: "policies",
    parent: "root",
    crumb: "Policies",
    kicker: "Policies that measurably cut emissions",
    headline: headline(POLICIES, top.entity, { sector: top.sector, economy_group: ind.observations.find((o) => o.entity === top.entity && o.dims.sector === top.sector && o.period === top.period)!.dims.economy_group }, top.period),
    sentence: `in ${dimLabel(POLICIES, "sector", top.sector).toLowerCase()} emissions in ${entityName(top.entity)} around ${top.period}, the largest of the drops Stechemesser and colleagues traced to policies. Most combined several policies, so no drop can be credited to one policy alone.`,
    chart: bars(
      rows.slice(0, TOP).map((r) => ({
        key: `${r.entity}-${r.sector}-${r.period}`,
        label: `${entityName(r.entity)}, ${dimLabel(POLICIES, "sector", r.sector).toLowerCase()} (${r.period})`,
        value: r.value,
        colour: colourOf(r.sector),
      })),
      ind.unit.short,
      ind.display.decimals,
      top.period,
      `The ${Math.min(TOP, rows.length)} largest of ${rows.length} drops in a sector's emissions that the authors link to policies, against what their model expects without them.`,
      SECTORS.map((x) => ({ label: dimLabel(POLICIES, "sector", x.id), colour: x.colour })),
    ),
    drills: [{ label: "Solutions at scale", to: "solutions" }],
    credit: credit(POLICIES),
    indicators: [POLICIES],
  };
}

function ids(): string[] {
  return ["root", ...DOMAINS.map((d) => `domain-${d.id}`), "flights", "cars", "solutions", "policies", "inequality", "budget"];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "inequality") return inequality();
  if (id === "budget") return budget();
  if (id === "flights") return flights();
  if (id === "cars") return cars();
  if (id === "solutions") return solutions();
  if (id === "policies") return policies();
  const d = id.match(/^domain-([a-z]+)$/);
  if (d && DOMAINS.some((x) => x.id === d[1])) return domain(d[1]);
  throw new Error(`unknown action node ${id}`);
}

export const action = chapter(ids, build);

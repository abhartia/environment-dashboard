import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { bars, type Built, chapter, credit, crossDrill, dimLabel, entitiesWithData, headline, latestPeriod, line, matches, points, ranking } from "@/lib/dash/kit";
import type { Bar } from "@/lib/dash/types";
import { formatPeriod } from "@/lib/format";
import { zeroRoot } from "@/lib/dash/zero-tree";

/**
 * The action chapter: what can be done, as measured. Household options ranked by the emissions they cut → one domain
 * at a time → who emits the most → how much carbon is left for 1.5 °C → the largest emitters' new climate plans.
 * Policies lead on to carbon prices (and the money they raise for governments) and to public support; solutions lead
 * on to whether the changes needed are on track. Effects are described, never prescribed.
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
const PRICE_COVERAGE = "carbon-pricing.wb-2026.emissions-covered";
const PRICE_REVENUE = "carbon-pricing.wb-2026.revenue";
const SUPPORT = "attitudes.andre-2024.climate-support";
const NDC = "ndc.climate-watch.2025-ndc";
const NDC_COUNTS = "ndc.climate-watch.2025-ndc-countries";
const PROGRESS = "progress.scl.outcome-status";
/** All greenhouse gases by country, including land use (FAO): only used to pick and order the largest emitters. */
const GHG = "ghg.faostat.total";

const WILLING = "willing-to-contribute";
const PERCEIVED = "perceived-willing-others";
/** Andre et al.'s measures of what people believe about their compatriots, as opposed to their own answers. */
const ABOUT_OTHERS = new Set([PERCEIVED, "believe-majority-willing"]);

const YES = "#1b7837";
const NO = "#b2182b";

/** SCL's progress statuses, coloured from on track to the wrong direction; too little data is grey. */
const STATUS_COLOUR: Record<string, string> = {
  "on-track": "#1b7837",
  "off-track": "#f4a582",
  "well-off-track": "#d6604d",
  "right-direction": "#7fbc41",
  "wrong-direction": "#b2182b",
  "insufficient-data": "#9aa0a6",
};

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
      crossDrill("Getting to zero", "zero", zeroRoot()),
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
    drills: [{ label: "Countries' new climate plans", to: "ndc" }],
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
    drills: [
      { label: "Policies that worked", to: "policies" },
      { label: "Are the changes on track", to: "progress" },
    ],
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
    drills: [
      { label: "Solutions at scale", to: "solutions" },
      { label: "Carbon prices", to: "carbon-prices" },
      { label: "Public support", to: "support" },
    ],
    credit: credit(POLICIES),
    indicators: [POLICIES],
  };
}

function carbonPrices(): Built {
  const ind = indicator(PRICE_COVERAGE);
  const h = headline(PRICE_COVERAGE, "WLD");
  return {
    id: "carbon-prices",
    parent: "policies",
    crumb: "Carbon prices",
    kicker: "How much of the world's emissions carry a carbon price",
    headline: h,
    sentence: `were covered by a carbon tax or an emissions trading system in force in ${h.period}, the World Bank finds. This says how much of the world's emissions face a price, not how high the price is. Fuel taxes and carbon credits are not counted.`,
    // One published value: one bar, with nothing invented to compare it with.
    chart: bars(
      [{ key: "covered", label: "Covered by a carbon tax or emissions trading", value: h.value, colour: "#2166ac" }],
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `The World Bank's share for the carbon taxes and emissions trading systems in force in ${h.period}.`,
    ),
    drills: [{ label: "Money raised", to: "carbon-revenue" }],
    credit: credit(PRICE_COVERAGE),
    indicators: [PRICE_COVERAGE],
  };
}

/** What governments raised from carbon prices: a fact about public budgets, never a cost or saving for anyone. */
function carbonRevenue(): Built {
  const ind = indicator(PRICE_REVENUE);
  const h = headline(PRICE_REVENUE, "WLD");
  return {
    id: "carbon-revenue",
    parent: "carbon-prices",
    crumb: "Revenue",
    kicker: "What carbon prices raised for governments",
    headline: h,
    sentence: `raised by governments worldwide from carbon taxes and emissions trading systems in ${h.period}, as the World Bank estimates it.`,
    chart: bars(
      [{ key: "revenue", label: `Carbon taxes and emissions trading, ${h.period}`, value: h.value, colour: "#2166ac" }],
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "The World Bank's estimate of government revenue for the year, worldwide.",
    ),
    drills: [],
    credit: credit(PRICE_REVENUE),
    indicators: [PRICE_REVENUE],
  };
}

/** A survey question's label as Andre et al. publish it, without the bracketed name the authors give the measure. */
function measureLabel(measure: string): string {
  return dimLabel(SUPPORT, "measure", measure).replace(/ \([^)]*\)$/, "");
}

function support(): Built {
  const ind = indicator(SUPPORT);
  const willing = headline(SUPPORT, "WLD", { measure: WILLING });
  const perceived = headline(SUPPORT, "WLD", { measure: PERCEIVED });
  // The kicker's two claims, checked so a refresh that falsifies either fails the build.
  if (willing.value <= 50) throw new Error("action/support: the kicker says most would give, but the world share is not above half");
  if (perceived.value >= willing.value) throw new Error("action/support: the kicker says people underestimate others, but the believed share is not lower");
  const measures = ind.dimensions.find((d) => d.id === "measure")!.values.map((v) => v.id);
  const rows = ind.observations
    .filter((o) => matches(o, "WLD") && o.value !== null)
    .map((o) => ({ measure: o.dims.measure, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.measure.localeCompare(b.measure));
  const missing = measures.filter((m) => !rows.some((r) => r.measure === m));
  const own = "#2166ac";
  const others = "#9aa0a6";
  return {
    id: "support",
    parent: "policies",
    crumb: "Public support",
    kicker: "Most would give to fight warming, and underestimate others",
    headline: willing,
    sentence: `were ${measureLabel(WILLING).toLowerCase()} every month to fight global warming, the authors' world average across the countries surveyed (Andre and colleagues, Gallup World Poll ${formatPeriod(willing.period)}). Asked about their compatriots, people guessed fewer would.`,
    chart: bars(
      rows.map((r) => ({
        key: r.measure,
        label: measureLabel(r.measure),
        value: r.value,
        colour: ABOUT_OTHERS.has(r.measure) ? others : own,
        ...(r.measure === WILLING ? { drill: "support-countries" } : {}),
      })),
      ind.unit.short,
      ind.display.decimals,
      willing.period,
      `World averages of national shares, weighted by population, as the authors publish them.${missing.length ? ` No world value for: ${missing.map(measureLabel).join("; ")}.` : ""}`,
      [
        { label: "Their own answers", colour: own },
        { label: "What they believe of their compatriots", colour: others },
      ],
    ),
    drills: [{ label: "In the largest emitters", to: "support-countries" }],
    credit: credit(SUPPORT),
    indicators: [SUPPORT],
  };
}

/** The largest greenhouse gas emitters in FAO's latest year (countries and territories only), largest first. */
function largestEmitters(): string[] {
  return ranking(GHG, latestPeriod(GHG))
    .slice(0, TOP)
    .map((r) => r.entity);
}

function supportCountries(): Built {
  const ind = indicator(SUPPORT);
  const period = headline(SUPPORT, "WLD", { measure: WILLING }).period;
  const largest = largestEmitters();
  const rows = ranking(SUPPORT, period, { measure: WILLING }).filter((r) => largest.includes(r.entity));
  const missing = largest.filter((e) => !rows.some((r) => r.entity === e));
  const believed = (iso: string) => ind.observations.find((o) => matches(o, iso, { measure: PERCEIVED }) && o.period === period)?.value ?? null;
  const top = rows[0];
  const colour = "#2166ac";
  return {
    id: "support-countries",
    parent: "support",
    crumb: "Largest emitters",
    kicker: "Willing to give, in the largest emitters",
    headline: headline(SUPPORT, top.entity, { measure: WILLING }, period),
    sentence: `in ${entityName(top.entity)} were ${measureLabel(WILLING).toLowerCase()} every month to fight global warming, the highest share among the largest emitters shown. The dark part of each bar is the share people believed of their compatriots.`,
    chart: bars(
      rows.map((r) => {
        const inner = believed(r.entity);
        return { key: r.entity, label: entityName(r.entity), value: r.value, colour, ...(inner !== null ? { inner } : {}) };
      }),
      ind.unit.short,
      ind.display.decimals,
      period,
      `National shares, Gallup World Poll ${formatPeriod(period)}, for the largest greenhouse gas emitters in ${latestPeriod(GHG)} (FAO).${missing.length ? ` No data for ${missing.map(entityName).join(", ")} in the survey.` : ""}`,
      [
        { label: measureLabel(PERCEIVED), colour },
        { label: measureLabel(WILLING), colour: `${colour}59` },
      ],
    ),
    drills: [],
    credit: credit(SUPPORT, GHG),
    indicators: [SUPPORT, GHG],
  };
}

/**
 * A country's 2025 NDC record in Climate Watch's own words: the status it gives (submitted, withdrawn) and the
 * document it coded, from the label it publishes with each value.
 */
function ndcRecord(iso: string): { value: number; date: string; status: string; document: string } {
  const o = indicator(NDC).observations.find((x) => matches(x, iso, { question: "submitted" }));
  if (!o || o.value === null || o.period === null || !o.note) throw new Error(`${NDC}: no submission record for ${iso}`);
  const m = o.note.match(/^Climate Watch: (.+?)\. Document: (.+) \(https?:\/\/\S+\)\.$/);
  if (!m) throw new Error(`${NDC}: the note for ${iso} no longer reads "Climate Watch: <status>. Document: <title> (<url>)."`);
  return { value: o.value, date: o.period, status: m[1], document: m[2] };
}

/** The largest emitters that Climate Watch has a 2025 NDC record for, largest first. */
function ndcEmitters(): string[] {
  const coded = new Set(entitiesWithData(NDC, { question: "submitted" }));
  return largestEmitters().filter((e) => coded.has(e));
}

function ndc(): Built {
  const ind = indicator(NDC_COUNTS);
  const submitted = headline(NDC_COUNTS, "WLD", { question: "submitted", answer: "yes" });
  const questions = ind.dimensions.find((d) => d.id === "question")!.values.filter((v) => v.id !== "submitted");
  return {
    id: "ndc",
    parent: "budget",
    crumb: "New climate plans",
    kicker: "Countries that have sent a new climate plan",
    headline: submitted,
    sentence: `had sent their 2025 climate plan (NDC, a country's plan under the Paris Agreement) when Climate Watch's tracker was read on ${formatPeriod(submitted.period)}, each EU member state counted once. Each bar counts the plans Climate Watch finds one thing in.`,
    chart: bars(
      questions.map((q) => ({
        key: q.id,
        label: q.label,
        value: headline(NDC_COUNTS, "WLD", { question: q.id, answer: "yes" }).value,
        colour: YES,
      })),
      ind.unit.short,
      ind.display.decimals,
      submitted.period,
      "Countries whose plan Climate Watch codes yes for each question, from the plans' texts.",
    ),
    drills: [{ label: "The largest emitters' plans", to: "ndc-emitters" }],
    credit: credit(NDC_COUNTS),
    indicators: [NDC_COUNTS],
  };
}

function emittersPlans(): Built {
  const ind = indicator(NDC);
  const largest = largestEmitters();
  const shown = ndcEmitters();
  const missing = largest.filter((e) => !shown.includes(e));
  const first = shown[0];
  const rec = ndcRecord(first);
  const which = first === largest[0] ? "the largest emitter" : "the largest emitter Climate Watch has a record for";
  return {
    id: "ndc-emitters",
    parent: "ndc",
    crumb: "Largest emitters",
    kicker: "Have the largest emitters sent new climate plans?",
    headline: headline(NDC, first, { question: "submitted" }),
    sentence: `for "${dimLabel(NDC, "question", "submitted")}" in ${entityName(first)}, ${which} of greenhouse gases (FAO): Climate Watch records "${rec.status}", dated ${formatPeriod(rec.date)}. An NDC is a country's climate plan under the Paris Agreement. Each bar opens what a country's plan contains.`,
    chart: bars(
      shown.map((iso) => {
        const r = ndcRecord(iso);
        return { key: iso, label: entityName(iso), value: r.value, colour: r.value === 1 ? YES : NO, drill: `ndc-${iso}` };
      }),
      ind.unit.short,
      ind.display.decimals,
      rec.date,
      `The largest greenhouse gas emitters in ${latestPeriod(GHG)} (FAO), largest first; ${ind.unit.label}.${missing.length ? ` Climate Watch has no record for ${missing.map(entityName).join(", ")}.` : ""}`,
    ),
    drills: [],
    credit: credit(NDC, GHG),
    indicators: [NDC, GHG],
  };
}

function ndcCountry(iso: string): Built {
  const ind = indicator(NDC);
  const name = entityName(iso);
  const rec = ndcRecord(iso);
  const questions = ind.dimensions.find((d) => d.id === "question")!.values.map((v) => v.id);
  const answers = questions.map((q) => ({ q, o: ind.observations.find((o) => matches(o, iso, { question: q }) && o.value !== null) }));
  const missing = answers.filter((a) => !a.o).map((a) => dimLabel(NDC, "question", a.q));
  return {
    id: `ndc-${iso}`,
    parent: "ndc-emitters",
    crumb: name,
    kicker: `${name}'s climate plan, question by question`,
    headline: headline(NDC, iso, { question: "submitted" }),
    sentence: `for "${dimLabel(NDC, "question", "submitted")}": Climate Watch records "${rec.status}" for ${name}, dated ${formatPeriod(rec.date)}, for the document "${rec.document}". Each bar is one question it answers from the plan's text: a full bar is yes, an empty one no.`,
    chart: bars(
      answers.flatMap(({ q, o }) => (o ? [{ key: q, label: dimLabel(NDC, "question", q), value: o.value as number, colour: o.value === 1 ? YES : NO }] : [])),
      ind.unit.short,
      ind.display.decimals,
      rec.date,
      `Climate Watch's coding of the plan's text; ${ind.unit.label}.${missing.length ? ` No answer from Climate Watch for: ${missing.join("; ")}.` : ""}`,
    ),
    drills: [],
    credit: credit(NDC),
    indicators: [NDC],
  };
}

function progress(): Built {
  const ind = indicator(PROGRESS);
  const h = headline(PROGRESS, "WLD", { status: "on-track" });
  const statuses = ind.dimensions.find((d) => d.id === "status")!.values.map((v) => v.id);
  const rows = statuses.flatMap((s) => {
    const o = ind.observations.find((x) => matches(x, "WLD", { status: s }) && x.period === h.period && x.value !== null);
    return o ? [{ status: s, value: o.value as number }] : [];
  });
  const missing = statuses.filter((s) => !rows.some((r) => r.status === s));
  return {
    id: "progress",
    parent: "solutions",
    crumb: "On track?",
    kicker: "Are the changes needed on track?",
    headline: h,
    sentence: `were on track on ${formatPeriod(h.period)}, by Systems Change Lab's own assessment of the shifts it tracks, from power and transport to land, food and finance. Each bar is the share at one status.`,
    chart: bars(
      rows.map((r) => {
        const colour = STATUS_COLOUR[r.status];
        if (!colour) throw new Error(`action/progress: no colour for status ${r.status}`);
        return { key: r.status, label: dimLabel(PROGRESS, "status", r.status), value: r.value, colour };
      }),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `Shares of Systems Change Lab's outcome indicators by its own progress status, in its order. Indicators built on International Energy Agency data are left out.${missing.length ? ` No share for: ${missing.map((s) => dimLabel(PROGRESS, "status", s)).join("; ")}.` : ""}`,
    ),
    drills: [],
    credit: credit(PROGRESS),
    indicators: [PROGRESS],
  };
}

function ids(): string[] {
  return [
    "root",
    ...DOMAINS.map((d) => `domain-${d.id}`),
    "flights",
    "cars",
    "solutions",
    "progress",
    "policies",
    "carbon-prices",
    "carbon-revenue",
    "support",
    "support-countries",
    "inequality",
    "budget",
    "ndc",
    "ndc-emitters",
    ...ndcEmitters().map((iso) => `ndc-${iso}`),
  ];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "inequality") return inequality();
  if (id === "budget") return budget();
  if (id === "flights") return flights();
  if (id === "cars") return cars();
  if (id === "solutions") return solutions();
  if (id === "progress") return progress();
  if (id === "policies") return policies();
  if (id === "carbon-prices") return carbonPrices();
  if (id === "carbon-revenue") return carbonRevenue();
  if (id === "support") return support();
  if (id === "support-countries") return supportCountries();
  if (id === "ndc") return ndc();
  if (id === "ndc-emitters") return emittersPlans();
  const n = id.match(/^ndc-([A-Z0-9]+)$/);
  if (n && ndcEmitters().includes(n[1])) return ndcCountry(n[1]);
  const d = id.match(/^domain-([a-z]+)$/);
  if (d && DOMAINS.some((x) => x.id === d[1])) return domain(d[1]);
  throw new Error(`unknown action node ${id}`);
}

export const action = chapter(ids, build);

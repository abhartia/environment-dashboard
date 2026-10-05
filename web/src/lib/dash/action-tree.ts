import "server-only";

import { indicator } from "@/lib/data";
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

function ids(): string[] {
  return ["root", ...DOMAINS.map((d) => `domain-${d.id}`), "inequality", "budget"];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "inequality") return inequality();
  if (id === "budget") return budget();
  const d = id.match(/^domain-([a-z]+)$/);
  if (d && DOMAINS.some((x) => x.id === d[1])) return domain(d[1]);
  throw new Error(`unknown action node ${id}`);
}

export const action = chapter(ids, build);

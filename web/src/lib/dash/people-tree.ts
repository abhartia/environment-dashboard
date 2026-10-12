import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { dimValues } from "@/lib/dash/food-nodes";
import { area, bars, type Built, chapter, credit, crossTo, dimLabel, headline, latestPeriod, line, points } from "@/lib/dash/kit";
import type { Bar, SeriesPoint } from "@/lib/dash/types";
import { formatReadable } from "@/lib/format";

/**
 * The people chapter: what these changes mean for people. It opens on hot extremes becoming more frequent (how many
 * times as often a once-a-decade hottest day comes at each level of warming, from the IPCC's models), with downpours and
 * drought and what has been observed since the 1950s below it. Then what the changes do to people: heatwave days
 * caused by the warming (and for babies and people over 65), deaths from heat of any cause and work lost, children's
 * lifetimes, people forced from home by weather disasters, people living below high tide, early deaths from the smoke
 * of burning coal, oil and gas, and fires and their smoke. Each says what its producer measured, and links back to the
 * change it follows. The Lancet Countdown's ids live only here, so a new report year changes one file.
 */

const EXTREMES = "extremes.ipcc-ar6.frequency-by-warming-level";
const OBSERVED = "extremes.ipcc-ar6.observed-regions";
const HUMAN = "warming.igcc-2025.human-induced";
const HOTTEST = "extremes.igcc-2025.txx-land";
const RAIN = "rain.lancet-2025.extreme-events";
const DROUGHT = "drought.lancet-2025.land-share";
const HEATWAVE = "heat.lancet-2025.heatwave-days-global";
const VULNERABLE = "heat.lancet-2025.heatwave-days-vulnerable";
const DEATHS = "heat.lancet-2025.deaths-global";
const LABOUR = "heat.lancet-2025.labour-hours-global";
const CHILDREN = "lifetime.grant-2025.unprecedented-heatwaves";
const DISPLACED = "displacement.idmc-gidd.weather-by-hazard";
const BELOW_TIDE = "coastal.kulp-strauss-2019.below-high-tide";
const BELOW_FLOOD = "coastal.kulp-strauss-2019.annual-flood";
const FOSSIL_DEATHS = "air-pollution.lancet-2025.fossil-deaths";
const BY_SECTOR = "air-pollution.lancet-2025.deaths-by-sector-fuel";
const FIRE_SMOKE = "smoke.lancet-2025.wildfire-deaths";
const BURNED = "burned-area.gwis.annual-by-land-cover";
const EFFIS = "burned-area.effis.europe-annual";

/**
 * Values their producers attribute to human-caused warming: only these may sit under "Caused by the warming" (checked
 * when a node is resolved, lib/dash/chapters.ts). Lancet Countdown splits observed heatwave days into those a world
 * without the warming would also have had and the rest; the IPCC gives how much more often extremes come at each level
 * of warming.
 */
export const ATTRIBUTED: { indicator: string; dims?: Record<string, string> }[] = [{ indicator: HEATWAVE, dims: { scenario: "attributable" } }, { indicator: EXTREMES }];

/** The level of warming the opening view reads at: the lowest the IPCC gives, which the world has already passed. */
const NOW_LEVEL = "1.0";

const WARM = "#b2182b";
const RAIN_COLOUR = "#2166ac";
const DRY = "#b8860b";
const GREY = "#9aa0a6";
const INK = "#1f1f1f";

const SECTORS: { id: string; colour: string }[] = [
  { id: "agriculture", colour: "#1b7837" },
  { id: "construction", colour: "#c75400" },
  { id: "manufacturing", colour: "#5f5f5f" },
  { id: "services", colour: "#2166ac" },
];

/** A legend swatch for the outer bar of an inner/outer pair, which the bar chart draws at 35% (lib/dash/types.ts Bar). */
const pale = (colour: string) => `color-mix(in srgb, ${colour} 35%, transparent)`;

/** A producer's label inside a sentence: only its first letter lowered ("Warming reaching 1.5 °C" -> "warming reaching 1.5 °C"). */
const lowerFirst = (label: string) => label.charAt(0).toLowerCase() + label.slice(1);

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

/**
 * An annual series' points with a gap marked where the producer publishes no years (a line is never drawn across
 * years nobody measured). Only the absence is marked; no value is made up.
 */
function withGaps(pts: SeriesPoint[]): SeriesPoint[] {
  return pts.flatMap((p, i) => (i > 0 && p[0] - pts[i - 1][0] > 1 ? [[pts[i - 1][0] + 1, null] as SeriesPoint, p] : [p]));
}

/** The levels of warming the IPCC data gives, in order, as bars of one kind of extreme. */
function levelBars(extreme: string, colour: string): Bar[] {
  return dimValues(EXTREMES, "level").map((l) => ({ key: l.id, label: l.label, value: headline(EXTREMES, "WLD", { extreme, level: l.id }).value, colour }));
}

/** The very likely range the IPCC gives for one extreme at one level, in words, from the published bounds. */
function likelyRange(extreme: string, level: string): string {
  const o = indicator(EXTREMES).observations.find((x) => x.entity === "WLD" && x.dims.extreme === extreme && x.dims.level === level);
  if (!o || o.lower === null || o.upper === null) throw new Error(`${EXTREMES}: no range for ${extreme} at ${level}`);
  const d = indicator(EXTREMES).display.decimals;
  return `${formatReadable(o.lower, d)} to ${formatReadable(o.upper, d)}`;
}

/** "Now" holds only while the warming people caused is at or above the level the view reads at. */
function passed(level: string): void {
  if (headline(HUMAN, "WLD").value < Number(level)) throw new Error(`people: the warming people caused is below ${level} °C, so "already passed" no longer holds`);
}

function extremeView(id: string, extreme: string, parent: string | null, crumb: string, kicker: string, what: string, colour: string, drills: Built["drills"]): Built {
  const ind = indicator(EXTREMES);
  passed(NOW_LEVEL);
  const h = headline(EXTREMES, "WLD", { extreme, level: NOW_LEVEL });
  // A kicker that says "more often" must hold across the IPCC's very likely range, not only at its median.
  const lower = ind.observations.find((o) => o.entity === "WLD" && o.dims.extreme === extreme && o.dims.level === NOW_LEVEL)?.lower;
  if (/more often/.test(kicker) && !(lower !== null && lower !== undefined && lower > 1)) throw new Error(`people/${id}: the very likely range at ${NOW_LEVEL} °C includes no change, so "more often" does not hold`);
  const levelWords = dimLabel(EXTREMES, "level", NOW_LEVEL);
  return {
    id,
    parent,
    crumb,
    kicker,
    headline: h,
    sentence: `for ${what}, at ${levelWords}, which the world has passed, by the IPCC's climate models. The bars are each level of warming.`,
    chart: bars(
      levelBars(extreme, colour),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `How many times as often, by level of warming: the median of the CMIP6 climate models (very likely range at ${levelWords}: ${likelyRange(extreme, NOW_LEVEL)}). Modelled, not counted.`,
    ),
    drills,
    credit: credit(EXTREMES, HUMAN),
    indicators: [EXTREMES, HUMAN],
  };
}

function root(): Built {
  return extremeView("root", "hot-10yr", null, "Extremes", "Hot extremes, more often", "a hottest day over land that came once a decade then", WARM, [
    { label: "The hottest day of the year", to: "hottest-day" },
    { label: "Seen since the 1950s", to: "observed" },
    { label: "Downpours", to: "downpours" },
    { label: "Drought", to: "drought" },
    { label: "Heatwave days caused by the warming", to: "heatwaves" },
    { label: "Children born today", to: "children" },
    { label: "Forced from home", to: "displaced" },
    { label: "Deaths from heat", to: "deaths" },
    { label: "People below high tide", to: "coasts" },
    { label: "Smoke from burning fuel", to: "smoke" },
    { label: "Fires", to: "fires" },
    crossTo("How much warmer the world is", "heat:root"),
  ]);
}

function hottestDay(): Built {
  const { short, decimals } = u(HOTTEST);
  const h = headline(HOTTEST, "WLD");
  // The kicker says the hottest day is getting hotter: its latest ten years must average above its first ten.
  const vals = points(HOTTEST, "WLD").flatMap((p) => (p[1] === null ? [] : [p[1]]));
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  if (vals.length < 20 || mean(vals.slice(-10)) <= mean(vals.slice(0, 10))) throw new Error("people/hottest-day: the latest ten years are not hotter than the first ten, so the kicker no longer holds");
  return {
    id: "hottest-day",
    parent: "root",
    crumb: "Hottest day",
    kicker: "The hottest day of the year is getting hotter",
    headline: h,
    sentence: `above its 1961–1990 average for the hottest day of ${h.period}, averaged over land outside Antarctica, in the ERA5 reanalysis (Indicators of Global Climate Change). How hot the hottest day gets, not how often heat comes.`,
    chart: line([{ key: "txx", label: "Hottest day of the year over land (ERA5)", colour: WARM, points: points(HOTTEST, "WLD") }], short, decimals),
    drills: [{ label: "Seen since the 1950s", to: "observed" }, crossTo("How much warmer the world is", "heat:root")],
    credit: credit(HOTTEST),
    indicators: [HOTTEST],
  };
}

function downpours(): Built {
  return extremeView("downpours", "rain-10yr", "root", "Downpours", "Downpours, more often", "a wettest day over land that came once a decade then", RAIN_COLOUR, [{ label: "Extreme rain days measured", to: "rain-observed" }]);
}

function drought(): Built {
  return extremeView("drought", "drought-10yr", "root", "Drought", "Drought in the regions drying out", "a drought that came once a decade then, in the regions drying out", DRY, [
    { label: "Land in extreme drought", to: "drought-observed" },
  ]);
}

function rainObserved(): Built {
  const { short, decimals } = u(RAIN);
  const h = headline(RAIN, "WLD");
  return {
    id: "rain-observed",
    parent: "downpours",
    crumb: "Measured",
    kicker: "Extreme rain days at the average place on land",
    headline: h,
    sentence: `in ${h.period}, in the ERA5-Land reanalysis, by the Lancet Countdown. Heavy rain or snow, not floods; the gap is years the producer does not publish.`,
    chart: line([{ key: "rain", label: "Extreme rain days a year, average over land", colour: RAIN_COLOUR, points: withGaps(points(RAIN, "WLD")) }], short, decimals),
    drills: [],
    credit: credit(RAIN),
    indicators: [RAIN],
  };
}

function droughtObserved(): Built {
  const { short, decimals } = u(DROUGHT);
  const months = dimValues(DROUGHT, "months");
  const h = headline(DROUGHT, "WLD", { months: months[0].id });
  return {
    id: "drought-observed",
    parent: "drought",
    crumb: "Measured",
    kicker: "Land in extreme drought",
    headline: h,
    sentence: `of the world's land had ${lowerFirst(months[0].label)} of extreme drought in ${h.period}, by the Lancet Countdown's index (SPEI-6, against 1986–2005). Warmer air itself pushes this index towards drought; it does not count droughts caused by climate change.`,
    chart: line(
      months.map((m, i) => ({ key: m.id, label: m.label, colour: i === 0 ? DRY : i === 1 ? "#8c510a" : "#543005", points: points(DROUGHT, "WLD", { months: m.id }) })),
      short,
      decimals,
    ),
    drills: [],
    credit: credit(DROUGHT),
    indicators: [DROUGHT],
  };
}

function observed(): Built {
  const ind = indicator(OBSERVED);
  const extremes = dimValues(OBSERVED, "extreme");
  const value = (extreme: string, assessment: string) => headline(OBSERVED, "WLD", { extreme, assessment }).value;
  const h = headline(OBSERVED, "WLD", { extreme: extremes[0].id, assessment: "increase" });
  return {
    id: "observed",
    parent: "root",
    crumb: "Since the 1950s",
    kicker: "Where extremes have increased since the 1950s",
    headline: h,
    sentence: `saw ${lowerFirst(extremes[0].label)} increase since the 1950s, as assessed by the IPCC. The inner bars are regions where it has high confidence that people's influence contributed.`,
    chart: bars(
      extremes.map((e) => ({ key: e.id, label: e.label, value: value(e.id, "increase"), inner: value(e.id, "increase-high"), colour: WARM })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Regions where each extreme increased, and inside, those with high confidence in a human contribution (IPCC AR6, Figure SPM.3). Where data are limited or studies disagree, no change is claimed.",
      [
        { label: dimLabel(OBSERVED, "assessment", "increase"), colour: pale(WARM) },
        { label: dimLabel(OBSERVED, "assessment", "increase-high"), colour: WARM },
      ],
    ),
    drills: [{ label: "Downpours", to: "downpours" }, { label: "Drought", to: "drought" }],
    credit: credit(OBSERVED),
    indicators: [OBSERVED],
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
    kicker: "Heatwave days caused by climate change (modelled)",
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
    drills: [{ label: "Babies and people over 65", to: "vulnerable" }, { label: "Work lost to heat", to: "labour" }, crossTo("How much of the warming people caused", "heat:human")],
    credit: credit(HEATWAVE),
    indicators: [HEATWAVE],
  };
}

function vulnerable(): Built {
  const { short, decimals } = u(VULNERABLE);
  const groups = dimValues(VULNERABLE, "group");
  const older = groups.find((g) => g.id === "over-65");
  if (!older) throw new Error(`${VULNERABLE}: no over-65 group`);
  const h = headline(VULNERABLE, "WLD", { group: older.id });
  return {
    id: "vulnerable",
    parent: "heatwaves",
    crumb: "Babies and over-65s",
    kicker: "Heatwaves lived through by the most vulnerable",
    headline: h,
    sentence: `of heatwave for ${lowerFirst(older.label)} in ${h.period}, by the Lancet Countdown from temperatures where people live. Each line is one age group.`,
    chart: line(
      groups.map((g, i) => ({ key: g.id, label: g.label, colour: g.id === older.id ? WARM : i === 0 ? "#f4a582" : "#d6604d", points: points(VULNERABLE, "WLD", { group: g.id }) })),
      short,
      decimals,
    ),
    drills: [],
    credit: credit(VULNERABLE),
    indicators: [VULNERABLE],
  };
}

function deaths(): Built {
  const { short, decimals } = u(DEATHS);
  return {
    id: "deaths",
    parent: "root",
    crumb: "Heat deaths",
    kicker: "People killed by heat",
    headline: headline(DEATHS, "WLD"),
    sentence: `from heat worldwide in ${latestPeriod(DEATHS)}, as estimated by the Lancet Countdown from temperatures and death records. A model, not a count, and heat of any cause, not only the warming people caused.`,
    chart: area([{ key: "deaths", label: "Heat-related deaths", colour: WARM, points: points(DEATHS, "WLD") }], short, decimals, false),
    drills: [{ label: "Work lost to heat", to: "labour" }, crossTo("Money for adapting", "zero:adapt-finance")],
    credit: credit(DEATHS),
    indicators: [DEATHS],
  };
}

function labour(): Built {
  const { short, decimals } = u(LABOUR);
  return {
    id: "labour",
    parent: "deaths",
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

function children(): Built {
  const ind = indicator(CHILDREN);
  const cohorts = dimValues(CHILDREN, "cohort");
  const pathways = dimValues(CHILDREN, "pathway");
  const young = cohorts.at(-1)!;
  const old = cohorts[0];
  const value = (cohort: string, pathway: string) => indicator(CHILDREN).observations.find((o) => o.entity === "WLD" && o.dims.cohort === cohort && o.dims.pathway === pathway)?.value ?? null;
  // The bars set the youngest generation against the oldest at each pathway; a pathway without both is not drawn.
  const shown = pathways.filter((p) => value(young.id, p.id) !== null && value(old.id, p.id) !== null);
  if (!shown.length) throw new Error(`${CHILDREN}: no pathway gives both ${young.id} and ${old.id}`);
  for (const p of shown) if ((value(young.id, p.id) as number) <= (value(old.id, p.id) as number)) throw new Error(`people/children: at ${p.id} the younger generation is not worse off, so the view's claim fails`);
  const h = headline(CHILDREN, "WLD", { cohort: young.id, pathway: shown[0].id });
  return {
    id: "children",
    parent: "root",
    crumb: `Children ${lowerFirst(young.label)}`,
    kicker: `Heatwaves in the lifetime of a child ${lowerFirst(young.label)}`,
    headline: h,
    sentence: `would live through more heatwaves than all but one in ten thousand lifetimes could in a climate without warming, with ${lowerFirst(shown[0].label)} (Grant and others, 2025; modelled). The inner bars are people ${lowerFirst(old.label)}.`,
    chart: bars(
      shown.map((p) => ({ key: p.id, label: p.label, value: value(young.id, p.id) as number, inner: value(old.id, p.id) as number, colour: WARM })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `Share of each generation projected to face unprecedented lifetime heatwave exposure, by how much the world warms by 2100. Projected with ISIMIP impact models; "unprecedented" is a statistical threshold, not a count of deaths.`,
      [
        { label: young.label, colour: pale(WARM) },
        { label: old.label, colour: WARM },
      ],
    ),
    drills: [{ label: "Heatwave days caused by the warming", to: "heatwaves" }],
    credit: credit(CHILDREN),
    indicators: [CHILDREN],
  };
}

const HAZARD_COLOURS = ["#2166ac", "#5e3c99", "#c75400", "#8c510a", "#b2182b", "#4d9221", "#7f7f7f", "#01665e", "#9e9ac8"];

/**
 * The first year IDMC splits China's figures by hazard: before it, IDMC files China's whole disaster displacement
 * under "Mixed disasters" (said in the indicator's own per-year notes), so those years' weather totals leave China out
 * and are not comparable with later ones.
 */
function comparableFrom(): number {
  const lumped = indicator(DISPLACED)
    .observations.filter((o) => o.entity === "WLD" && o.dims.hazard === "all" && /Mixed disasters'.*the largest: China/.test(o.note ?? ""))
    .map((o) => Number(o.period));
  if (!lumped.length) throw new Error(`${DISPLACED}: no year notes China under "Mixed disasters"; the view's start year needs rethinking`);
  return Math.max(...lumped) + 1;
}

function displaced(): Built {
  const { short, decimals } = u(DISPLACED);
  const hazards = dimValues(DISPLACED, "hazard").filter((hz) => hz.id !== "all");
  const from = comparableFrom();
  const h = headline(DISPLACED, "WLD", { hazard: "all" });
  return {
    id: "displaced",
    parent: "root",
    crumb: "Forced from home",
    kicker: "Forced from home by weather disasters",
    headline: h,
    sentence: `in ${h.period}, by floods, storms, fires and other weather, calculated from IDMC's event data. Movements, not people (one person can move twice), including evacuations before a disaster. Monitoring has grown, so a rise is not a trend; the chart starts in ${from}, the first year IDMC splits China's figures by hazard instead of filing them all under "Mixed disasters". The bands are its hazards.`,
    chart: area(
      hazards.map((hz, i) => ({ key: hz.id, label: hz.label, colour: HAZARD_COLOURS[i % HAZARD_COLOURS.length], points: points(DISPLACED, "WLD", { hazard: hz.id }, from) })),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "People below high tide", to: "coasts" }],
    credit: credit(DISPLACED),
    indicators: [DISPLACED],
  };
}

/** Kulp and Strauss's lead projections: K14 (Kopp and others, 2014), probabilistic and closely aligned with the IPCC. */
const LEAD_PROJECTION = "k14";

function coasts(): Built {
  const ind = indicator(BELOW_TIDE);
  const scenarios = dimValues(BELOW_TIDE, "scenario");
  const h = headline(BELOW_TIDE, "WLD", { scenario: "present", projection: "none" });
  // Today's people under today's and future sea levels: one bar per year and scenario, as published.
  const rows = ind.observations
    .filter((o) => o.entity === "WLD" && o.value !== null && (o.dims.projection === "none" || o.dims.projection === LEAD_PROJECTION))
    .sort((a, b) => (a.period ?? "").localeCompare(b.period ?? "") || scenarios.findIndex((x) => x.id === a.dims.scenario) - scenarios.findIndex((x) => x.id === b.dims.scenario));
  const flood = (o: (typeof rows)[number]) =>
    indicator(BELOW_FLOOD).observations.find((x) => x.entity === "WLD" && x.period === o.period && x.dims.scenario === o.dims.scenario && x.dims.projection === o.dims.projection)?.value ?? null;
  return {
    id: "coasts",
    parent: "root",
    crumb: "Below high tide",
    kicker: "People living below high tide",
    headline: h,
    sentence: `lived on land below the high-tide line in ${h.period}, by Kulp and Strauss's elevation model. It ignores sea walls and other defences, so it counts people at risk, not people flooded. The paler bars are land below the yearly flood line; later years put the same people under projected seas.`,
    chart: bars(
      rows.map((o) => {
        const f = flood(o);
        if (f === null) throw new Error(`${BELOW_FLOOD}: no value for ${o.period} ${o.dims.scenario} ${o.dims.projection}`);
        return { key: `${o.period}-${o.dims.scenario}`, label: o.dims.scenario === "present" ? `${o.period}` : `${o.period}, ${dimLabel(BELOW_TIDE, "scenario", o.dims.scenario)}`, value: f, inner: o.value as number, colour: RAIN_COLOUR };
      }),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      `People on land below the yearly coastal flood line (bar) and below high tide (inside), at today's sea level and under projected seas (${dimLabel(BELOW_TIDE, "projection", LEAD_PROJECTION)}), with population held as it was. Not a forecast of floods.`,
      [
        { label: "Below the yearly flood line", colour: pale(RAIN_COLOUR) },
        { label: "Below high tide", colour: RAIN_COLOUR },
      ],
    ),
    drills: [crossTo("How much the sea has risen", "oceans:root"), crossTo("Money for adapting", "zero:adapt-finance")],
    credit: credit(BELOW_TIDE, BELOW_FLOOD),
    indicators: [BELOW_TIDE, BELOW_FLOOD],
  };
}

function smoke(): Built {
  const { short, decimals } = u(FOSSIL_DEATHS);
  const fuels = dimValues(FOSSIL_DEATHS, "fuel").filter((f) => f.id !== "total");
  const h = headline(FOSSIL_DEATHS, "WLD", { fuel: "total" });
  return {
    id: "smoke",
    parent: "root",
    crumb: "Smoke from fuel",
    kicker: "Estimated early deaths from the smoke of coal, oil and gas",
    headline: h,
    sentence: `in ${h.period}, from breathing the fine particles that burning coal, oil and gas puts into the air, modelled by the Lancet Countdown. A harm of the burning itself, not of the warming. The bands are the fuels.`,
    chart: area(
      fuels.map((f, i) => ({ key: f.id, label: f.label, colour: i === 0 ? INK : "#8c510a", points: points(FOSSIL_DEATHS, "WLD", { fuel: f.id }), ...(i === 0 ? { drill: "smoke-power" } : {}) })),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "Coal power stations", to: "smoke-power" }, crossTo("Which fuels we burn", "emissions:fuels")],
    credit: credit(FOSSIL_DEATHS),
    indicators: [FOSSIL_DEATHS],
  };
}

function smokePower(): Built {
  const { short, decimals } = u(BY_SECTOR);
  const sectors = dimValues(BY_SECTOR, "sector");
  const fuels = dimValues(BY_SECTOR, "fuel");
  const power = sectors.find((s) => /power/i.test(s.label));
  const coal = fuels.find((f) => /coal/i.test(f.label));
  const oilGas = fuels.find((f) => /liquid|gas/i.test(f.label));
  if (!power || !coal || !oilGas) throw new Error(`${BY_SECTOR}: no power-plant sector, or no coal or liquids-and-gas fuel`);
  const h = headline(BY_SECTOR, "WLD", { sector: power.id, fuel: coal.id });
  // The sentence says most of these deaths come from coal: a refresh that made that false must fail the build.
  if (h.value <= headline(BY_SECTOR, "WLD", { sector: power.id, fuel: oilGas.id }, h.period).value) throw new Error("people/smoke-power: coal is no longer the larger share");
  return {
    id: "smoke-power",
    parent: "smoke",
    crumb: "Power stations",
    kicker: "Estimated early deaths from coal power stations' smoke",
    headline: h,
    sentence: `early deaths in ${h.period} from the smoke of power stations burning coal, more than from those burning oil and gas (the grey line), modelled by the Lancet Countdown. Clean electricity replaces them.`,
    chart: line(
      [
        { key: "coal", label: `${power.label}, ${coal.label.toLowerCase()}`, colour: INK, points: points(BY_SECTOR, "WLD", { sector: power.id, fuel: coal.id }) },
        { key: "oil-gas", label: `${power.label}, ${oilGas.label.toLowerCase()}`, colour: GREY, points: points(BY_SECTOR, "WLD", { sector: power.id, fuel: oilGas.id }) },
      ],
      short,
      decimals,
    ),
    drills: [crossTo("Electricity from clean sources", "energy:root")],
    credit: credit(BY_SECTOR),
    indicators: [BY_SECTOR],
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
      { label: "Deaths from the smoke", to: "fire-smoke" },
      { label: "By continent", to: "fires-continents" },
      { label: "In Europe", to: "fires-europe" },
    ],
    credit: credit(BURNED),
    indicators: [BURNED],
  };
}

function fireSmoke(): Built {
  const { short, decimals } = u(FIRE_SMOKE);
  const h = headline(FIRE_SMOKE, "WLD");
  return {
    id: "fire-smoke",
    parent: "fires",
    crumb: "Smoke deaths",
    kicker: "Deaths from wildfire smoke",
    headline: h,
    sentence: `from breathing the smoke of fires in ${h.period}, modelled by the Lancet Countdown. Fires of every cause; not attributed to climate change.`,
    chart: area([{ key: "smoke", label: "Deaths from wildfire smoke", colour: "#c75400", points: points(FIRE_SMOKE, "WLD") }], short, decimals, false),
    drills: [{ label: "Smoke from burning fuel", to: "smoke" }],
    credit: credit(FIRE_SMOKE),
    indicators: [FIRE_SMOKE],
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

const NODES: Record<string, () => Built> = {
  root,
  "hottest-day": hottestDay,
  observed,
  downpours,
  "rain-observed": rainObserved,
  drought,
  "drought-observed": droughtObserved,
  heatwaves,
  vulnerable,
  deaths,
  labour,
  children,
  displaced,
  coasts,
  smoke,
  "smoke-power": smokePower,
  fires,
  "fire-smoke": fireSmoke,
  "fires-continents": firesContinents,
  "fires-europe": firesEurope,
};

function ids(): string[] {
  return Object.keys(NODES);
}

function build(id: string): Built {
  const make = NODES[id];
  if (!make) throw new Error(`unknown people node ${id}`);
  return make();
}

export const people = chapter(ids, build);

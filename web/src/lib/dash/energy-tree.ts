import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { area, bars, type Built, chapter, credit, headline, latestPeriod, line, points, ranking } from "@/lib/dash/kit";
import type { Series } from "@/lib/dash/types";
import { formatPeriod } from "@/lib/format";

/**
 * The energy chapter: how fast the switch away from fossil fuels is going. Clean electricity → what makes it → by
 * country (its mix, its grid's carbon) → month by month (each source, then fossil power against a year earlier); then
 * all energy, not just electricity (by fuel; in total, then by country), renewable power built (its share of all
 * plants; what electricity from new plants costs), electric cars, and who has electricity at all (then where the
 * fewest do).
 */

const CLEAN = "electricity.ember.clean-share-world";
const MIX = "electricity.ember.mix-world";
const CLEAN_BY_COUNTRY = "electricity.ember.clean-share-by-country";
const MIX_BY_COUNTRY = "electricity.ember.mix-by-country";
const INTENSITY = "electricity.ember.lifecycle-intensity-by-country";
const MONTHLY_CLEAN = "electricity.ember.monthly-clean-share-world";
const MONTHLY_MIX = "electricity.ember.monthly-mix-world";
const MONTHLY_FOSSIL_CHANGE = "electricity.ember.monthly-fossil-change-world";
const FOSSIL_SHARE = "energy.eia.fossil-share";
const PRIMARY_BY_FUEL = "energy.eia.primary-by-fuel";
const PRIMARY_TOTAL = "energy.eia.primary-total";
const CAPACITY = "capacity.irena.renewables-world";
const CAPACITY_BY_TECH = "capacity.irena.renewables-by-technology-world";
const CAPACITY_SHARE = "capacity.irena.renewable-share-world";
const COST = "lcoe.irena.by-technology-world";
const EV = "ev.iea.sales-share";
const ACCESS = "access.wb-wdi.electricity";
const EMITTERS = "emissions.gcp-2025.fossil-co2-by-country";

const TOP = 15;
const CLEAN_COLOUR = "#1b7837";
const FOSSIL_COLOUR = "#2b2b2b";
const GREY = "#9aa0a6";
/** Quantities that are not one source (all energy used, people with electricity). */
const NEUTRAL_COLOUR = "#3f4a5a";

/** Ember's fossil sources: selecting one of their monthly bands opens fossil power against a year earlier. */
const FOSSIL_SOURCES = new Set(["coal", "gas", "other-fossil"]);

/** Ember's sources, fossil first then clean. Each colour is at least 3:1 on white. */
const SOURCES: { id: string; label: string; colour: string }[] = [
  { id: "coal", label: "Coal", colour: "#2b2b2b" },
  { id: "gas", label: "Gas", colour: "#6b6b6b" },
  { id: "other-fossil", label: "Other fossil", colour: "#8b8b86" },
  { id: "nuclear", label: "Nuclear", colour: "#7b5ea7" },
  { id: "hydro", label: "Hydro", colour: "#2166ac" },
  { id: "wind", label: "Wind", colour: "#1b9e77" },
  { id: "solar", label: "Solar", colour: "#b8860b" },
  { id: "bioenergy", label: "Bioenergy", colour: "#1b7837" },
  { id: "other-renewables", label: "Other renewables", colour: "#4d9221" },
];

const PRIMARY_FUELS: { id: string; label: string; colour: string }[] = [
  { id: "coal", label: "Coal", colour: "#2b2b2b" },
  { id: "petroleum", label: "Oil", colour: "#8c510a" },
  { id: "natural-gas", label: "Gas", colour: "#6b6b6b" },
  { id: "nuclear", label: "Nuclear", colour: "#7b5ea7" },
  { id: "renewables-and-other", label: "Renewables and other", colour: "#1b7837" },
];

const TECHNOLOGIES: { id: string; label: string; colour: string }[] = [
  { id: "hydropower", label: "Hydropower", colour: "#2166ac" },
  { id: "onshore-wind", label: "Onshore wind", colour: "#1b9e77" },
  { id: "offshore-wind", label: "Offshore wind", colour: "#006d5b" },
  { id: "solar-pv", label: "Solar panels", colour: "#b8860b" },
  { id: "csp", label: "Concentrated solar", colour: "#c75400" },
  { id: "bioenergy", label: "Bioenergy", colour: "#1b7837" },
  { id: "geothermal", label: "Geothermal", colour: "#a8447f" },
  { id: "marine", label: "Marine", colour: "#053061" },
];

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

/** The largest-emitting countries that Ember also covers, so the country views follow the countries that matter most. */
function countryCodes(): string[] {
  const covered = new Set(ranking(CLEAN_BY_COUNTRY, latestPeriod(CLEAN_BY_COUNTRY)).map((r) => r.entity));
  return ranking(EMITTERS, latestPeriod(EMITTERS))
    .map((r) => r.entity)
    .filter((e) => covered.has(e))
    .slice(0, TOP);
}

function root(): Built {
  const { short, decimals } = u(CLEAN);
  return {
    id: "root",
    parent: null,
    crumb: "Electricity",
    kicker: "Electricity from clean sources",
    headline: headline(CLEAN, "WLD"),
    sentence: `of the world's electricity came from renewables and nuclear in ${latestPeriod(CLEAN)}, by Ember.`,
    chart: area([{ key: "clean", label: "Clean share of electricity", colour: CLEAN_COLOUR, points: points(CLEAN, "WLD"), drill: "mix" }], short, decimals, false),
    drills: [
      { label: "What makes our electricity", to: "mix" },
      { label: "By country", to: "countries" },
      { label: "Month by month", to: "monthly" },
      { label: "All energy, not just electricity", to: "all-energy" },
      { label: "Renewable power built", to: "capacity" },
      { label: "Electric cars", to: "ev" },
      { label: "Who has electricity", to: "access" },
    ],
    credit: credit(CLEAN),
    indicators: [CLEAN],
  };
}

function mixSeries(entity: string, id: string): Series[] {
  return SOURCES.map((s) => ({ key: s.id, label: s.label, colour: s.colour, points: points(id, entity, { source: s.id }) })).filter((s) =>
    s.points.some((p) => p[1] !== null),
  );
}

function largestSource(id: string, entity: string, period: string) {
  return SOURCES.map((s) => ({ s, v: indicator(id).observations.find((o) => o.entity === entity && o.period === period && o.dims.source === s.id)?.value ?? null }))
    .filter((x): x is { s: (typeof SOURCES)[number]; v: number } => x.v !== null)
    .sort((a, b) => b.v - a.v)[0].s;
}

function mix(): Built {
  const { short, decimals } = u(MIX);
  const year = latestPeriod(MIX);
  const top = largestSource(MIX, "WLD", year);
  return {
    id: "mix",
    parent: "root",
    crumb: "By source",
    kicker: `${top.label} is the largest source`,
    headline: headline(MIX, "WLD", { source: top.id }, year),
    sentence: `of the world's electricity came from ${top.label.toLowerCase()} in ${year}. The bands add up to all electricity generated.`,
    chart: area(mixSeries("WLD", MIX), short, decimals, true),
    drills: [{ label: "By country", to: "countries" }],
    credit: credit(MIX),
    indicators: [MIX],
  };
}

function countries(): Built {
  const { short, decimals } = u(CLEAN_BY_COUNTRY);
  const year = latestPeriod(CLEAN_BY_COUNTRY);
  const codes = countryCodes();
  const rows = ranking(CLEAN_BY_COUNTRY, year).filter((r) => codes.includes(r.entity));
  return {
    id: "countries",
    parent: "root",
    crumb: "By country",
    kicker: "The largest emitters' electricity",
    headline: headline(CLEAN_BY_COUNTRY, rows[0].entity, {}, year),
    sentence: `of ${entityName(rows[0].entity)}'s electricity was clean in ${year}, the most among the largest emitters. Select a country.`,
    chart: bars(
      rows.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: CLEAN_COLOUR, drill: `c-${r.entity}` })),
      short,
      decimals,
      year,
      `The ${rows.length} countries with the largest fossil carbon dioxide emissions, ranked by the clean share of their electricity.`,
    ),
    drills: [],
    credit: credit(CLEAN_BY_COUNTRY, EMITTERS),
    indicators: [CLEAN_BY_COUNTRY, EMITTERS],
  };
}

function country(iso: string): Built {
  const { short, decimals } = u(CLEAN_BY_COUNTRY);
  const name = entityName(iso);
  return {
    id: `c-${iso}`,
    parent: "countries",
    crumb: name,
    kicker: `${name}: electricity from clean sources`,
    headline: headline(CLEAN_BY_COUNTRY, iso),
    sentence: `of ${name}'s electricity came from renewables and nuclear in ${headline(CLEAN_BY_COUNTRY, iso).period}. The grey line is the world.`,
    chart: line(
      [
        { key: iso, label: name, colour: CLEAN_COLOUR, points: points(CLEAN_BY_COUNTRY, iso) },
        { key: "WLD", label: "World", colour: GREY, points: points(CLEAN_BY_COUNTRY, "WLD") },
      ],
      short,
      decimals,
    ),
    drills: [
      { label: "What makes its electricity", to: `c-${iso}-mix` },
      { label: "How much carbon per unit", to: `c-${iso}-intensity` },
    ],
    credit: credit(CLEAN_BY_COUNTRY),
    indicators: [CLEAN_BY_COUNTRY],
  };
}

function countryMix(iso: string): Built {
  const { short, decimals } = u(MIX_BY_COUNTRY);
  const name = entityName(iso);
  const year = headline(CLEAN_BY_COUNTRY, iso).period;
  const top = largestSource(MIX_BY_COUNTRY, iso, year);
  return {
    id: `c-${iso}-mix`,
    parent: `c-${iso}`,
    crumb: "By source",
    kicker: `${name}: ${top.label.toLowerCase()} is the largest source`,
    headline: headline(MIX_BY_COUNTRY, iso, { source: top.id }, year),
    sentence: `of ${name}'s electricity came from ${top.label.toLowerCase()} in ${year}.`,
    chart: area(mixSeries(iso, MIX_BY_COUNTRY), short, decimals, true),
    drills: [{ label: "How much carbon per unit", to: `c-${iso}-intensity` }],
    credit: credit(MIX_BY_COUNTRY),
    indicators: [MIX_BY_COUNTRY],
  };
}

function countryIntensity(iso: string): Built {
  const { short, decimals } = u(INTENSITY);
  const name = entityName(iso);
  return {
    id: `c-${iso}-intensity`,
    parent: `c-${iso}`,
    crumb: "Carbon per unit",
    kicker: `How much carbon ${name}'s electricity carries`,
    headline: headline(INTENSITY, iso),
    sentence: `for each kilowatt-hour generated in ${name} in ${headline(INTENSITY, iso).period}, counting power stations' whole life cycle. The grey line is the world.`,
    chart: line(
      [
        { key: iso, label: name, colour: FOSSIL_COLOUR, points: points(INTENSITY, iso) },
        { key: "WLD", label: "World", colour: GREY, points: points(INTENSITY, "WLD") },
      ],
      short,
      decimals,
    ),
    drills: [{ label: "What makes its electricity", to: `c-${iso}-mix` }],
    credit: credit(INTENSITY),
    indicators: [INTENSITY],
  };
}

function monthly(): Built {
  const { short, decimals } = u(MONTHLY_CLEAN);
  return {
    id: "monthly",
    parent: "root",
    crumb: "Month by month",
    kicker: "Clean electricity, month by month",
    headline: headline(MONTHLY_CLEAN, "WLD"),
    sentence: "of the world's electricity was clean in the latest month Ember reports.",
    chart: line([{ key: "clean", label: "Clean share, monthly", colour: CLEAN_COLOUR, points: points(MONTHLY_CLEAN, "WLD"), drill: "monthly-mix" }], short, decimals),
    drills: [{ label: "Each source, month by month", to: "monthly-mix" }],
    credit: credit(MONTHLY_CLEAN),
    indicators: [MONTHLY_CLEAN],
  };
}

function monthlyMix(): Built {
  const { short, decimals } = u(MONTHLY_MIX);
  const month = latestPeriod(MONTHLY_MIX);
  const top = largestSource(MONTHLY_MIX, "WLD", month);
  return {
    id: "monthly-mix",
    parent: "monthly",
    crumb: "Each source",
    kicker: "Each source, month by month",
    headline: headline(MONTHLY_MIX, "WLD", { source: top.id }, month),
    sentence: `of the world's electricity came from ${top.label.toLowerCase()} in ${formatPeriod(month)}, the largest source that month (Ember's estimate). The bands add up to all electricity generated.`,
    chart: area(
      mixSeries("WLD", MONTHLY_MIX).map((s) => (FOSSIL_SOURCES.has(s.key) ? { ...s, drill: "monthly-fossil" } : s)),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "Fossil power against a year earlier", to: "monthly-fossil" }],
    credit: credit(MONTHLY_MIX),
    indicators: [MONTHLY_MIX],
  };
}

function monthlyFossil(): Built {
  const { short, decimals } = u(MONTHLY_FOSSIL_CHANGE);
  const h = headline(MONTHLY_FOSSIL_CHANGE, "WLD");
  return {
    id: "monthly-fossil",
    parent: "monthly-mix",
    crumb: "Fossil power",
    kicker: "Fossil electricity against a year earlier",
    headline: h,
    sentence: `in the world's electricity from coal, gas and other fossil fuels in ${formatPeriod(h.period)} (Ember's estimate). Below zero, the world made less fossil power than in the same month a year before.`,
    chart: line([{ key: "fossil-change", label: "Fossil generation, change from a year earlier", colour: FOSSIL_COLOUR, points: points(MONTHLY_FOSSIL_CHANGE, "WLD") }], short, decimals),
    drills: [],
    credit: credit(MONTHLY_FOSSIL_CHANGE),
    indicators: [MONTHLY_FOSSIL_CHANGE],
  };
}

function allEnergy(): Built {
  const { short, decimals } = u(FOSSIL_SHARE);
  return {
    id: "all-energy",
    parent: "root",
    crumb: "All energy",
    kicker: "All energy, not just electricity",
    headline: headline(FOSSIL_SHARE, "WLD"),
    sentence: `of all the energy the world used in ${latestPeriod(FOSSIL_SHARE)} came from coal, oil and gas, including for transport, heating and industry (US EIA).`,
    chart: area([{ key: "fossil", label: "Fossil share of primary energy", colour: FOSSIL_COLOUR, points: points(FOSSIL_SHARE, "WLD"), drill: "all-energy-fuels" }], short, decimals, false),
    drills: [
      { label: "Split by fuel", to: "all-energy-fuels" },
      { label: "How much in total", to: "all-energy-total" },
    ],
    credit: credit(FOSSIL_SHARE),
    indicators: [FOSSIL_SHARE],
  };
}

function allEnergyTotal(): Built {
  const { short, decimals } = u(PRIMARY_TOTAL);
  return {
    id: "all-energy-total",
    parent: "all-energy",
    crumb: "In total",
    kicker: "How much energy the world uses",
    headline: headline(PRIMARY_TOTAL, "WLD"),
    sentence: `used worldwide in ${latestPeriod(PRIMARY_TOTAL)}, every fuel counted, by the US EIA's accounting. Other agencies count wind, solar and hydro power differently, so their totals are not comparable.`,
    chart: area([{ key: "total", label: "Total primary energy", colour: NEUTRAL_COLOUR, points: points(PRIMARY_TOTAL, "WLD"), drill: "all-energy-countries" }], short, decimals, false),
    drills: [{ label: "By country", to: "all-energy-countries" }],
    credit: credit(PRIMARY_TOTAL),
    indicators: [PRIMARY_TOTAL],
  };
}

function allEnergyCountries(): Built {
  const { short, decimals } = u(PRIMARY_TOTAL);
  const year = latestPeriod(PRIMARY_TOTAL);
  const ranked = ranking(PRIMARY_TOTAL, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "all-energy-countries",
    parent: "all-energy-total",
    crumb: "By country",
    kicker: "Which countries use the most energy",
    headline: headline(PRIMARY_TOTAL, top[0].entity, {}, year),
    sentence: `used in ${entityName(top[0].entity)} in ${year}, the most of any country or territory. These are national totals, not amounts per person.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: NEUTRAL_COLOUR })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, as the US EIA accounts for energy.`,
    ),
    drills: [],
    credit: credit(PRIMARY_TOTAL),
    indicators: [PRIMARY_TOTAL],
  };
}

function allEnergyFuels(): Built {
  const { short, decimals } = u(PRIMARY_BY_FUEL);
  const year = latestPeriod(PRIMARY_BY_FUEL);
  const top = PRIMARY_FUELS.map((f) => ({ f, v: headline(PRIMARY_BY_FUEL, "WLD", { fuel: f.id }, year).value })).sort((a, b) => b.v - a.v)[0].f;
  return {
    id: "all-energy-fuels",
    parent: "all-energy",
    crumb: "By fuel",
    kicker: `${top.label} is the largest source of energy`,
    headline: headline(PRIMARY_BY_FUEL, "WLD", { fuel: top.id }, year),
    sentence: `of energy from ${top.label.toLowerCase()} in ${year}.`,
    chart: area(
      PRIMARY_FUELS.map((f) => ({ key: f.id, label: f.label, colour: f.colour, points: points(PRIMARY_BY_FUEL, "WLD", { fuel: f.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [],
    credit: credit(PRIMARY_BY_FUEL),
    indicators: [PRIMARY_BY_FUEL],
  };
}

function capacity(): Built {
  const { short, decimals } = u(CAPACITY_BY_TECH);
  return {
    id: "capacity",
    parent: "root",
    crumb: "Renewable power built",
    kicker: "Renewable power plants in the world",
    headline: headline(CAPACITY, "WLD"),
    sentence: `of renewable generating capacity at the end of ${latestPeriod(CAPACITY)}, by IRENA.`,
    chart: area(
      TECHNOLOGIES.map((t) => ({ key: t.id, label: t.label, colour: t.colour, points: points(CAPACITY_BY_TECH, "WLD", { technology: t.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [
      { label: "Share of all power plants", to: "capacity-share" },
      { label: "What new plants' electricity costs", to: "capacity-cost" },
    ],
    credit: credit(CAPACITY, CAPACITY_BY_TECH),
    indicators: [CAPACITY, CAPACITY_BY_TECH],
  };
}

function capacityShare(): Built {
  const { short, decimals } = u(CAPACITY_SHARE);
  return {
    id: "capacity-share",
    parent: "capacity",
    crumb: "Share of all plants",
    kicker: "Renewables' share of the world's power plants",
    headline: headline(CAPACITY_SHARE, "WLD"),
    sentence: `of the world's electricity generating capacity was renewable at the end of ${latestPeriod(CAPACITY_SHARE)}, by IRENA. This counts the power plants, not the electricity they made.`,
    chart: area([{ key: "renewable-share", label: "Renewable share of generating capacity", colour: CLEAN_COLOUR, points: points(CAPACITY_SHARE, "WLD") }], short, decimals, false),
    drills: [],
    credit: credit(CAPACITY_SHARE),
    indicators: [CAPACITY_SHARE],
  };
}

/** Every technology IRENA publishes a cost for, with this chapter's label and colour (an unknown one fails the build). */
function costTechnologies(): (typeof TECHNOLOGIES)[number][] {
  const dim = indicator(COST).dimensions.find((d) => d.id === "technology");
  if (!dim) throw new Error(`${COST}: no technology dimension`);
  return dim.values.map((v) => {
    const t = TECHNOLOGIES.find((x) => x.id === v.id);
    if (!t) throw new Error(`${COST}: no label or colour for technology ${v.id}`);
    return t;
  });
}

function capacityCost(): Built {
  const { short, decimals } = u(COST);
  const year = latestPeriod(COST);
  const techs = costTechnologies();
  // The technology with the lowest published cost in the latest year, so the sentence's "lowest" follows the data.
  const ranked = techs
    .map((t) => ({ t, v: indicator(COST).observations.find((o) => o.entity === "WLD" && o.period === year && o.dims.technology === t.id)?.value ?? null }))
    .filter((x): x is { t: (typeof TECHNOLOGIES)[number]; v: number } => x.v !== null)
    .sort((a, b) => a.v - b.v || a.t.id.localeCompare(b.t.id));
  if (ranked.length === 0) throw new Error(`${COST}: no technology has a ${year} value`);
  const lowest = ranked[0].t;
  return {
    id: "capacity-cost",
    parent: "capacity",
    crumb: "Cost of new power",
    kicker: "What electricity from new renewable plants costs",
    headline: headline(COST, "WLD", { technology: lowest.id }, year),
    sentence: `for electricity from ${lowest.label.toLowerCase()} plants that started in ${year}, the lowest of the technologies IRENA tracks. A worldwide average over each plant's life, before the cost of fitting variable power into grids; costs vary widely between countries and projects.`,
    chart: line(
      techs.map((t) => ({ key: t.id, label: t.label, colour: t.colour, points: points(COST, "WLD", { technology: t.id }) })),
      short,
      decimals,
    ),
    drills: [],
    credit: credit(COST),
    indicators: [COST],
  };
}

function ev(): Built {
  const { short, decimals } = u(EV);
  return {
    id: "ev",
    parent: "root",
    crumb: "Electric cars",
    kicker: "Electric cars as a share of new cars",
    headline: headline(EV, "WLD", { mode: "cars" }),
    sentence: `of new cars sold worldwide in ${headline(EV, "WLD", { mode: "cars" }).period} were electric (battery or plug-in hybrid), by the IEA.`,
    chart: area([{ key: "cars", label: "Electric share of new car sales", colour: CLEAN_COLOUR, points: points(EV, "WLD", { mode: "cars" }) }], short, decimals, false),
    drills: [],
    credit: credit(EV),
    indicators: [EV],
  };
}

function access(): Built {
  const { short, decimals } = u(ACCESS);
  return {
    id: "access",
    parent: "root",
    crumb: "Who has electricity",
    kicker: "People with access to electricity",
    headline: headline(ACCESS, "WLD"),
    sentence: `of the world's people had access to electricity in ${latestPeriod(ACCESS)}, by the World Bank.`,
    chart: area([{ key: "access", label: "Share of people with electricity", colour: NEUTRAL_COLOUR, points: points(ACCESS, "WLD"), drill: "access-countries" }], short, decimals, false),
    drills: [{ label: "Where the fewest have it", to: "access-countries" }],
    credit: credit(ACCESS),
    indicators: [ACCESS],
  };
}

function accessCountries(): Built {
  const { short, decimals } = u(ACCESS);
  const year = latestPeriod(ACCESS);
  // Lowest share first (ties by code), so the sentence's "lowest" follows the data.
  const ranked = [...ranking(ACCESS, year)].sort((a, b) => a.value - b.value || a.entity.localeCompare(b.entity));
  const fewest = ranked.slice(0, TOP);
  const name = entityName(fewest[0].entity);
  return {
    id: "access-countries",
    parent: "access",
    crumb: "Where the fewest have it",
    kicker: "Where the fewest people have electricity",
    headline: headline(ACCESS, fewest[0].entity, {}, year),
    sentence: `of people in ${name} had access to electricity in ${year}, the lowest share of any country or territory the World Bank reports for that year.`,
    chart: bars(
      fewest.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: NEUTRAL_COLOUR })),
      short,
      decimals,
      year,
      `The ${fewest.length} lowest of ${ranked.length} countries and territories with a value for ${year}.`,
    ),
    drills: [],
    credit: credit(ACCESS),
    indicators: [ACCESS],
  };
}

function ids(): string[] {
  const out = [
    "root",
    "mix",
    "countries",
    "monthly",
    "monthly-mix",
    "monthly-fossil",
    "all-energy",
    "all-energy-fuels",
    "all-energy-total",
    "all-energy-countries",
    "capacity",
    "capacity-share",
    "capacity-cost",
    "ev",
    "access",
    "access-countries",
  ];
  for (const iso of countryCodes()) out.push(`c-${iso}`, `c-${iso}-mix`, `c-${iso}-intensity`);
  return out;
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "mix") return mix();
  if (id === "countries") return countries();
  if (id === "monthly") return monthly();
  if (id === "monthly-mix") return monthlyMix();
  if (id === "monthly-fossil") return monthlyFossil();
  if (id === "all-energy") return allEnergy();
  if (id === "all-energy-fuels") return allEnergyFuels();
  if (id === "all-energy-total") return allEnergyTotal();
  if (id === "all-energy-countries") return allEnergyCountries();
  if (id === "capacity") return capacity();
  if (id === "capacity-share") return capacityShare();
  if (id === "capacity-cost") return capacityCost();
  if (id === "ev") return ev();
  if (id === "access") return access();
  if (id === "access-countries") return accessCountries();
  const c = id.match(/^c-([A-Z0-9_]+)(-mix|-intensity)?$/);
  if (c) return c[2] === "-mix" ? countryMix(c[1]) : c[2] === "-intensity" ? countryIntensity(c[1]) : country(c[1]);
  throw new Error(`unknown energy node ${id}`);
}

export const energy = chapter(ids, build);

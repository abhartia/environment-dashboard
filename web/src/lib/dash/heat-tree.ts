import "server-only";

import { indicator } from "@/lib/data";
import { calendarPeriod, formatPeriod } from "@/lib/format";
import { entityName } from "@/lib/dash/entities";
import { bars, type Built, chapter, credit, headline, latestPeriod, line, periodToX, points, ranking } from "@/lib/dash/kit";
import type { Bar, Drill, Series, SeriesPoint } from "@/lib/dash/types";

/**
 * The heat chapter: how much warmer the world is. The global record → do independent records agree → how much of it
 * people caused (and IGCC's own figure for the latest year) → month by month → day by day → the sea surface (day by
 * day) → which countries' emissions caused it → where it is warming → each country in degrees → hot days ahead. Each
 * record keeps its producer's own baseline, named in its label.
 */

const HADCRUT = "temp.hadcrut5.annual-1850-1900";
const NOAA = "temp.noaaglobaltemp-v6.annual-1850-1900";
const GISTEMP = "temp.gistemp-v4.annual-1880-1899";
const ERA5 = "temp.c3s-era5-bulletin.monthly-1850-1900";
const HUMAN = "warming.igcc-2025.human-induced";
const HUMAN_YEAR = "warming.igcc-2025.human-induced-2025";
const DAILY = "temp.c3s-climate-pulse.daily-1991-2020";
const SST_DAILY = "sst.c3s-climate-pulse.daily-60s-60n-1991-2020";
const SST = "sst.hadsst4.annual-1961-1990";
const JONES = "warming.jones-2025.national-contribution";
const CCKP = "temp.wb-cckp.era5-annual-1991-2020";
const CCKP_ABS = "temp.wb-cckp.era5-annual-absolute";
const HOT_DAYS = "hot-days-35c.wb-cckp.cmip6";

const TOP = 15;
/**
 * A daily series since 1940 is tens of thousands of points, too many for a node file or a readable line, so the daily
 * views show the latest day's calendar year and the RECENT_YEARS full years before it (every published day in them).
 */
const RECENT_YEARS = 3;
const WARM = "#b2182b";
const COOL = "#2166ac";
const GREY = "#9aa0a6";

const SCENARIOS: { id: string; label: string; colour: string }[] = [
  { id: "historical", label: "1995–2014 (modelled past)", colour: GREY },
  { id: "ssp126", label: "2040–2059, low emissions (SSP1-2.6)", colour: "#f4a582" },
  { id: "ssp245", label: "2040–2059, middle (SSP2-4.5)", colour: "#d6604d" },
  { id: "ssp585", label: "2040–2059, very high emissions (SSP5-8.5)", colour: "#67001f" },
];

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

function root(): Built {
  const { short, decimals } = u(HADCRUT);
  return {
    id: "root",
    parent: null,
    crumb: "World",
    kicker: "How much warmer the world is",
    headline: headline(HADCRUT, "WLD"),
    sentence: `above the 1850–1900 average, by the Met Office Hadley Centre and University of East Anglia record, in ${latestPeriod(HADCRUT)}.`,
    chart: line([{ key: "hadcrut", label: "HadCRUT5, above 1850–1900", colour: WARM, points: points(HADCRUT, "WLD"), drill: "agree" }], short, decimals),
    drills: [
      { label: "Do other records agree?", to: "agree" },
      { label: "How much did people cause?", to: "human" },
      { label: "This year, month by month", to: "monthly" },
      { label: "Which countries caused it?", to: "causers" },
      { label: "Where is it warming?", to: "countries" },
    ],
    credit: credit(HADCRUT),
    indicators: [HADCRUT],
  };
}

function agree(): Built {
  const { short, decimals } = u(HADCRUT);
  const s: Series[] = [
    { key: "hadcrut", label: "HadCRUT5 (UK), above 1850–1900", colour: WARM, points: points(HADCRUT, "WLD") },
    { key: "noaa", label: "NOAAGlobalTemp (US), above 1850–1900", colour: "#c75400", points: points(NOAA, "WLD") },
    { key: "gistemp", label: "GISTEMP (NASA), above 1880–1899", colour: COOL, points: points(GISTEMP, "WLD") },
  ];
  return {
    id: "agree",
    parent: "root",
    crumb: "Three records",
    kicker: "Three independent records, one answer",
    headline: headline(GISTEMP, "WLD"),
    sentence: `above 1880–1899 by NASA's record in ${latestPeriod(GISTEMP)}. Each line keeps its own team's baseline.`,
    chart: line(s, short, decimals),
    drills: [
      { label: "The sea surface", to: "sea" },
      { label: "How much did people cause?", to: "human" },
    ],
    credit: credit(HADCRUT, NOAA, GISTEMP),
    indicators: [HADCRUT, NOAA, GISTEMP],
  };
}

function human(): Built {
  const { short, decimals } = u(HUMAN);
  const s: Series[] = [
    { key: "observed", label: "Observed (HadCRUT5)", colour: GREY, points: points(HADCRUT, "WLD") },
    { key: "human", label: "Caused by people (IGCC)", colour: WARM, points: points(HUMAN, "WLD"), drill: "human-year" },
  ];
  return {
    id: "human",
    parent: "root",
    crumb: "Caused by people",
    kicker: "How much of the warming people caused",
    headline: headline(HUMAN, "WLD"),
    sentence: `of warming caused by human activity in ${latestPeriod(HUMAN)}, by the Indicators of Global Climate Change assessment. The grey line is what thermometers measured.`,
    chart: line(s, short, decimals),
    drills: [
      { label: "IGCC's figure for the latest year", to: "human-year" },
      { label: "Which countries caused it?", to: "causers" },
    ],
    credit: credit(HUMAN, HADCRUT),
    indicators: [HUMAN, HADCRUT],
  };
}

function humanYear(): Built {
  const { short, decimals } = u(HUMAN_YEAR);
  const h = headline(HUMAN_YEAR, "WLD");
  return {
    id: "human-year",
    parent: "human",
    crumb: h.period,
    kicker: `Warming people caused in ${h.period}`,
    headline: h,
    sentence:
      "of warming caused by people, by the Indicators of Global Climate Change assessment's own measure for a single year: the trend through that year, which damps natural ups and downs. The line is its estimate of each year's average.",
    chart: line([{ key: "human", label: "Caused by people, each year's average (IGCC)", colour: WARM, points: points(HUMAN, "WLD") }], short, decimals),
    drills: [],
    credit: credit(HUMAN_YEAR, HUMAN),
    indicators: [HUMAN_YEAR, HUMAN],
  };
}

function monthly(): Built {
  const { short, decimals } = u(ERA5);
  return {
    id: "monthly",
    parent: "root",
    crumb: "Month by month",
    kicker: "Every month since 1940",
    headline: headline(ERA5, "WLD"),
    sentence: "above the 1850–1900 average in the latest month, by the Copernicus ERA5 reanalysis.",
    chart: line([{ key: "era5", label: "ERA5, above 1850–1900", colour: WARM, points: points(ERA5, "WLD"), drill: "daily" }], short, decimals),
    drills: [{ label: "Every day", to: "daily" }],
    credit: credit(ERA5),
    indicators: [ERA5],
  };
}

function sea(): Built {
  const { short, decimals } = u(SST);
  return {
    id: "sea",
    parent: "agree",
    crumb: "Sea surface",
    kicker: "The sea surface is warming too",
    headline: headline(SST, "WLD"),
    sentence: `above the 1961–1990 average at the sea surface, by HadSST4, in ${latestPeriod(SST)}.`,
    chart: line([{ key: "sst", label: "HadSST4, above 1961–1990", colour: COOL, points: points(SST, "WLD"), drill: "sea-daily" }], short, decimals),
    drills: [{ label: "Every day", to: "sea-daily" }],
    credit: credit(SST),
    indicators: [SST],
  };
}

/** A daily world series over its recent window (see RECENT_YEARS): every published day from the window's first on. */
function recentDays(id: string): { first: string; points: SeriesPoint[] } {
  const start = `${Number(latestPeriod(id).slice(0, 4)) - RECENT_YEARS}-01-01`;
  const days = indicator(id)
    .observations.flatMap((o) => (o.entity === "WLD" && o.period !== null && o.period >= start ? [o.period] : []))
    .sort();
  if (days.length === 0) throw new Error(`${id}: no days from ${start}`);
  return { first: days[0], points: points(id, "WLD", {}, periodToX({ period: days[0] })) };
}

function daily(): Built {
  const { short, decimals } = u(DAILY);
  const h = headline(DAILY, "WLD");
  const w = recentDays(DAILY);
  return {
    id: "daily",
    parent: "monthly",
    crumb: "Day by day",
    kicker: `Every day since ${w.first.slice(0, 4)}`,
    headline: h,
    sentence: `above the 1991–2020 average for the same day of the year, worldwide on ${formatPeriod(h.period)}, by the Copernicus ERA5 reanalysis. The line shows every day since ${formatPeriod(w.first)}.`,
    chart: line([{ key: "era5-daily", label: "ERA5, daily, above 1991–2020", colour: WARM, points: w.points }], short, decimals),
    drills: [],
    credit: credit(DAILY),
    indicators: [DAILY],
  };
}

function seaDaily(): Built {
  const { short, decimals } = u(SST_DAILY);
  const h = headline(SST_DAILY, "WLD");
  const w = recentDays(SST_DAILY);
  return {
    id: "sea-daily",
    parent: "sea",
    crumb: "Day by day",
    kicker: `The sea surface every day since ${w.first.slice(0, 4)}`,
    headline: h,
    sentence: `above the 1991–2020 average for the same day of the year, over the oceans except the far north and far south on ${formatPeriod(h.period)}, by the Copernicus ERA5 reanalysis. The line shows every day since ${formatPeriod(w.first)}.`,
    chart: line([{ key: "sst-daily", label: "ERA5 sea surface, 60° S–60° N, daily, above 1991–2020", colour: COOL, points: w.points }], short, decimals),
    drills: [],
    credit: credit(SST_DAILY),
    indicators: [SST_DAILY],
  };
}

function jonesTop(): { entity: string; value: number }[] {
  return ranking(JONES, latestPeriod(JONES)).slice(0, TOP);
}

function causers(): Built {
  const { short, decimals } = u(JONES);
  const year = latestPeriod(JONES);
  const ranked = ranking(JONES, year);
  const top = ranked.slice(0, TOP);
  const items: Bar[] = top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: WARM, drill: `causer-${r.entity}` }));
  return {
    id: "causers",
    parent: "root",
    crumb: "Who caused it",
    kicker: "Whose emissions caused the warming",
    headline: headline(JONES, top[0].entity, {}, year),
    sentence: `of warming by ${year} from ${entityName(top[0].entity)}'s carbon dioxide, methane and nitrous oxide since 1851, the largest share. Select a country.`,
    chart: bars(items, short, decimals, year, `The ${top.length} largest of ${ranked.length} countries and territories, by Jones et al.; excludes fluorinated gases.`),
    drills: [],
    credit: credit(JONES),
    indicators: [JONES],
  };
}

function causer(iso: string): Built {
  const { short, decimals } = u(JONES);
  const name = entityName(iso);
  return {
    id: `causer-${iso}`,
    parent: "causers",
    crumb: name,
    kicker: `Warming caused by ${name}`,
    headline: headline(JONES, iso),
    sentence: `of global warming from ${name}'s emissions since 1851, growing year by year.`,
    chart: line([{ key: iso, label: name, colour: WARM, points: points(JONES, iso) }], short, decimals),
    drills: hasCountry(iso) ? [{ label: `How much has ${name} warmed?`, to: `c-${iso}` }] : [],
    credit: credit(JONES),
    indicators: [JONES],
  };
}

function hasCountry(iso: string): boolean {
  return indicator(CCKP).observations.some((o) => o.entity === iso && o.value !== null);
}

function countries(): Built {
  const { short, decimals } = u(CCKP);
  const year = latestPeriod(CCKP);
  const ranked = ranking(CCKP, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "countries",
    parent: "root",
    crumb: "By country",
    kicker: `Where ${year} was furthest above normal`,
    headline: headline(CCKP, top[0].entity, {}, year),
    sentence: `above the 1991–2020 average in ${entityName(top[0].entity)} in ${year}, the most of any country. Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: WARM, drill: `c-${r.entity}` })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, ERA5 via the World Bank Climate Change Knowledge Portal.`,
    ),
    drills: [],
    credit: credit(CCKP),
    indicators: [CCKP],
  };
}

function country(iso: string): Built {
  const { short, decimals } = u(CCKP);
  const name = entityName(iso);
  const drills: Drill[] = [];
  if (hasAbsolute(iso)) drills.push({ label: "In degrees Celsius", to: `t-${iso}` });
  if (hasHotDays(iso)) drills.push({ label: "Hot days ahead", to: `c-${iso}-hot-days` });
  return {
    id: `c-${iso}`,
    parent: "countries",
    crumb: name,
    kicker: `How much ${name} has warmed`,
    headline: headline(CCKP, iso),
    sentence: `above ${name}'s 1991–2020 average in ${latestPeriod(CCKP)}. The grey line is the world on the same measure.`,
    chart: line(
      [
        { key: iso, label: name, colour: WARM, points: points(CCKP, iso), ...(hasAbsolute(iso) ? { drill: `t-${iso}` } : {}) },
        { key: "WLD", label: "World", colour: GREY, points: points(CCKP, "WLD") },
      ],
      short,
      decimals,
    ),
    drills,
    credit: credit(CCKP),
    indicators: [CCKP],
  };
}

function hasAbsolute(iso: string): boolean {
  return indicator(CCKP_ABS).observations.some((o) => o.entity === iso && o.value !== null);
}

function absolute(iso: string): Built {
  const { short, decimals } = u(CCKP_ABS);
  const name = entityName(iso);
  const h = headline(CCKP_ABS, iso);
  return {
    id: `t-${iso}`,
    parent: `c-${iso}`,
    crumb: "In degrees",
    kicker: `Average temperature in ${name}`,
    headline: h,
    sentence: `averaged across ${name} in ${h.period}, by the ERA5 reanalysis via the World Bank Climate Change Knowledge Portal. The grey line is the world on the same measure.`,
    chart: line(
      [
        { key: iso, label: name, colour: WARM, points: points(CCKP_ABS, iso) },
        { key: "WLD", label: "World", colour: GREY, points: points(CCKP_ABS, "WLD") },
      ],
      short,
      decimals,
    ),
    drills: [],
    credit: credit(CCKP_ABS),
    indicators: [CCKP_ABS],
  };
}

function hasHotDays(iso: string): boolean {
  return SCENARIOS.every((s) => indicator(HOT_DAYS).observations.some((o) => o.entity === iso && o.dims.scenario === s.id && o.value !== null));
}

function hotDays(iso: string): Built {
  const ind = indicator(HOT_DAYS);
  const name = entityName(iso);
  const value = (scenario: string) => {
    const o = ind.observations.find((x) => x.entity === iso && x.dims.scenario === scenario && x.value !== null);
    if (!o) throw new Error(`${HOT_DAYS}: no ${scenario} value for ${iso}`);
    return o;
  };
  const period = calendarPeriod(value("ssp245"));
  return {
    id: `c-${iso}-hot-days`,
    parent: `c-${iso}`,
    crumb: "Hot days ahead",
    kicker: `Days above 35 °C in ${name}`,
    headline: headline(HOT_DAYS, iso, { scenario: "ssp245" }, period),
    sentence: "a year in 2040–2059 on a middle emissions path, the median of the climate models. The bars compare the paths.",
    chart: bars(
      SCENARIOS.map((s) => ({ key: s.id, label: s.label, value: value(s.id).value as number, colour: s.colour })),
      ind.unit.short,
      ind.display.decimals,
      period,
      "Modelled (CMIP6 multi-model median) via the World Bank Climate Change Knowledge Portal; not a forecast of any one year.",
    ),
    drills: [],
    credit: credit(HOT_DAYS),
    indicators: [HOT_DAYS],
  };
}

function ids(): string[] {
  const out = ["root", "agree", "human", "human-year", "monthly", "daily", "sea", "sea-daily", "causers", "countries"];
  for (const r of jonesTop()) out.push(`causer-${r.entity}`);
  const linked = new Set([...ranking(CCKP, latestPeriod(CCKP)).slice(0, TOP).map((r) => r.entity), ...jonesTop().map((r) => r.entity).filter(hasCountry)]);
  for (const iso of [...linked].sort()) {
    out.push(`c-${iso}`);
    if (hasAbsolute(iso)) out.push(`t-${iso}`);
    if (hasHotDays(iso)) out.push(`c-${iso}-hot-days`);
  }
  return out;
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "agree") return agree();
  if (id === "human") return human();
  if (id === "human-year") return humanYear();
  if (id === "monthly") return monthly();
  if (id === "daily") return daily();
  if (id === "sea") return sea();
  if (id === "sea-daily") return seaDaily();
  if (id === "causers") return causers();
  if (id === "countries") return countries();
  const cz = id.match(/^causer-([A-Z0-9_]+)$/);
  if (cz) return causer(cz[1]);
  const t = id.match(/^t-([A-Z0-9_]+)$/);
  if (t) return absolute(t[1]);
  const c = id.match(/^c-([A-Z0-9_]+)(-hot-days)?$/);
  if (c) return c[2] ? hotDays(c[1]) : country(c[1]);
  throw new Error(`unknown heat node ${id}`);
}

export const heat = chapter(ids, build);

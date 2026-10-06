import "server-only";

import { indicator } from "@/lib/data";
import { formatPeriod } from "@/lib/format";
import { bars, type Built, chapter, credit, headline, line, periodToX, points } from "@/lib/dash/kit";
import type { Series, SeriesPoint } from "@/lib/dash/types";

/**
 * The seas and ice chapter. Sea level → how fast it rises, and where the water comes from (each ice source) → the ice
 * itself, and glaciers year by year; and the ocean's other changes: the heat it stores (back to the 1950s as five-year
 * averages, and the coral reefs it bleaches), Arctic sea ice (and its lowest day each year, and snow on northern land),
 * and acidity.
 */

const GMSL = "gmsl.aviso.monthly";
const GMSL_RATE = "gmsl.aviso.rate";
const SLR_GRL = "sea-level-contribution.imbie-2026.greenland";
const SLR_ATA = "sea-level-contribution.imbie-2026.antarctica";
const SLR_GLACIERS = "sea-level-contribution.wgms-amce.glaciers-cumulative";
const MASS_GRL = "ice-sheet-mass.imbie-2026.greenland";
const MASS_ATA = "ice-sheet-mass.imbie-2026.antarctica";
const GLACIER_MASS = "glacier-mass.wgms-amce.cumulative";
const GLACIER_YEARLY = "glacier-mass.wgms-amce.annual";
const OHC_700 = "ohc.ncei.yearly-0-700m";
const OHC_2000 = "ohc.ncei.yearly-0-2000m";
const OHC_2000_5Y = "ohc.ncei.pentadal-0-2000m";
const CORAL = "coral.noaa-crw.fourth-event-reef-area";
const SEA_ICE = "sea-ice-extent.nsidc.arctic-september";
const SEA_ICE_OSISAF = "sea-ice-extent.osisaf.arctic-september";
const SEA_ICE_LOW = "sea-ice-extent.nsidc.arctic-minimum-5day";
const SNOW = "snow-cover.rutgers-snow-cdr.nh-monthly";
const PH = "ph.hot-aloha.surface-insitu";
const PCO2 = "pco2.hot-aloha.surface-insitu";

/** The month of the snow record shown: one calendar month from each year, so the seasonal cycle does not hide the trend. */
const SNOW_MONTH = { code: "06", name: "June" };

const SEA = "#2166ac";
const GREENLAND = "#4393c3";
const ANTARCTICA = "#053061";
const GLACIERS = "#7b5ea7";
const HEAT = "#b2182b";
const SNOW_COLOUR = "#5e8fb8";

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

/** The year a period starts: "1999/2026" -> 1999, "2026-06" -> 2026. */
function startYear(period: string): number {
  const y = Number(period.slice(0, 4));
  if (!Number.isInteger(y)) throw new Error(`oceans: ${period} does not start with a year`);
  return y;
}

/**
 * One calendar month from each year of a monthly series (the published monthly values of that month, nothing
 * averaged), oldest first. A month with no value stays in, as a gap.
 */
function monthEachYear(id: string, entity: string, month: string) {
  const rows = indicator(id)
    .observations.filter((o) => o.entity === entity && o.period !== null && o.period.slice(5) === month)
    .sort((a, b) => (a.period as string).localeCompare(b.period as string));
  if (rows.length === 0) throw new Error(`${id}: no ${month} values for ${entity}`);
  const xs = new Set(rows.map((o) => periodToX(o)));
  // Through points(), so the licence check and the axis positions are the kit's own.
  const series: SeriesPoint[] = points(id, entity).filter((p) => xs.has(p[0]));
  return { rows, series };
}

function root(): Built {
  const { short, decimals } = u(GMSL);
  return {
    id: "root",
    parent: null,
    crumb: "Sea level",
    kicker: "How much the sea has risen",
    headline: headline(GMSL, "WLD"),
    sentence: "higher than the 1993 average, measured from space by satellite altimetry (AVISO), in the latest month.",
    chart: line([{ key: "gmsl", label: "Global mean sea level, from 1993", colour: SEA, points: points(GMSL, "WLD"), drill: "sources" }], short, decimals),
    drills: [
      { label: "Where the water comes from", to: "sources" },
      { label: "How fast it is rising", to: "rate" },
      { label: "Heat stored in the ocean", to: "heat" },
      { label: "Arctic sea ice", to: "sea-ice" },
      { label: "Ocean acidity", to: "acidity" },
    ],
    credit: credit(GMSL),
    indicators: [GMSL],
  };
}

function rate(): Built {
  const h = headline(GMSL_RATE, "WLD");
  // AVISO states its rate "from 1999" with no end; the line shows the measured rise over the same stretch.
  const from = startYear(h.period);
  const { short, decimals } = u(GMSL);
  return {
    id: "rate",
    parent: "root",
    crumb: "How fast",
    kicker: "How fast the sea is rising",
    headline: h,
    sentence: `on average since ${from}, as stated by AVISO from satellite measurements of the sea surface. The line is the rise measured over those years.`,
    chart: line([{ key: "gmsl", label: `Global mean sea level, from ${from}`, colour: SEA, points: points(GMSL, "WLD", {}, from) }], short, decimals),
    drills: [{ label: "Where the water comes from", to: "sources" }],
    credit: credit(GMSL_RATE, GMSL),
    indicators: [GMSL_RATE, GMSL],
  };
}

function sources(): Built {
  const { short, decimals } = u(SLR_GRL);
  const s: Series[] = [
    { key: "greenland", label: "Greenland Ice Sheet (from 1971)", colour: GREENLAND, points: points(SLR_GRL, "GRL"), drill: "greenland" },
    { key: "antarctica", label: "Antarctic Ice Sheet (from 1979)", colour: ANTARCTICA, points: points(SLR_ATA, "ATA"), drill: "antarctica" },
    { key: "glaciers", label: "Mountain glaciers (from 1975)", colour: GLACIERS, points: points(SLR_GLACIERS, "WLD"), drill: "glaciers" },
  ];
  return {
    id: "sources",
    parent: "root",
    crumb: "Melting ice",
    kicker: "Melting ice adds to the sea",
    headline: headline(SLR_GRL, "GRL"),
    sentence: "of sea level rise from Greenland's melting ice sheet alone. Warmer water also takes up more room. Select an ice source.",
    chart: line(s, short, decimals),
    drills: [
      { label: "Greenland", to: "greenland" },
      { label: "Antarctica", to: "antarctica" },
      { label: "Glaciers", to: "glaciers" },
    ],
    credit: credit(SLR_GRL, SLR_ATA, SLR_GLACIERS),
    indicators: [SLR_GRL, SLR_ATA, SLR_GLACIERS],
  };
}

function iceSheet(id: "greenland" | "antarctica"): Built {
  const mass = id === "greenland" ? MASS_GRL : MASS_ATA;
  const entity = id === "greenland" ? "GRL" : "ATA";
  const name = id === "greenland" ? "Greenland" : "Antarctica";
  const { short, decimals } = u(mass);
  return {
    id,
    parent: "sources",
    crumb: name,
    kicker: `Ice lost from ${name}`,
    headline: headline(mass, entity),
    sentence: `of ice, the change since the record began (IMBIE). Negative is ice lost to the sea.`,
    chart: line([{ key: id, label: `${name} ice sheet, cumulative change`, colour: id === "greenland" ? GREENLAND : ANTARCTICA, points: points(mass, entity) }], short, decimals),
    drills: [{ label: id === "greenland" ? "Antarctica" : "Greenland", to: id === "greenland" ? "antarctica" : "greenland" }],
    credit: credit(mass),
    indicators: [mass],
  };
}

function glaciers(): Built {
  const { short, decimals } = u(GLACIER_MASS);
  return {
    id: "glaciers",
    parent: "sources",
    crumb: "Glaciers",
    kicker: "Ice lost from the world's glaciers",
    headline: headline(GLACIER_MASS, "WLD"),
    sentence: "of ice since late 1975, from the World Glacier Monitoring Service. Negative is ice lost.",
    chart: line([{ key: "glaciers", label: "Glaciers, cumulative change", colour: GLACIERS, points: points(GLACIER_MASS, "WLD"), drill: "glaciers-yearly" }], short, decimals),
    drills: [{ label: "Year by year", to: "glaciers-yearly" }],
    credit: credit(GLACIER_MASS),
    indicators: [GLACIER_MASS],
  };
}

function glaciersYearly(): Built {
  const { short, decimals } = u(GLACIER_YEARLY);
  const h = headline(GLACIER_YEARLY, "WLD");
  const rows = indicator(GLACIER_YEARLY).observations.filter((o) => o.entity === "WLD" && o.value !== null && o.period !== null);
  // The year with the most ice lost: the most negative published value (ties go to the earlier year).
  const most = [...rows].sort((a, b) => (a.value as number) - (b.value as number) || (a.period as string).localeCompare(b.period as string))[0];
  if (!most || (most.value as number) >= 0) throw new Error("oceans/glaciers-yearly: no year with ice lost, so the sentence no longer holds");
  return {
    id: "glaciers-yearly",
    parent: "glaciers",
    crumb: "Each year",
    kicker: "The world's glaciers, year by year",
    headline: h,
    sentence: `of glacier ice in the glacier year ending in ${h.period}, by the World Glacier Monitoring Service. Negative is ice lost; the most was lost in ${most.period}.`,
    chart: line([{ key: "glaciers-yearly", label: `Glaciers, change each year, from ${firstPeriodStart(GLACIER_YEARLY, "WLD")}`, colour: GLACIERS, points: points(GLACIER_YEARLY, "WLD") }], short, decimals),
    drills: [],
    credit: credit(GLACIER_YEARLY),
    indicators: [GLACIER_YEARLY],
  };
}

function heat(): Built {
  const { short, decimals } = u(OHC_2000);
  return {
    id: "heat",
    parent: "root",
    crumb: "Ocean heat",
    kicker: "Heat piling up in the ocean",
    headline: headline(OHC_2000, "WLD"),
    sentence: "of heat in the top 2,000 metres of ocean, compared with NCEI's long-term average.",
    chart: line(
      [
        { key: "0-700", label: "Top 700 metres (from 1955)", colour: "#d6604d", points: points(OHC_700, "WLD") },
        { key: "0-2000", label: "Top 2,000 metres (from 2005)", colour: HEAT, points: points(OHC_2000, "WLD"), drill: "heat-5y" },
      ],
      short,
      decimals,
    ),
    drills: [
      { label: `Five-year averages from ${firstPeriodStart(OHC_2000_5Y, "WLD")}`, to: "heat-5y" },
      { label: "Coral reefs", to: "coral" },
    ],
    credit: credit(OHC_2000, OHC_700),
    indicators: [OHC_2000, OHC_700],
  };
}

/** The start year of an entity's first published value (for "from …" labels, never typed). */
function firstPeriodStart(id: string, entity: string): number {
  const periods = indicator(id)
    .observations.filter((o) => o.entity === entity && o.value !== null && o.period !== null)
    .map((o) => o.period as string)
    .sort();
  if (periods.length === 0) throw new Error(`${id}: no values for ${entity}`);
  return startYear(periods[0]);
}

function heat5y(): Built {
  const { short, decimals } = u(OHC_2000_5Y);
  const h = headline(OHC_2000_5Y, "WLD");
  const from = firstPeriodStart(OHC_2000_5Y, "WLD");
  return {
    id: "heat-5y",
    parent: "heat",
    crumb: `Since ${from}`,
    kicker: `Ocean heat since ${from}`,
    headline: h,
    sentence: `of heat in the top 2,000 metres of ocean, averaged over ${formatPeriod(h.period)}, compared with NCEI's long-term average. Each point is a five-year average, placed at its middle year.`,
    chart: line([{ key: "0-2000", label: `Top 2,000 metres, five-year averages (from ${from})`, colour: HEAT, points: points(OHC_2000_5Y, "WLD") }], short, decimals),
    drills: [{ label: "Coral reefs", to: "coral" }],
    credit: credit(OHC_2000_5Y),
    indicators: [OHC_2000_5Y],
  };
}

function coral(): Built {
  const ind = indicator(CORAL);
  const h = headline(CORAL, "WLD");
  const [start, end] = h.period.split("/");
  if (!start || !end) throw new Error(`${CORAL}: expected a date range, got ${h.period}`);
  return {
    id: "coral",
    parent: "heat",
    crumb: "Coral reefs",
    kicker: "Coral reefs hit by heat that bleaches coral",
    headline: h,
    sentence: `had heat stress strong enough to bleach coral at least once from ${formatPeriod(start)} to ${formatPeriod(end)}, the fourth global bleaching event, by NOAA Coral Reef Watch.`,
    chart: bars(
      [{ key: "fourth-event", label: "Fourth global bleaching event", value: h.value, colour: HEAT }],
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "NOAA Coral Reef Watch's one figure for the whole event, from satellite sea temperatures. Heat stress is the risk of bleaching, not bleaching seen.",
    ),
    drills: [],
    credit: credit(CORAL),
    indicators: [CORAL],
  };
}

function seaIce(): Built {
  const { short, decimals } = u(SEA_ICE);
  return {
    id: "sea-ice",
    parent: "root",
    crumb: "Arctic sea ice",
    kicker: "Arctic sea ice at its yearly low",
    headline: headline(SEA_ICE, "NH"),
    sentence: "of Arctic Ocean covered by ice in September, by NSIDC's Sea Ice Index. The second line is Europe's independent OSI SAF record.",
    chart: line(
      [
        { key: "nsidc", label: "NSIDC (US)", colour: SEA, points: points(SEA_ICE, "NH"), drill: "sea-ice-low" },
        { key: "osisaf", label: "OSI SAF (Europe)", colour: "#9aa0a6", points: points(SEA_ICE_OSISAF, "NH") },
      ],
      short,
      decimals,
    ),
    drills: [
      { label: "The lowest day each year", to: "sea-ice-low" },
      { label: "Snow on northern land", to: "snow" },
    ],
    credit: credit(SEA_ICE, SEA_ICE_OSISAF),
    indicators: [SEA_ICE, SEA_ICE_OSISAF],
  };
}

function seaIceLow(): Built {
  const { short, decimals } = u(SEA_ICE_LOW);
  const h = headline(SEA_ICE_LOW, "NH");
  // The latest year may not be over yet: its lowest day so far is preliminary, and the sentence says so.
  const year = startYear(h.period);
  const when =
    h.status === "preliminary"
      ? `on ${formatPeriod(h.period)}, the lowest so far in ${year} (preliminary: the year is not over)`
      : `on ${formatPeriod(h.period)}, the lowest of ${year}`;
  return {
    id: "sea-ice-low",
    parent: "sea-ice",
    crumb: "Lowest day",
    kicker: "Arctic sea ice on its lowest day of the year",
    headline: h,
    sentence: `of Arctic Ocean covered by ice ${when}, by NSIDC, as a five-day average. Each point is one year's lowest day.`,
    chart: line([{ key: "nsidc", label: `NSIDC, lowest five-day average each year, from ${firstPeriodStart(SEA_ICE_LOW, "NH")}`, colour: SEA, points: points(SEA_ICE_LOW, "NH") }], short, decimals),
    drills: [{ label: "Snow on northern land", to: "snow" }],
    credit: credit(SEA_ICE_LOW),
    indicators: [SEA_ICE_LOW],
  };
}

function snow(): Built {
  const { short, decimals } = u(SNOW);
  const { rows, series } = monthEachYear(SNOW, "NH", SNOW_MONTH.code);
  const withValue = rows.filter((o) => o.value !== null);
  const latest = withValue.at(-1);
  if (!latest) throw new Error(`${SNOW}: no ${SNOW_MONTH.name} value`);
  const h = headline(SNOW, "NH", {}, latest.period as string);
  const first = startYear(withValue[0].period as string);
  // A month with no snow maps stays a gap in the line, and the sentence names it.
  const gaps = rows.filter((o) => o.value === null).map((o) => startYear(o.period as string));
  const gapNote = gaps.length === 0 ? "" : ` ${SNOW_MONTH.name} ${gaps.join(", ")} ${gaps.length === 1 ? "has" : "have"} no snow maps.`;
  return {
    id: "snow",
    parent: "sea-ice",
    crumb: `Snow in ${SNOW_MONTH.name}`,
    kicker: `Snow on northern land in ${SNOW_MONTH.name}`,
    headline: h,
    sentence: `of Northern Hemisphere land was under snow in ${formatPeriod(h.period)}, on average over the month, by NOAA's snow record made at Rutgers University. Each point is one ${SNOW_MONTH.name}, from ${first}.${gapNote}`,
    chart: line([{ key: "snow", label: `Snow cover in ${SNOW_MONTH.name}, Northern Hemisphere land`, colour: SNOW_COLOUR, points: series }], short, decimals),
    drills: [{ label: "The lowest day of Arctic sea ice", to: "sea-ice-low" }],
    credit: credit(SNOW),
    indicators: [SNOW],
  };
}

function acidity(): Built {
  const { short, decimals } = u(PH);
  return {
    id: "acidity",
    parent: "root",
    crumb: "Acidity",
    kicker: "The ocean is becoming more acidic",
    headline: headline(PH, "ALOHA"),
    sentence: "at the surface of the North Pacific off Hawaii, at the latest Hawaii Ocean Time-series cruise. Lower pH is more acidic.",
    chart: line([{ key: "ph", label: "Seawater pH, Station ALOHA", colour: SEA, points: points(PH, "ALOHA") }], short, decimals),
    drills: [{ label: "Why: carbon dioxide in the water", to: "pco2" }],
    credit: credit(PH),
    indicators: [PH],
  };
}

function pco2(): Built {
  const { short, decimals } = u(PCO2);
  return {
    id: "pco2",
    parent: "acidity",
    crumb: "Carbon dioxide in the water",
    kicker: "The sea absorbs carbon dioxide from the air",
    headline: headline(PCO2, "ALOHA"),
    sentence: "of carbon dioxide in the surface water at Station ALOHA, at the latest cruise. As it rises, pH falls.",
    chart: line([{ key: "pco2", label: "Carbon dioxide in seawater, Station ALOHA", colour: HEAT, points: points(PCO2, "ALOHA") }], short, decimals),
    drills: [],
    credit: credit(PCO2),
    indicators: [PCO2],
  };
}

function ids(): string[] {
  return [
    "root",
    "rate",
    "sources",
    "greenland",
    "antarctica",
    "glaciers",
    "glaciers-yearly",
    "heat",
    "heat-5y",
    "coral",
    "sea-ice",
    "sea-ice-low",
    "snow",
    "acidity",
    "pco2",
  ];
}

function build(id: string): Built {
  switch (id) {
    case "root":
      return root();
    case "rate":
      return rate();
    case "sources":
      return sources();
    case "greenland":
    case "antarctica":
      return iceSheet(id);
    case "glaciers":
      return glaciers();
    case "glaciers-yearly":
      return glaciersYearly();
    case "heat":
      return heat();
    case "heat-5y":
      return heat5y();
    case "coral":
      return coral();
    case "sea-ice":
      return seaIce();
    case "sea-ice-low":
      return seaIceLow();
    case "snow":
      return snow();
    case "acidity":
      return acidity();
    case "pco2":
      return pco2();
    default:
      throw new Error(`unknown oceans node ${id}`);
  }
}

export const oceans = chapter(ids, build);

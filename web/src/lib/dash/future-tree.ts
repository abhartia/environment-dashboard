import "server-only";

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import type { GeoIndex } from "@/gen/hey-api/types.gen";
import { indicator } from "@/lib/data";
import { countryOf, entityKind, entityName, isPlace } from "@/lib/dash/entities";
import type { FutureFrame } from "@/lib/dash/future-select";
import { heat } from "@/lib/dash/heat-tree";
import { bars, type Built, chapter, credit, crossTo, dimLabel, headline, line, observations, periodToX, ranking } from "@/lib/dash/kit";
import { people } from "@/lib/dash/people-tree";
import type { Bar, Drill, FutureCell, FutureMeasure, FuturePath, FuturePayload, FuturePeriod, FuturePlace, Series } from "@/lib/dash/types";

/**
 * The future: what the climate models project for every country and every state or province, as the World Bank's
 * Climate Change Knowledge Portal (CCKP) publishes it (pipeline transform future/cckp_projections.py). It lives on the
 * home page (future mode): the root is the world map, and each country's node is its own map of regions. A node
 * carries every value a reader can choose between (each measure, 20-year window and emissions path, with the model
 * range), so moving the dial or the path never fetches; the browser only selects (lib/dash/future-select.ts).
 *
 * Values are CCKP's area averages: "averaged over the land of" the place, not weighted by where people live.
 */

/**
 * The measures, in the order of the cards. The kicker is ours, in plain words; every threshold it names ("35 °C or
 * more") must be in the published unit label, and `qualifier` (what the threshold is of) too, so a change of
 * definition upstream fails the build rather than mislabel the map.
 */
const MEASURES: { key: string; kicker: string | null; qualifier?: string; ramp: FutureMeasure["ramp"] }[] = [
  { key: "hot-days-35c", kicker: "Days at 35 °C or more", qualifier: "daily maximum temperature", ramp: "warm" },
  { key: "hot-nights-26c", kicker: "Nights that stay at 26 °C or more", qualifier: "daily minimum temperature", ramp: "warm" },
  { key: "heat-index-39c-days", kicker: "Days that feel like 39 °C or more", qualifier: "heat index of 39 °C or more", ramp: "warm" },
  { key: "hottest-day", kicker: "The hottest day of the year", ramp: "warm" },
  { key: "longest-dry-spell", kicker: "The longest dry spell of the year", ramp: "dry" },
  // Warming is itself a change from the baseline window, so its kicker names that window, as the data states it.
  { key: "warming", kicker: null, ramp: "warm" },
];

/** The view a reader lands on (the owner's choice of 2026-10-16): the middle path in the window centred on 2050. */
const DEFAULT_MEASURE = "hot-days-35c";
const DEFAULT_PERIOD = "2040/2059";
const DEFAULT_PATH = "ssp245";

/** The model simulation of the past every window is compared with. */
const BASELINE_SCENARIO = "historical";

/** Which curve shape stands for each of CCKP's scenarios. A scenario not listed stops the build. */
const TIERS: Record<string, FuturePath["tier"]> = { ssp126: "low", ssp245: "middle", ssp585: "very-high" };

const GEO_SOURCE = "wb-gad-v1";
const WARM = "#b2182b";
const PATH_COLOURS: Record<FuturePath["tier"], string> = { low: "#f4a582", middle: "#d6604d", "very-high": "#67001f" };
const GREY = "#9aa0a6";
const TOP = 15;

const countriesId = (key: string) => `future.wb-cckp.${key}-countries`;
const regionsId = (key: string) => `future.wb-cckp.${key}-regions`;

const GEO = path.join(process.cwd(), ".generated", "v1", "geo");

function readGeo<T>(rel: string): T {
  return JSON.parse(readFileSync(path.join(GEO, rel), "utf8")) as T;
}

let geoIndexCache: GeoIndex | null = null;
function geoIndex(): GeoIndex {
  geoIndexCache ??= readGeo<GeoIndex>("index.json");
  return geoIndexCache;
}

let worldIdsCache: Set<string> | null = null;
/** The entities the world map has a feature for (a shape, or a point where a place is too small to draw). */
function worldIds(): Set<string> {
  if (worldIdsCache) return worldIdsCache;
  const topo = readGeo<{ objects: { countries: { geometries: { id: string }[] } } }>("world.topo.json");
  worldIdsCache = new Set(topo.objects.countries.geometries.map((g) => g.id));
  return worldIdsCache;
}

/** One indicator's cells, indexed once: entity -> "<period>|<scenario>" -> [median, 10th, 90th percentile]. */
type Cells = Map<string, Map<string, FutureCell>>;
const cellsCache = new Map<string, Cells>();

function cells(id: string): Cells {
  const hit = cellsCache.get(id);
  if (hit) return hit;
  const out: Cells = new Map();
  for (const o of observations(id)) {
    const scenario = o.dims.scenario;
    if (!scenario) throw new Error(`${id}: an observation without a scenario`);
    if (o.period === null) throw new Error(`${id}: an observation without a window`);
    if (o.value === null) throw new Error(`${id}: ${o.entity} ${o.period} ${scenario} has no value`);
    // A window's status must say what it is: the historical runs are a simulation of the past, the rest projections.
    const status = scenario === BASELINE_SCENARIO ? "final" : "projection";
    if (o.status !== status) throw new Error(`${id}: ${o.entity} ${o.period} ${scenario} is ${o.status}, not ${status}`);
    let row = out.get(o.entity);
    if (!row) out.set(o.entity, (row = new Map()));
    row.set(`${o.period}|${scenario}`, [o.value, o.lower, o.upper]);
  }
  cellsCache.set(id, out);
  return out;
}

function window(p: string): { from: number; to: number } {
  const m = p.match(/^(\d{4})\/(\d{4})$/);
  if (!m) throw new Error(`future: ${p} is not a window of years`);
  const from = Number(m[1]);
  const to = Number(m[2]);
  // CCKP's climatologies are 20-year averages; anything else is not what the dial and the chart say.
  if (to - from !== 19) throw new Error(`future: ${p} is not a 20-year window`);
  return { from, to };
}

type Frame = {
  periods: FuturePeriod[];
  paths: FuturePath[];
  baseline: FuturePayload["baseline"];
  statistics: FuturePayload["statistics"];
  measures: FutureMeasure[];
};

/** The sentence every projection indicator's description uses to say which statistics of the models it publishes. */
const STATISTICS = /The value is the (median) of the models and the range runs from the (\d+th) to the (\d+th) percentile of the models\./;

let frameCache: Frame | null = null;

/** What the data offers: its windows, paths and measures, each checked against what the screens say about it. */
function frame(): Frame {
  if (frameCache) return frameCache;
  const first = countriesId(MEASURES[0].key);
  const scenarioDim = indicator(first).dimensions.find((d) => d.id === "scenario");
  if (!scenarioDim) throw new Error(`${first}: no scenario dimension`);
  const paths = scenarioDim.values
    .filter((v) => v.id !== BASELINE_SCENARIO)
    .map((v): FuturePath => {
      const tier = TIERS[v.id];
      if (!tier) throw new Error(`${first}: scenario ${v.id} has no curve shape on the path picker`);
      return { id: v.id, tier, label: v.label };
    });
  const windows = new Set<string>();
  const baselines = new Set<string>();
  for (const o of observations(first)) (o.dims.scenario === BASELINE_SCENARIO ? baselines : windows).add(o.period as string);
  if (baselines.size !== 1) throw new Error(`${first}: ${baselines.size} baseline windows, not one`);
  const basePeriod = [...baselines][0];
  window(basePeriod);
  const periods = [...windows].sort().map((p): FuturePeriod => ({ id: p.replace("/", "-"), period: p, ...window(p) }));

  const measures = MEASURES.map((m): FutureMeasure => {
    const c = indicator(countriesId(m.key));
    const r = indicator(regionsId(m.key));
    if (c.unit.label !== r.unit.label || c.unit.short !== r.unit.short) throw new Error(`${m.key}: countries and regions differ in unit`);
    for (const t of [...(m.kicker?.match(/\d+ °C or more/g) ?? []), ...(m.qualifier ? [m.qualifier] : [])]) {
      if (!c.unit.label.includes(t)) throw new Error(`${c.id}: the kicker "${m.kicker}" says ${t}, but the unit is "${c.unit.label}"`);
    }
    // The colour scale's ends: the smallest and largest published median over every place, window and path, so a colour
    // means the same on every map and in every window. Chosen, not computed.
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const id of [c.id, r.id]) {
      for (const row of cells(id).values()) {
        for (const [k, cell] of row) {
          if (k.endsWith(`|${BASELINE_SCENARIO}`) || !cell) continue;
          if (cell[0] < min) min = cell[0];
          if (cell[0] > max) max = cell[0];
        }
      }
    }
    // Counts of days start at none; a temperature has no natural zero on this map.
    const spread = c.unit.code === "days" ? "sqrt" : c.unit.code === "degC" ? "linear" : null;
    if (spread === null) throw new Error(`${c.id}: no colour spread for unit ${c.unit.code}`);
    if (spread === "sqrt" && min < 0) throw new Error(`${c.id}: a negative count`);
    // "Warmer than 1995–2014" holds only while no place's median is a cooling.
    if (m.kicker === null && min <= 0) throw new Error(`${c.id}: a median of ${min}, so "warmer than" is not true everywhere`);
    const hasBaseline = [...cells(c.id).values()].some((row) => row.has(`${basePeriod}|${BASELINE_SCENARIO}`));
    const span = basePeriod.replace("/", "–");
    if (m.kicker === null && !(c.scope.baseline ?? "").startsWith(`${span} mean`)) throw new Error(`${c.id}: its baseline "${c.scope.baseline}" is not the ${span} model mean`);
    return {
      key: m.key,
      countries: c.id,
      regions: r.id,
      kicker: m.kicker ?? `Warmer than ${span}`,
      unit: c.unit.short,
      unitLabel: c.unit.label,
      decimals: c.display.decimals,
      ramp: m.ramp,
      spread,
      min: spread === "sqrt" ? 0 : min,
      max,
      baseline: hasBaseline,
    };
  });
  // Which statistics of the models the values are, read from the indicators' own descriptions (the same in all).
  const said = new Set(MEASURES.flatMap((m) => [countriesId(m.key), regionsId(m.key)]).map((id) => indicator(id).description.match(STATISTICS)?.slice(1).join("|") ?? null));
  const only = [...said][0];
  if (said.size !== 1 || only === null) throw new Error(`future: the indicators do not all say the median and range of the models the same way`);
  const [value, lower, upper] = only.split("|");

  if (!periods.some((p) => p.period === DEFAULT_PERIOD)) throw new Error(`future: the default window ${DEFAULT_PERIOD} is not published`);
  if (!paths.some((p) => p.id === DEFAULT_PATH)) throw new Error(`future: the default path ${DEFAULT_PATH} is not published`);
  frameCache = {
    periods,
    paths,
    baseline: { period: basePeriod, scenario: BASELINE_SCENARIO, label: dimLabel(first, "scenario", BASELINE_SCENARIO) },
    statistics: { value, lower, upper },
    measures,
  };
  return frameCache;
}

/** The home page's choices (windows, paths, measures and the landing view), for the header's dial and picker. */
export function futureFrame(): FutureFrame {
  const f = frame();
  return {
    periods: f.periods,
    paths: f.paths,
    measures: f.measures.map((m) => ({ key: m.key, kicker: m.kicker })),
    defaults: { period: DEFAULT_PERIOD, path: DEFAULT_PATH, measure: DEFAULT_MEASURE },
  };
}

function values(f: Frame, places: FuturePlace[]): FuturePayload["values"] {
  const slices = [`${f.baseline.period}|${f.baseline.scenario}`, ...f.periods.flatMap((p) => f.paths.map((s) => `${p.period}|${s.id}`))];
  const out: FuturePayload["values"] = {};
  for (const m of f.measures) {
    const byCountry = cells(m.countries);
    const byRegion = cells(m.regions);
    out[m.key] = {};
    for (const slice of slices) {
      const row = places.map((p) => (p.kind === "region" ? byRegion : byCountry).get(p.entity)?.get(slice) ?? null);
      if (row.some((c) => c !== null)) out[m.key][slice] = row;
    }
  }
  return out;
}

function geoCredit(): FuturePayload["geoCredit"] {
  const g = geoIndex();
  const origin = g.origins.find((o) => o.source_id === GEO_SOURCE);
  if (!origin) throw new Error(`data/v1/geo/index.json: no origin from ${GEO_SOURCE}`);
  return { source: GEO_SOURCE, producers: origin.producer, licence: g.licence.name, attribution: g.attribution };
}

/** Countries and territories with values, by code. */
function countryCodes(): string[] {
  return [...cells(countriesId(DEFAULT_MEASURE)).keys()].filter(isPlace).sort();
}

function countryPlace(iso: string): FuturePlace {
  const kind = entityKind(iso);
  if (kind !== "country" && kind !== "territory") throw new Error(`future: ${iso} is a ${kind}, not a country or territory`);
  return { entity: iso, name: entityName(iso), kind, onMap: worldIds().has(iso) };
}

let regionsCache: Map<string, string[]> | null = null;
/** Each country's CCKP regions with values, by code. */
function regionsByCountry(): Map<string, string[]> {
  if (regionsCache) return regionsCache;
  const out = new Map<string, string[]>();
  for (const code of cells(regionsId(DEFAULT_MEASURE)).keys()) {
    const iso = countryOf(code);
    out.set(iso, [...(out.get(iso) ?? []), code]);
  }
  for (const list of out.values()) list.sort();
  regionsCache = out;
  return out;
}

/** The scenario's label as the data names it ("SSP2-4.5, middle emissions"). */
function pathLabel(f: Frame, id: string): string {
  return f.paths.find((p) => p.id === id)!.label;
}

/** One place, one measure, every window: the baseline, then each path's windows, as a line per path. */
function windowsChart(f: Frame, m: FutureMeasure, id: string, entity: string) {
  const row = cells(id).get(entity);
  const base = row?.get(`${f.baseline.period}|${f.baseline.scenario}`)?.[0] ?? null;
  const series: Series[] = f.paths.map((s) => ({
    key: s.id,
    label: s.label,
    colour: PATH_COLOURS[s.tier],
    points: [
      ...(base !== null ? [[periodToX({ period: f.baseline.period }), base] as [number, number]] : []),
      ...f.periods.map((p) => [periodToX({ period: p.period }), row?.get(`${p.period}|${s.id}`)?.[0] ?? null] as [number, number | null]),
    ],
  }));
  if (base !== null) series.unshift({ key: "baseline", label: f.baseline.label, colour: GREY, points: [[periodToX({ period: f.baseline.period }), base]] });
  return line(series, m.unit, m.decimals);
}

function root(): Built {
  const f = frame();
  const m = f.measures.find((x) => x.key === DEFAULT_MEASURE)!;
  const places = countryCodes().map(countryPlace);
  const dims = { scenario: DEFAULT_PATH };
  const top = ranking(m.countries, DEFAULT_PERIOD, dims).filter((r) => entityKind(r.entity) === "country");
  if (top.length === 0) throw new Error(`${m.countries}: no country ranked in ${DEFAULT_PERIOD}`);
  const most = top[1]?.value === top[0].value ? "tied for the most of any country" : "the most of any country";
  const items: Bar[] = top.slice(0, TOP).map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: WARM, drill: `c-${r.entity}` }));
  const indicators = f.measures.map((x) => x.countries);
  const w = window(DEFAULT_PERIOD);
  return {
    id: "root",
    parent: null,
    crumb: "World",
    kicker: m.kicker,
    headline: headline(m.countries, top[0].entity, dims, DEFAULT_PERIOD),
    sentence: `in ${entityName(top[0].entity)}, ${most}, ${w.from}–${w.to}, ${pathLabel(f, DEFAULT_PATH)}, projected.`,
    chart: bars(items, m.unit, m.decimals, DEFAULT_PERIOD, `${w.from}–${w.to}, ${pathLabel(f, DEFAULT_PATH)}, averaged over each country's land.`),
    drills: [],
    credit: credit(...indicators),
    indicators,
    future: {
      level: "world",
      place: null,
      periods: f.periods,
      paths: f.paths,
      measures: f.measures,
      baseline: f.baseline,
      statistics: f.statistics,
      places,
      values: values(f, places),
      geo: "v1/geo/world.topo.json",
      unmatched: [],
      geoCredit: geoCredit(),
    },
  };
}

let peopleIds: Set<string> | null = null;
let heatIds: Set<string> | null = null;

/** The other chapters' views of this country, each only where that chapter has one. */
function elsewhere(iso: string): Drill[] {
  peopleIds ??= new Set(people.ids());
  heatIds ??= new Set(heat.ids());
  const out: Drill[] = [];
  // The panel is about this country already, so the labels leave its name out.
  if (peopleIds.has(`hw-${iso}`)) out.push(crossTo("Heatwave days caused by the warming", `people:hw-${iso}`));
  if (peopleIds.has(`coast-${iso}`)) out.push(crossTo("People below high tide", `people:coast-${iso}`));
  if (heatIds.has(`c-${iso}`)) out.push(crossTo("How much it has warmed so far", `heat:c-${iso}`));
  return out;
}

function country(iso: string): Built {
  const f = frame();
  const m = f.measures.find((x) => x.key === DEFAULT_MEASURE)!;
  const self = countryPlace(iso);
  const g = geoIndex().countries.find((c) => c.entity === iso);
  // A country with one region has nothing more to show at that level: its region is the whole country.
  const codes = regionsByCountry().get(iso) ?? [];
  const regions = codes.length > 1 ? codes : [];
  const file = regions.length && g?.file ? g.file : null;
  if (file && !existsSync(path.join(process.cwd(), ".generated", file))) throw new Error(`future: ${iso}'s map ${file} is not published`);
  const notDrawn = new Set([...(g?.unjoined ?? []), ...(g?.shapeless ?? [])]);
  const places: FuturePlace[] = [
    self,
    ...regions.map((code): FuturePlace => ({ entity: code, name: entityName(code), kind: "region", onMap: file !== null && !notDrawn.has(code) })),
  ];
  const indicators = f.measures.flatMap((x) => (regions.length ? [x.countries, x.regions] : [x.countries]));
  const w = window(DEFAULT_PERIOD);
  return {
    id: `c-${iso}`,
    parent: "root",
    crumb: self.name,
    kicker: m.kicker,
    headline: headline(m.countries, iso, { scenario: DEFAULT_PATH }, DEFAULT_PERIOD),
    sentence: `averaged over the land of ${self.name}, ${w.from}–${w.to}, ${pathLabel(f, DEFAULT_PATH)}, projected.`,
    chart: windowsChart(f, m, m.countries, iso),
    drills: elsewhere(iso),
    credit: credit(...indicators),
    indicators,
    future: {
      level: "country",
      place: iso,
      periods: f.periods,
      paths: f.paths,
      measures: f.measures,
      baseline: f.baseline,
      statistics: f.statistics,
      places,
      values: values(f, places),
      geo: file,
      unmatched: places.filter((p) => p.kind === "region" && !p.onMap).map((p) => p.entity),
      geoCredit: geoCredit(),
    },
  };
}

/**
 * Every place the future map opens on, for the search: each country and territory, and each state or province of a
 * country with more than one (its name with its country's, "Delhi, India"). Regions CCKP gives no name are left out.
 */
export function futurePlaces(): { title: string; detail: string; href: string }[] {
  const out: { title: string; detail: string; href: string }[] = [];
  const regions = regionsByCountry();
  for (const iso of countryCodes()) {
    const name = entityName(iso);
    out.push({ title: name, detail: "Its future, projected", href: `/?mode=future&c=${iso}` });
    const codes = regions.get(iso) ?? [];
    if (codes.length < 2) continue;
    for (const code of codes) {
      const r = entityName(code);
      if (r.startsWith("Unnamed region of ")) continue;
      out.push({ title: `${r}, ${name}`, detail: "Its future, projected", href: `/?mode=future&c=${iso}&r=${code}` });
    }
  }
  return out;
}

function ids(): string[] {
  return ["root", ...countryCodes().map((iso) => `c-${iso}`)];
}

function build(id: string): Built {
  if (id === "root") return root();
  const c = id.match(/^c-([A-Z0-9_]+)$/);
  if (c) return country(c[1]);
  throw new Error(`unknown future node ${id}`);
}

export const future = chapter(ids, build);

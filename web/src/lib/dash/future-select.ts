import type { FutureCell, FutureMeasure, FuturePayload, FuturePlace, Headline } from "@/lib/dash/types";

/**
 * Future mode reads published values; it never computes one. These helpers only choose: which cell of a node's payload
 * belongs to the reader's measure, place, window and path, and the traced headline for it (the indicator and entity it
 * came from, so the number opens its source). Pure, so they run in the browser and in tests alike.
 */

/** The key of a slice in a payload: "<period>|<scenario>", e.g. "2040/2059|ssp245". */
export function sliceKey(period: string, scenario: string): string {
  return `${period}|${scenario}`;
}

export function measureOf(payload: FuturePayload, key: string): FutureMeasure {
  const m = payload.measures.find((x) => x.key === key);
  if (!m) throw new Error(`future: no measure ${key}`);
  return m;
}

export function placeIndex(payload: FuturePayload, entity: string): number {
  return payload.places.findIndex((p) => p.entity === entity);
}

/** The published cell for one place, or null where the source has none (or the slice is not published). */
export function cellOf(payload: FuturePayload, measure: string, entity: string, period: string, scenario: string): FutureCell {
  const i = placeIndex(payload, entity);
  if (i < 0) return null;
  return payload.values[measure]?.[sliceKey(period, scenario)]?.[i] ?? null;
}

/** The indicator a place's value is published in: regions have their own file, countries and territories theirs. */
export function indicatorFor(measure: FutureMeasure, place: FuturePlace): string {
  return place.kind === "region" ? measure.regions : measure.countries;
}

/**
 * A traced headline for one cell: everything the Trace panel needs, including which path and which statistic of the
 * models it is. `which` picks the median or one end of the model range; a missing end gives null, never a substitute.
 */
export function headlineFor(
  payload: FuturePayload,
  measure: FutureMeasure,
  place: FuturePlace,
  period: string,
  scenario: string,
  which: "value" | "lower" | "upper" = "value",
): Headline | null {
  const cell = cellOf(payload, measure.key, place.entity, period, scenario);
  if (!cell) return null;
  const v = which === "value" ? cell[0] : which === "lower" ? cell[1] : cell[2];
  if (v === null) return null;
  return {
    indicator: indicatorFor(measure, place),
    entity: place.entity,
    period,
    value: v,
    decimals: measure.decimals,
    unit: measure.unit,
    unitLabel: measure.unitLabel,
    status: scenario === payload.baseline.scenario ? "final" : "projection",
    dims: { scenario },
    sliceLabel: `${scenario === payload.baseline.scenario ? payload.baseline.label : payload.paths.find((p) => p.id === scenario)?.label}, ${which === "value" ? payload.statistics.value : `${payload.statistics[which]} percentile`} of the climate models`,
  };
}

/** The reader's choices, read from the home's URL and checked against what the data offers. */
export type FutureState = { mode: "past" | "future" | null; period: string; path: string; measure: string; country: string | null; region: string | null };

export type FutureFrame = {
  periods: { id: string; period: string; from: number; to: number }[];
  paths: { id: string; tier: "low" | "middle" | "very-high"; label: string }[];
  measures: { key: string; kicker: string }[];
  defaults: { period: string; path: string; measure: string };
};

/**
 * Read ?mode=&p=&s=&m=&c=&r= from a query string. An unknown window, path or measure falls back to the default (a
 * stale or mistyped link still opens the map); a place is kept as given and the map says when it has no such place.
 */
export function parseFuture(search: string, frame: FutureFrame): FutureState {
  const q = new URLSearchParams(search);
  const mode = q.get("mode");
  const p = q.get("p");
  const s = q.get("s");
  const m = q.get("m");
  return {
    mode: mode === "future" || mode === "past" ? mode : null,
    period: frame.periods.find((x) => x.id === p)?.period ?? frame.defaults.period,
    path: frame.paths.find((x) => x.id === s)?.id ?? frame.defaults.path,
    measure: frame.measures.find((x) => x.key === m)?.key ?? frame.defaults.measure,
    country: q.get("c"),
    region: q.get("r"),
  };
}

/** The URL id of a window ("2040/2059" -> "2040-2059"). */
export function periodId(period: string): string {
  return period.replace("/", "-");
}

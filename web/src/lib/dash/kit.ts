import "server-only";

import type { Observation } from "@/gen/hey-api/types.gen";
import { catalogEntry, indicator } from "@/lib/data";
import { isPlace } from "@/lib/dash/entities";
import type { Bar, Chart, Credit, DrillNode, Headline, Preview, Series, SeriesPoint } from "@/lib/dash/types";

/**
 * Building blocks for a chapter's drill-down tree (lib/dash/<chapter>-tree.ts). They only select, order and label
 * published observations; none of them computes a value. A missing value stays missing (null), never filled.
 */

export type Dims = Record<string, string>;

/** A node before its breadcrumb trail is attached (the chapter attaches it from the parent chain). */
export type Built = Omit<DrillNode, "trail">;

/**
 * Dashboard nodes are published as JSON files anyone can download, so they may only carry values whose licence allows
 * redistribution. No-derivatives and display-only values stay on server-rendered pages.
 */
const PUBLISHABLE = new Set(["open", "share-alike", "noncommercial"]);

function publishable(id: string): void {
  const cls = catalogEntry(id).licence_class;
  if (!PUBLISHABLE.has(cls)) throw new Error(`${id} is ${cls}: its values cannot go into a dashboard data file`);
}

export function matches(o: Observation, entity: string, dims: Dims = {}): boolean {
  return o.entity === entity && Object.entries(dims).every(([k, v]) => o.dims[k] === v);
}

/**
 * A period as a position on a time axis: "2024" -> 2024, "2026-08" -> 2026.625 (mid-month), "2024-12-20" -> the
 * middle of that day, and a years-before-1950 age as its calendar year (1950 - age). Ranges are not drawn on these
 * charts and throw.
 */
export function periodToX(o: { period: string | null; age_bp?: number | null }): number {
  if (o.period === null) {
    if (o.age_bp === null || o.age_bp === undefined) throw new Error("observation has neither a period nor an age");
    return 1950 - o.age_bp;
  }
  const m = o.period.match(/^(-?\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/);
  if (!m) throw new Error(`periodToX: ${o.period} is not a year, month or day`);
  const year = Number(m[1]);
  if (m[3]) {
    const start = Date.UTC(year, 0, 1);
    const day = (Date.UTC(year, Number(m[2]) - 1, Number(m[3])) - start) / 86_400_000;
    return year + (day + 0.5) / ((Date.UTC(year + 1, 0, 1) - start) / 86_400_000);
  }
  return m[2] ? year + (Number(m[2]) - 0.5) / 12 : year;
}

/** One entity's series (optionally one slice of its dimensions) as chart points, from `from` (axis position) on. */
export function points(id: string, entity: string, dims: Dims = {}, from = Number.NEGATIVE_INFINITY): SeriesPoint[] {
  publishable(id);
  return indicator(id)
    .observations.filter((o) => matches(o, entity, dims))
    .map((o) => [periodToX(o), o.value] as SeriesPoint)
    .filter((p) => p[0] >= from)
    .sort((a, b) => a[0] - b[0]);
}

/** The traced headline: the value for `period`, or the entity's latest non-null value. */
export function headline(id: string, entity: string, dims: Dims = {}, period?: string): Headline {
  publishable(id);
  const ind = indicator(id);
  const rows = ind.observations.filter((o) => matches(o, entity, dims) && o.value !== null);
  // A value dated by age (an ice-core record) has no calendar period; it can be a headline only when it is the one value.
  const o = period === undefined ? (rows.length === 1 ? rows[0] : rows.filter((r) => r.period !== null).at(-1)) : rows.find((r) => r.period === period);
  if (!o || o.value === null) throw new Error(`${id}: no value for ${entity} ${JSON.stringify(dims)} ${period ?? "latest"}`);
  return {
    indicator: id,
    entity,
    period: o.period ?? "",
    value: o.value,
    // Reading precision: thousands need no decimals ("15,805 million tonnes"). Never more than published.
    decimals: Math.abs(o.value) >= 1000 ? 0 : ind.display.decimals,
    unit: ind.unit.short,
    unitLabel: ind.unit.label,
    status: o.status,
  };
}

/** The producer's label for one value of a dimension, as published in the indicator (never our own wording). */
export function dimLabel(id: string, dim: string, value: string): string {
  const d = indicator(id).dimensions.find((x) => x.id === dim);
  const v = d?.values.find((x) => x.id === value);
  if (!v) throw new Error(`${id}: no label for ${dim}=${value}`);
  return v.label;
}

/** The credit for each indicator shown: producers and licence in short, the full attribution on its data page. */
export function credit(...ids: string[]): Credit[] {
  return [...new Set(ids)].map((id) => {
    const entry = catalogEntry(id);
    const producers = [...new Set(entry.provenance.origins.map((o) => o.producer))].join(", ");
    return { indicator: id, producers, licence: entry.provenance.licence.name, attribution: entry.provenance.attribution };
  });
}

/** The indicator's latest period (its headline entity's last non-null value). */
export function latestPeriod(id: string): string {
  const p = indicator(id).latest.period;
  if (!p) throw new Error(`${id}: no calendar latest period`);
  return p;
}

/** Countries and territories (never aggregates) ranked by their value in `period`, largest first, ties by code. */
export function ranking(id: string, period: string, dims: Dims = {}): { entity: string; value: number }[] {
  publishable(id);
  return indicator(id)
    .observations.filter((o) => o.period === period && o.value !== null && isPlace(o.entity) && Object.entries(dims).every(([k, v]) => o.dims[k] === v))
    .map((o) => ({ entity: o.entity, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.entity.localeCompare(b.entity));
}

/** Entities with at least one non-null value (optionally in one dimension slice). */
export function entitiesWithData(id: string, dims: Dims = {}): string[] {
  const set = new Set<string>();
  for (const o of indicator(id).observations) if (o.value !== null && Object.entries(dims).every(([k, v]) => o.dims[k] === v)) set.add(o.entity);
  return [...set].sort();
}

function span(series: Series[]): { from: number; to: number } {
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  return { from: Math.min(...xs), to: Math.max(...xs) };
}

/**
 * An area chart. A stacked chart orders its bands by the first year each has data, oldest at the bottom: a band with
 * no data in a year (the producer starts it later) then has nothing stacked on it, so no gap is ever filled in.
 */
export function area(series: Series[], unit: string, decimals: number, stacked: boolean): Chart {
  const first = (s: Series) => s.points.find((p) => p[1] !== null)?.[0] ?? Number.POSITIVE_INFINITY;
  const ordered = stacked ? [...series].sort((a, b) => first(a) - first(b)) : series;
  return { kind: "area", stacked, series: ordered, unit, decimals, ...span(series) };
}

export function line(series: Series[], unit: string, decimals: number): Chart {
  return { kind: "line", series, unit, decimals, ...span(series) };
}

export function bars(items: Bar[], unit: string, decimals: number, period: string, note: string, legend?: { label: string; colour: string }[]): Chart {
  return { kind: "bars", bars: items, unit, decimals, period, note, ...(legend ? { legend } : {}) };
}

const PREVIEW_POINTS = 60;
const PREVIEW_BARS = 6;

/**
 * A thumbnail of a chart: every k-th point (and always the last) so a line keeps its shape in a few dozen points, or
 * the first few bars of a ranking. Decorative only; the node itself carries every value.
 */
export function preview(chart: Chart): Preview {
  if (chart.kind === "bars") return { kind: "bars", bars: chart.bars.slice(0, PREVIEW_BARS).map((b) => ({ key: b.key, value: b.value, colour: b.colour })) };
  const thin = (pts: SeriesPoint[]) => {
    const k = Math.max(1, Math.ceil(pts.length / PREVIEW_POINTS));
    return pts.filter((_, i) => i % k === 0 || i === pts.length - 1);
  };
  return {
    kind: "lines",
    stacked: chart.kind === "area" && chart.stacked,
    series: chart.series.map((s) => ({ colour: s.colour, points: thin(s.points) })),
  };
}

/**
 * A chapter: its node ids (for the static files) and a node builder that attaches the breadcrumb trail by walking
 * the parent chain, so a deep link shows where it sits, and gives each choice the idea and the chart shape it leads to.
 */
export function chapter(ids: () => string[], build: (id: string) => Built): { ids: () => string[]; node: (id: string) => DrillNode } {
  return {
    ids,
    node(id) {
      const node = build(id);
      const trail: { id: string; crumb: string }[] = [];
      for (let p = node.parent; p !== null; ) {
        const parent = build(p);
        trail.unshift({ id: parent.id, crumb: parent.crumb });
        p = parent.parent;
      }
      const drills = node.drills.map((d) => {
        const next = build(d.to);
        return { ...d, crumb: next.crumb, kicker: next.kicker, preview: preview(next.chart) };
      });
      return { ...node, drills, trail };
    },
  };
}

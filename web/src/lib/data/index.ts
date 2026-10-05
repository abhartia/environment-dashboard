import "server-only";

import { readFileSync } from "node:fs";
import path from "node:path";

import type {
  Catalog,
  CatalogEntry,
  Indicator,
  Observation,
  Source,
  SourceList,
  Status,
} from "@/gen/hey-api/types.gen";

/**
 * The one data door (pattern from gigabiome's lib/demo/data.ts). Pages read published numbers only through these
 * functions, at build time, from web/.generated (copied there by scripts/sync-data.mjs from data/ and
 * data-private/). Unknown ids throw, so a typo fails the build instead of rendering nothing.
 */

const ROOT = path.join(process.cwd(), ".generated", "v1");

function readJson<T>(rel: string): T {
  return JSON.parse(readFileSync(path.join(ROOT, rel), "utf8")) as T;
}

let catalogCache: Catalog | null = null;
let sourcesCache: Map<string, Source> | null = null;
const indicatorCache = new Map<string, Indicator>();

export function catalog(): Catalog {
  catalogCache ??= readJson<Catalog>("catalog.json");
  return catalogCache;
}

export function catalogEntry(id: string): CatalogEntry {
  const entry = catalog().indicators.find((e) => e.id === id);
  if (!entry) throw new Error(`Unknown indicator "${id}": it is not in data/v1/catalog.json`);
  return entry;
}

/** The full indicator, public or private. Private values may only be rendered on the server, never passed to a client component. */
export function indicator(id: string): Indicator {
  const cached = indicatorCache.get(id);
  if (cached) return cached;
  catalogEntry(id);
  const ind = readJson<Indicator>(`indicators/${id}.json`);
  indicatorCache.set(id, ind);
  return ind;
}

export function sources(): Source[] {
  sourcesCache ??= new Map(readJson<SourceList>("sources.json").sources.map((s) => [s.id, s]));
  return [...sourcesCache.values()];
}

export function source(id: string): Source {
  sources();
  const s = sourcesCache!.get(id);
  if (!s) throw new Error(`Unknown source "${id}": it is not in data/v1/sources.json`);
  return s;
}

export function status(): Status {
  return readJson<Status>("status.json");
}

/** Indicators that read from a source. */
export function indicatorsOfSource(sourceId: string): CatalogEntry[] {
  return catalog().indicators.filter((e) => e.source_ids.includes(sourceId));
}

export type Pick = { entity?: string; period?: string; dims?: Record<string, string> };

/** One observation: the latest headline by default, or the one matching entity/period/dims exactly. */
export function observation(id: string, pick: Pick = {}): Observation {
  const ind = indicator(id);
  const entity = pick.entity ?? ind.headline_entity;
  const period = pick.period ?? ind.latest.period;
  const dims = pick.dims ?? (pick.period || pick.entity ? undefined : ind.latest.dims);
  const matches = ind.observations.filter(
    (o) =>
      o.entity === entity &&
      o.period === period &&
      (dims === undefined || Object.entries(dims).every(([k, v]) => o.dims[k] === v)) &&
      (dims === undefined || Object.keys(o.dims).length === Object.keys(dims).length),
  );
  if (matches.length !== 1) {
    throw new Error(
      `${id}: ${matches.length} observations match entity=${entity} period=${period} dims=${JSON.stringify(dims ?? {})}; expected exactly 1`,
    );
  }
  const obs = matches[0];
  if (obs.value === null) throw new Error(`${id} ${entity} ${period}: no value (${obs.missing_reason})`);
  return obs;
}

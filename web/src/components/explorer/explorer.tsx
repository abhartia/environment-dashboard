import { catalogEntry, indicator } from "@/lib/data";

import { ExplorerLauncher, type ExplorerSpec } from "./explorer-launcher";

/**
 * The only drill-down widget (plan: one Explorer, at most three toggle groups, chart or table, a country picker).
 * The server renders a button; the interactive island loads on first use and fetches the indicator's public JSON
 * through the generated TanStack Query options. Only redistributable indicators can be explored this way.
 */
export function Explorer({ id, label, dimension, initial }: { id: string; label: string; dimension?: string; initial?: string[] }) {
  const entry = catalogEntry(id);
  if (!entry.downloadable) throw new Error(`<Explorer id="${id}">: ${entry.licence_class} values are not published as files`);
  const ind = indicator(id);
  const dim = dimension ? ind.dimensions.find((d) => d.id === dimension) : undefined;
  if (dimension && !dim) throw new Error(`<Explorer id="${id}">: no dimension "${dimension}"`);
  const spec: ExplorerSpec = {
    id,
    label,
    title: entry.title,
    unit: ind.unit.short,
    decimals: ind.display.decimals,
    headlineEntity: ind.headline_entity,
    countries: entry.geo_coverage !== "global-only",
    dimension: dim ? { id: dim.id, label: dim.label, values: dim.values } : null,
    initial: initial ?? (dim ? [ind.latest.dims[dim.id]] : []),
    fixedDims: Object.fromEntries(Object.entries(ind.latest.dims).filter(([k]) => k !== dim?.id)),
  };
  return <ExplorerLauncher spec={spec} />;
}

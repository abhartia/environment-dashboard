import Link from "next/link";

import { Figure } from "@/components/viz/figure";
import { SeriesChart, type Series } from "@/components/viz/series-chart";
import { catalogEntry, indicator } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { dataPath } from "@/lib/routes";
import { periodToYear } from "@/lib/viz/period";

type Line = { label?: string; entity?: string; dims?: Record<string, string> };

/**
 * A story figure for one indicator: the chart, a written takeaway, every plotted value as a table, and the credit
 * line its licence requires, linking to the data page. Lines default to the indicator's headline series.
 */
export function IndicatorFigure({
  id,
  title,
  takeaway,
  lines,
  from,
  yZero,
}: {
  id: string;
  title: string;
  takeaway: React.ReactNode;
  lines?: Line[];
  /** Only plot periods from this one on (ISO period, inclusive). */
  from?: string;
  yZero?: boolean;
}) {
  const ind = indicator(id);
  const entry = catalogEntry(id);
  const wanted: Line[] = lines ?? [{ dims: ind.latest.dims }];
  const series: Series[] = wanted.map((l, i) => {
    const entity = l.entity ?? ind.headline_entity;
    const dims = l.dims ?? {};
    const obs = ind.observations.filter(
      (o) =>
        o.entity === entity &&
        (from === undefined || o.period >= from) &&
        Object.entries(dims).every(([k, v]) => o.dims[k] === v) &&
        Object.keys(o.dims).length === Object.keys(dims).length,
    );
    if (obs.length < 2) throw new Error(`IndicatorFigure(${id}): line ${i} has ${obs.length} values`);
    const dimLabel = Object.entries(dims)
      .map(([k, v]) => ind.dimensions.find((d) => d.id === k)?.values.find((x) => x.id === v)?.label ?? v)
      .join(", ");
    return {
      key: `${entity}-${JSON.stringify(dims)}`,
      label: l.label ?? (dimLabel || entry.title),
      points: obs.map((o) => ({ x: periodToYear(o.period), y: o.value, lo: o.lower, hi: o.upper })),
    };
  });
  const periods = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].length;
  const rowsByPeriod = new Map<string, (string | null)[]>();
  wanted.forEach((l, i) => {
    const entity = l.entity ?? ind.headline_entity;
    const dims = l.dims ?? {};
    for (const o of ind.observations) {
      if (o.entity !== entity || (from !== undefined && o.period < from)) continue;
      if (!Object.entries(dims).every(([k, v]) => o.dims[k] === v) || Object.keys(o.dims).length !== Object.keys(dims).length) continue;
      const row = rowsByPeriod.get(o.period) ?? wanted.map(() => null);
      row[i] = o.value === null ? null : formatValue(o.value, ind.display.decimals);
      rowsByPeriod.set(o.period, row);
    }
  });
  return (
    <Figure
      id={`fig-${id.replaceAll(".", "-")}`}
      title={title}
      takeaway={takeaway}
      source={
        <>
          Source:{" "}
          <Link href={dataPath(id)} className="underline">
            {entry.provenance.attribution}
          </Link>
          {entry.provenance.attribution.includes(entry.provenance.licence.name) ? null : ` ${entry.provenance.licence.name}.`}
        </>
      }
      table={{
        caption: `${title}: the values plotted (${periods} periods)`,
        columns: ["Period", ...series.map((s) => `${s.label} (${ind.unit.short})`)],
        rows: [...rowsByPeriod.entries()].map(([p, vals]) => [p, ...vals.map((v) => v ?? "")]),
      }}
    >
      <SeriesChart series={series} decimals={ind.display.decimals} unit={ind.unit.short} yZero={yZero} />
      {series.length > 1 ? (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
          {series.map((s, i) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4" style={{ background: `var(--chart-${(i % 5) + 1})` }} />
              {s.label}
            </li>
          ))}
        </ul>
      ) : null}
    </Figure>
  );
}

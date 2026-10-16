"use client";

import { scaleLinear } from "d3-scale";
import { motion, useReducedMotion } from "motion/react";

import { formatValue } from "@/lib/format";
import { cellOf } from "@/lib/dash/future-select";
import type { FutureMeasure, FuturePayload } from "@/lib/dash/types";
import { cn } from "@/lib/utils";

import { useSize } from "../use-size";

/**
 * One place, one measure, every window: the 1995–2014 model simulation, then each 20-year window on each emissions path,
 * as a flat segment across its window (a window is an average, never a line through single years). The chosen path is
 * bold with its range across the climate models; the others are faint; on a region's view the country's own chosen
 * path is a dashed line behind. Selecting a window moves the map to it.
 */
export function WindowChart({
  payload,
  measure,
  entity,
  countryEntity,
  period,
  path,
  onPeriod,
}: {
  payload: FuturePayload;
  measure: FutureMeasure;
  entity: string;
  countryEntity: string | null;
  period: string;
  path: string;
  onPeriod: (period: string) => void;
}) {
  const reduce = useReducedMotion();
  const { ref, size } = useSize<HTMLDivElement>({ w: 160, h: 60 });
  const windows = [{ period: payload.baseline.period, label: payload.baseline.period.replace("/", "–"), past: true }, ...payload.periods.map((p) => ({ period: p.period, label: `${p.from}–${p.to}`, past: false }))].filter(
    (w) => !w.past || measure.baseline,
  );
  const cell = (e: string, p: string, s: string) => cellOf(payload, measure.key, e, p, s);
  const all = windows.flatMap((w) => (w.past ? [cell(entity, w.period, payload.baseline.scenario)] : payload.paths.map((s) => cell(entity, w.period, s.id))));
  const tops = all.flatMap((c) => (c ? [c[2] ?? c[0], c[0]] : []));
  const lows = all.flatMap((c) => (c ? [c[1] ?? c[0], c[0]] : []));

  if (!size || tops.length === 0) return <div ref={ref} className="h-full min-h-16 w-full" />;

  const pad = { l: 4, r: 4, t: 6, b: 18 };
  const x = scaleLinear().domain([0, windows.length]).range([pad.l, size.w - pad.r]);
  const y = scaleLinear()
    .domain([Math.min(0, ...lows), Math.max(...tops)])
    .nice()
    .range([size.h - pad.b, pad.t]);
  const gap = 4;
  const seg = (i: number) => ({ x1: x(i) + gap, x2: x(i + 1) - gap });

  return (
    <div ref={ref} className="h-full min-h-16 w-full">
      <svg width={size.w} height={size.h} className="block" role="img" aria-label={`${measure.kicker} by 20-year window and emissions path`}>
        <line x1={pad.l} x2={size.w - pad.r} y1={y(0)} y2={y(0)} stroke="var(--border)" />
        {windows.map((w, i) => {
          const { x1, x2 } = seg(i);
          const chosen = w.period === period;
          return (
            <g key={w.period}>
              <rect
                x={x(i)}
                y={pad.t}
                width={x(i + 1) - x(i)}
                height={size.h - pad.t}
                fill={chosen ? "var(--accent)" : "transparent"}
                className={cn(!w.past && "cursor-pointer")}
                onClick={() => !w.past && onPeriod(w.period)}
              />
              <text x={(x1 + x2) / 2} y={size.h - 4} textAnchor="middle" className={cn("text-[9px] num sm:text-[10px]", chosen ? "fill-foreground font-semibold" : "fill-muted-foreground")}>
                {w.label}
              </text>
              {w.past
                ? (() => {
                    const c = cell(entity, w.period, payload.baseline.scenario);
                    return c ? <line x1={x1} x2={x2} y1={y(c[0])} y2={y(c[0])} stroke="var(--muted-foreground)" strokeWidth={2} /> : null;
                  })()
                : payload.paths.map((s) => {
                    const c = cell(entity, w.period, s.id);
                    if (!c) return null;
                    const on = s.id === path;
                    const country = countryEntity ? cell(countryEntity, w.period, s.id) : null;
                    return (
                      <g key={s.id}>
                        {on && c[1] !== null && c[2] !== null ? (
                          <motion.rect
                            initial={false}
                            animate={{ y: y(c[2]), height: Math.max(1, y(c[1]) - y(c[2])) }}
                            transition={{ duration: reduce ? 0 : 0.4 }}
                            x={x1}
                            width={x2 - x1}
                            fill="var(--foreground)"
                            fillOpacity={0.1}
                          />
                        ) : null}
                        {on && country ? <line x1={x1} x2={x2} y1={y(country[0])} y2={y(country[0])} stroke="var(--muted-foreground)" strokeDasharray="3 2" /> : null}
                        <line x1={x1} x2={x2} y1={y(c[0])} y2={y(c[0])} stroke={on ? "var(--foreground)" : "var(--muted-foreground)"} strokeOpacity={on ? 1 : 0.45} strokeWidth={on ? 2.5 : 1.25} />
                      </g>
                    );
                  })}
            </g>
          );
        })}
        <text x={size.w - pad.r} y={pad.t + 8} textAnchor="end" className="fill-muted-foreground text-[9px] num">
          {formatValue(y.domain()[1], measure.decimals)} {measure.unit}
        </text>
      </svg>
    </div>
  );
}

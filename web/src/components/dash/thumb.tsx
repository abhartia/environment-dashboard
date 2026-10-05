"use client";

import { area as d3area, line as d3line, stack as d3stack, stackOffsetNone, stackOrderNone } from "d3-shape";
import { scaleLinear } from "d3-scale";
import { motion, useReducedMotion } from "motion/react";

import type { Preview } from "@/lib/dash/types";

const W = 160;
const H = 64;
const EASE = [0.22, 1, 0.36, 1] as const;

/** The shape of a chart in miniature (decorative: the card it sits in names what it shows). */
export function Thumb({ preview, delay = 0 }: { preview: Preview; delay?: number }) {
  const reduce = useReducedMotion();
  const t = { duration: reduce ? 0 : 0.9, ease: EASE, delay: reduce ? 0 : delay };

  if (preview.kind === "bars") {
    const max = Math.max(...preview.bars.map((b) => Math.abs(b.value)));
    const h = H / preview.bars.length;
    return (
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-full w-full" aria-hidden>
        {preview.bars.map((b, i) => (
          <motion.rect
            key={b.key}
            x={0}
            y={i * h + h * 0.15}
            height={h * 0.7}
            rx={1.5}
            fill={b.colour}
            initial={{ width: 0 }}
            animate={{ width: (Math.abs(b.value) / max) * W }}
            transition={{ ...t, delay: t.delay + i * 0.04 }}
          />
        ))}
      </svg>
    );
  }

  const xs = preview.series.flatMap((s) => s.points.map((p) => p[0]));
  const x = scaleLinear().domain([Math.min(...xs), Math.max(...xs)]).range([1, W - 1]);

  if (preview.stacked) {
    const years = [...new Set(xs)].sort((a, b) => a - b);
    const rows = years.map((yr) => {
      const row: Record<string, number> = { x: yr };
      preview.series.forEach((s, i) => {
        const p = s.points.find((q) => q[0] === yr);
        row[`s${i}`] = p && p[1] !== null ? p[1] : Number.NaN;
      });
      return row;
    });
    const layers = d3stack<Record<string, number>>()
      .keys(preview.series.map((_, i) => `s${i}`))
      .value((d, k) => d[k])
      .order(stackOrderNone)
      .offset(stackOffsetNone)(rows);
    const top = Math.max(...layers.flatMap((l) => l.map((d) => d[1]).filter(Number.isFinite)));
    const y = scaleLinear().domain([0, top]).range([H, 2]);
    return (
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-full w-full" aria-hidden>
        {layers.map((layer, i) => (
          <motion.path
            key={i}
            d={
              d3area<(typeof layer)[number]>()
                .defined((d) => Number.isFinite(d[0]) && Number.isFinite(d[1]))
                .x((d) => x(d.data.x))
                .y0((d) => y(d[0]))
                .y1((d) => y(d[1]))(layer) ?? ""
            }
            fill={preview.series[i].colour}
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.9 }}
            transition={{ ...t, delay: t.delay + i * 0.05 }}
          />
        ))}
      </svg>
    );
  }

  const ys = preview.series.flatMap((s) => s.points.flatMap((p) => (p[1] === null ? [] : [p[1]])));
  const y = scaleLinear().domain([Math.min(...ys), Math.max(...ys)]).range([H - 3, 3]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-full w-full" aria-hidden>
      {preview.series.map((s, i) => (
        <motion.path
          key={i}
          d={
            d3line<[number, number | null]>()
              .defined((p) => p[1] !== null)
              .x((p) => x(p[0]))
              .y((p) => y(p[1] as number))(s.points) ?? ""
          }
          fill="none"
          stroke={s.colour}
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={t}
        />
      ))}
    </svg>
  );
}

"use client";

import {
  area as d3area,
  line as d3line,
  stack as d3stack,
  stackOrderNone,
  stackOffsetNone,
} from "d3-shape";
import { scaleLinear } from "d3-scale";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import type { Chart, Series } from "@/lib/dash/types";
import { formatValue } from "@/lib/format";

const M = { top: 16, right: 12, bottom: 32, left: 36 };
const EASE = [0.22, 1, 0.36, 1] as const;

type TimeChartSpec = Extract<Chart, { kind: "area" } | { kind: "line" }>;

/**
 * Area (single or stacked) and line charts over years, drawn with d3-shape and animated with motion. A series that
 * stays between nodes morphs into its new shape; a new one grows from the baseline. Selecting a band or line drills
 * into it. Hover shows the year's values. Gaps in the data stay gaps (no interpolation).
 */
export function TimeChart({
  chart,
  onSelect,
  onPeek,
}: {
  chart: TimeChartSpec;
  onSelect: (nodeId: string) => void;
  onPeek: (nodeId: string) => void;
}) {
  const reduce = useReducedMotion();
  const [hoverYear, setHoverYear] = useState<number | null>(null);
  // Drawn at the container's own pixel size, so axis text stays readable on a phone and the chart fills a desktop.
  const box = useRef<HTMLDivElement>(null);
  // Unknown until measured: nothing is drawn at a guessed size (it would morph from the guess to the real one).
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      setSize({ w, h: Math.max(140, Math.round(entry.contentRect.height)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const W = size?.w ?? 0;
  const H = size?.h ?? 0;
  const stacked = chart.kind === "area" && chart.stacked;

  const years = (() => {
    const ys = new Set<number>();
    for (const s of chart.series) for (const [y] of s.points) ys.add(y);
    return [...ys].sort((a, b) => a - b);
  })();

  const byYear = (() => {
    return years.map((y) => {
      const row: Record<string, number> & { year: number } = { year: y };
      for (const s of chart.series) {
        const p = s.points.find((pt) => pt[0] === y);
        row[s.key] = p && p[1] !== null ? p[1] : Number.NaN;
      }
      return row;
    });
  })();

  const layers = (() => {
    if (!stacked) return null;
    return d3stack<Record<string, number>>()
      .keys(chart.series.map((s) => s.key))
      .value((d, k) => d[k])
      .order(stackOrderNone)
      .offset(stackOffsetNone)(byYear);
  })();

  const yMax = (() => {
    if (layers)
      return Math.max(
        ...layers.flatMap((l) => l.map((d) => d[1]).filter(Number.isFinite)),
      );
    return Math.max(
      ...chart.series.flatMap((s) =>
        s.points.map((p) => p[1]).filter((v): v is number => v !== null),
      ),
    );
  })();
  const yMin = (() => {
    if (layers || chart.kind === "area") return 0;
    return Math.min(
      0,
      ...chart.series.flatMap((s) =>
        s.points.map((p) => p[1]).filter((v): v is number => v !== null),
      ),
    );
  })();

  const y = scaleLinear()
    .domain([yMin, yMax * 1.05])
    .nice()
    .range([H - M.bottom, M.top]);
  const yTicks = y.ticks(5);
  // Axis labels need decimals only when the ticks are closer than 1 apart (e.g. tonnes per person).
  const tickDecimals = Math.max(
    0,
    Math.min(
      chart.decimals,
      -Math.floor(Math.log10(yTicks[1] - yTicks[0] || 1)),
    ),
  );
  // The left margin fits the longest axis label (about 7.5 px a character at 13 px), so "40,000" is never clipped.
  const left = Math.max(
    M.left,
    12 + 7.5 * Math.max(...yTicks.map((t) => formatValue(t, tickDecimals).length)),
  );
  const x = scaleLinear()
    .domain([chart.from, chart.to])
    .range([left, W - M.right]);
  // About one label per 90 px, so years never collide on a phone.
  const xTicks = x
    .ticks(Math.max(3, Math.floor(W / (chart.from < 0 ? 120 : 90))))
    .filter(Number.isInteger);

  const paths = (() => {
    return chart.series.map((s, i) => {
      if (layers) {
        const layer = layers[i];
        const gen = d3area<(typeof layer)[number]>()
          .defined((d) => Number.isFinite(d[0]) && Number.isFinite(d[1]))
          .x((d) => x(d.data.year))
          .y0((d) => y(d[0]))
          .y1((d) => y(d[1]));
        const flat = d3area<(typeof layer)[number]>()
          .defined((d) => Number.isFinite(d[0]) && Number.isFinite(d[1]))
          .x((d) => x(d.data.year))
          .y0(() => y(0))
          .y1(() => y(0));
        return {
          s,
          key: `${s.key}:${years[0]}:${years.length}`,
          d: gen(layer) ?? "",
          from: flat(layer) ?? "",
          fill: true,
        };
      }
      const pts = s.points;
      const key = `${s.key}:${pts[0]?.[0]}:${pts.length}`;
      if (chart.kind === "area") {
        const gen = d3area<[number, number | null]>()
          .defined((p) => p[1] !== null)
          .x((p) => x(p[0]))
          .y0(() => y(0))
          .y1((p) => y(p[1] as number));
        const flat = d3area<[number, number | null]>()
          .defined((p) => p[1] !== null)
          .x((p) => x(p[0]))
          .y0(() => y(0))
          .y1(() => y(0));
        return { s, key, d: gen(pts) ?? "", from: flat(pts) ?? "", fill: true };
      }
      const gen = d3line<[number, number | null]>()
        .defined((p) => p[1] !== null)
        .x((p) => x(p[0]))
        .y((p) => y(p[1] as number));
      return { s, key, d: gen(pts) ?? "", from: "", fill: false };
    });
  })();

  const hoverRow =
    hoverYear === null ? null : byYear.find((r) => r.year === hoverYear);
  const duration = reduce ? 0 : 0.9;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <Legend series={chart.series} onSelect={onSelect} onPeek={onPeek} />
      <div className="min-h-0 flex-1" ref={box}>
        {size ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            width={W}
            height={H}
            className="block h-full w-full touch-pan-y select-none"
            role="img"
            aria-label={`${chart.series.map((s) => s.label).join(", ")}, ${chart.from} to ${chart.to}, in ${chart.unit}`}
            onPointerMove={(e) => {
              const rect = (
                e.currentTarget as SVGSVGElement
              ).getBoundingClientRect();
              const px = ((e.clientX - rect.left) / rect.width) * W;
              setHoverYear(nearest(years, x.invert(px)));
            }}
            onPointerLeave={() => setHoverYear(null)}
          >
            <AnimatePresence initial={false}>
              {yTicks.map((t) => (
                <motion.g
                  key={`y${t}`}
                  initial={{ opacity: 0, y: y(t) }}
                  animate={{ opacity: 1, y: y(t) }}
                  exit={{ opacity: 0 }}
                  transition={{ duration, ease: EASE }}
                >
                  <line x1={left} x2={W - M.right} stroke="var(--grid)" />
                  <text
                    x={left - 10}
                    dy="0.32em"
                    textAnchor="end"
                    className="fill-muted-foreground text-[13px] num"
                  >
                    {formatValue(t, tickDecimals)}
                  </text>
                </motion.g>
              ))}
              {xTicks.map((t) => (
                <motion.text
                  key={`x${t}`}
                  initial={{ opacity: 0, x: x(t) }}
                  animate={{ opacity: 1, x: x(t) }}
                  exit={{ opacity: 0 }}
                  transition={{ duration, ease: EASE }}
                  y={H - 10}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[13px] num"
                >
                  {xLabel(t, true)}
                </motion.text>
              ))}
            </AnimatePresence>
            <line
              x1={left}
              x2={W - M.right}
              y1={y(0)}
              y2={y(0)}
              stroke="var(--foreground)"
              strokeOpacity={0.5}
            />
            <AnimatePresence initial={true}>
              {paths.map(({ s, key, d, from, fill }) => (
                <motion.path
                  key={key}
                  initial={
                    fill
                      ? { d: from, opacity: 0 }
                      : { pathLength: 0, opacity: 0 }
                  }
                  animate={
                    fill ? { d, opacity: 1 } : { d, pathLength: 1, opacity: 1 }
                  }
                  exit={{ opacity: 0, transition: { duration: duration / 3 } }}
                  transition={{ duration, ease: EASE }}
                  fill={fill ? s.colour : "none"}
                  fillOpacity={fill ? 0.92 : undefined}
                  stroke={fill ? "var(--background)" : s.colour}
                  strokeWidth={fill ? 0.75 : 3}
                  strokeLinejoin="round"
                  className={
                    s.drill
                      ? "cursor-pointer outline-none hover:opacity-80 focus-visible:opacity-80"
                      : undefined
                  }
                  tabIndex={s.drill ? 0 : undefined}
                  role={s.drill ? "button" : undefined}
                  aria-label={s.drill ? `${s.label}: drill down` : undefined}
                  onPointerEnter={() => s.drill && onPeek(s.drill)}
                  onClick={() => s.drill && onSelect(s.drill)}
                  onKeyDown={(e) => {
                    if (s.drill && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      onSelect(s.drill);
                    }
                  }}
                />
              ))}
            </AnimatePresence>
            {hoverYear !== null ? (
              <line
                x1={x(hoverYear)}
                x2={x(hoverYear)}
                y1={M.top}
                y2={H - M.bottom}
                stroke="var(--foreground)"
                strokeOpacity={0.35}
              />
            ) : null}
          </svg>
        ) : null}
      </div>
      {hoverRow ? (
        <div className="pointer-events-none absolute top-2 right-2 rounded-lg border border-border bg-background/95 px-3 py-2 text-xs shadow-sm">
          <p className="mb-1 font-semibold num">{xLabel(hoverRow.year)}</p>
          {chart.series.map((s) => (
            <p key={s.key} className="flex items-center gap-2">
              <span
                className="inline-block size-2.5 rounded-sm"
                style={{ background: s.colour }}
              />
              <span className="text-muted-foreground">{s.label}</span>
              <span className="ml-auto pl-3 num font-medium">
                {Number.isFinite(hoverRow[s.key])
                  ? `${formatValue(hoverRow[s.key], Math.abs(hoverRow[s.key]) >= 1000 ? 0 : chart.decimals)} ${chart.unit}`
                  : "no data"}
              </span>
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** The axis position nearest to `v` (positions are sorted). */
function nearest(xs: number[], v: number): number | null {
  if (xs.length === 0) return null;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < v) lo = mid;
    else hi = mid;
  }
  return Math.abs(xs[lo] - v) <= Math.abs(xs[hi] - v) ? xs[lo] : xs[hi];
}

/** 2024 -> "2024"; 2026.625 (mid-August) -> "Aug 2026"; before year 0 -> "12,000 BCE" ("800k BCE" on an axis). */
function xLabel(x: number, compact = false): string {
  if (x < 0)
    return compact && x <= -10_000
      ? `${formatValue(-x / 1000, 0)}k BCE`
      : `${formatValue(-Math.round(x), 0)} BCE`;
  if (Number.isInteger(x)) return String(x);
  return `${MONTHS[Math.floor((x - Math.floor(x)) * 12)]} ${Math.floor(x)}`;
}

function Legend({
  series,
  onSelect,
  onPeek,
}: {
  series: Series[];
  onSelect: (id: string) => void;
  onPeek: (id: string) => void;
}) {
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-1.5 pb-1">
      {series.map((s) =>
        s.drill ? (
          <li key={s.key}>
            <button
              type="button"
              onPointerEnter={() => onPeek(s.drill!)}
              onClick={() => onSelect(s.drill!)}
              className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold hover:border-foreground hover:bg-accent"
            >
              <span
                className="inline-block size-2.5 rounded-sm"
                style={{ background: s.colour }}
              />
              {s.label}
            </button>
          </li>
        ) : (
          <li
            key={s.key}
            className="flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
          >
            <span
              className="inline-block size-2.5 rounded-sm"
              style={{ background: s.colour }}
            />
            {s.label}
          </li>
        ),
      )}
    </ul>
  );
}

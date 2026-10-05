"use client";

import { area as d3area, line as d3line, stack as d3stack, stackOffsetNone, stackOrderNone } from "d3-shape";
import { scaleLinear } from "d3-scale";
import { RotateCcw } from "lucide-react";
import { animate, motion, useMotionValue, useMotionValueEvent, useReducedMotion, useTransform, type MotionValue } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";

import type { StoryRow, StoryValue } from "@/lib/dash/story";
import { formatReadable } from "@/lib/format";
import { dataPath } from "@/lib/routes";

const RDBU = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"];
const SWEEP_SECONDS = 7;

/**
 * The climate story on one screen: six published series on one time axis, in causal order. On arrival a cursor sweeps
 * from 1850 to today, each line drawing behind it and each number reading the value at that moment; then everything
 * rests on the latest values. Moving across the rows travels in time; selecting a row opens its chapter. Every number
 * is a published value and links to its source, whatever moment it shows.
 */
export function StoryTimeline({ rows, from, to }: { rows: StoryRow[]; from: number; to: number }) {
  const reduce = useReducedMotion();
  const router = useRouter();
  const cursor = useMotionValue(to);
  const [t, setT] = useState(to);
  const sweep = useRef<ReturnType<typeof animate> | null>(null);
  useMotionValueEvent(cursor, "change", (v) => setT(v));

  function play() {
    sweep.current?.stop();
    if (reduce) {
      cursor.set(to);
      return;
    }
    cursor.set(from);
    sweep.current = animate(cursor, to, { duration: SWEEP_SECONDS, ease: [0.45, 0, 0.25, 1] });
  }

  useEffect(() => {
    if (reduce) return;
    cursor.set(from);
    sweep.current = animate(cursor, to, { duration: SWEEP_SECONDS, ease: [0.45, 0, 0.25, 1], delay: 0.4 });
    return () => sweep.current?.stop();
  }, [cursor, from, to, reduce]);

  function scrub(e: React.PointerEvent<HTMLElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    sweep.current?.stop();
    cursor.set(from + frac * (to - from));
  }

  function rest() {
    sweep.current?.stop();
    sweep.current = animate(cursor, to, { duration: reduce ? 0 : 0.8, ease: [0.22, 1, 0.36, 1] });
  }

  const atRest = Math.abs(t - to) < 1e-6;
  const ticks = scaleLinear().domain([from, to]).ticks(6).filter(Number.isInteger);

  return (
    <div className="flex h-full flex-col py-3 sm:py-5">
      <div className="flex items-end justify-between gap-4 pb-2 sm:pb-4">
        <div>
          <h1 className="text-2xl sm:text-4xl">The climate, {from} to today</h1>
          <p className="mt-1 hidden text-sm text-muted-foreground sm:block">One story in six measurements. Move across them to travel in time; select one to dig in.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={play}
            aria-label="Play the story again"
            className="grid size-8 place-items-center rounded-full border border-border text-muted-foreground hover:border-foreground hover:text-foreground"
          >
            <RotateCcw aria-hidden className="size-4" />
          </button>
          <p className="text-4xl font-black tracking-tighter num sm:text-6xl" aria-live="off">
            {Math.floor(t)}
          </p>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[8.5rem_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto] sm:grid-cols-[15rem_minmax(0,1fr)] lg:grid-cols-[19rem_minmax(0,1fr)]">
        <ol className="relative col-start-1 row-start-1 grid min-h-0 auto-rows-fr">
          <span aria-hidden className="absolute top-4 bottom-4 left-[5px] w-px bg-border" />
          {rows.map((row) => (
            <li key={row.key} className="relative flex min-h-0 min-w-0 flex-col justify-center gap-0.5 border-b border-border/60 pr-2 pl-5 last:border-b-0 sm:pr-3">
              <span aria-hidden className="absolute top-1/2 left-0 size-[11px] -translate-y-1/2 rounded-full border-2 border-background" style={{ background: row.series.at(-1)!.colour }} />
              <Link href={row.href} className="block text-[11px] leading-tight font-semibold break-words hover:underline sm:text-sm">
                {row.phrase}
              </Link>
              <Reading row={row} t={t} atRest={atRest} />
            </li>
          ))}
        </ol>

        <div
          className="relative col-start-2 row-start-1 grid min-h-0 touch-none auto-rows-fr"
          onPointerMove={scrub}
          onPointerDown={scrub}
          onPointerLeave={rest}
        >
          {rows.map((row) => (
            <button
              key={row.key}
              type="button"
              tabIndex={-1}
              aria-hidden
              onClick={() => router.push(row.href)}
              className="relative min-h-0 cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-accent/40"
            >
              <RowChart row={row} from={from} to={to} cursor={cursor} />
            </button>
          ))}
        </div>

        <div className="relative col-start-2 h-5 text-[11px] text-muted-foreground num" aria-hidden>
          {ticks.map((y, i) => (
            <span key={y} className={i % 2 === 1 ? "absolute top-1 hidden -translate-x-1/2 sm:inline" : "absolute top-1 -translate-x-1/2"} style={{ left: `${((y - from) / (to - from)) * 100}%` }}>
              {y}
            </span>
          ))}
        </div>
      </div>

      <p className="truncate pt-2 text-[11px] text-muted-foreground">
        Data:{" "}
        {rows
          .flatMap((r) => r.credit)
          .filter((c, i, all) => all.findIndex((d) => d.producers === c.producers) === i)
          .map((c, i) => (
            <Fragment key={c.indicator}>
              {i > 0 ? " · " : null}
              <Link href={dataPath(c.indicator)} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
                {c.producers}
              </Link>
            </Fragment>
          ))}
        . Stripes after Ed Hawkins (showyourstripes.info, CC BY 4.0).
      </p>
    </div>
  );
}

/** The latest published value at or before t: what the instrument read at that moment (never interpolated). */
function valueAt(values: StoryValue[], t: number): StoryValue | null {
  let found: StoryValue | null = null;
  for (const v of values) {
    if (v.x > t + 1e-9) break;
    found = v;
  }
  return found;
}

function Reading({ row, t, atRest }: { row: StoryRow; t: number; atRest: boolean }) {
  const v = atRest ? row.values.at(-1)! : valueAt(row.values, t);
  if (!v) {
    return (
      <p className="text-xs text-muted-foreground sm:text-sm">
        <span className="text-xl font-black text-border sm:text-3xl">—</span> records from {row.values[0].period.slice(0, 4)}
      </p>
    );
  }
  const decimals = v.value >= 1000 ? 0 : row.decimals;
  const text = formatReadable(v.value, decimals);
  return (
    <p className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
      <a
        href={dataPath(v.indicator, v.period)}
        data-indicator={v.indicator}
        data-period={v.period}
        data-entity={v.entity}
        aria-label={`${text} ${row.unitLabel}, ${v.period}, show source`}
        aria-haspopup="dialog"
        className="text-xl font-black tracking-tighter num hover:underline sm:text-3xl lg:text-4xl"
      >
        {text}
      </a>
      <span className="line-clamp-2 text-[10px] leading-tight text-muted-foreground sm:text-xs">{row.unitLabel}</span>
    </p>
  );
}

function useSize() {
  const ref = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(50, Math.round(e.contentRect.width)), h: Math.max(30, Math.round(e.contentRect.height)) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

function stripeColour(v: number, lo: number, hi: number): string {
  const s = v < 0 ? -Math.min(1, v / lo) : Math.min(1, v / hi);
  return RDBU[Math.round(((s + 1) / 2) * (RDBU.length - 1))];
}

function RowChart({ row, from, to, cursor }: { row: StoryRow; from: number; to: number; cursor: MotionValue<number> }) {
  const { ref, size } = useSize();
  const w = size?.w ?? 0;
  const h = size?.h ?? 0;
  const pad = 6;
  const x = scaleLinear().domain([from, to]).range([0, w]);
  const reveal = useTransform(cursor, (c) => Math.max(0, x(c)));
  const clipId = `clip-${row.key}`;

  let body: React.ReactNode = null;
  if (!size) body = null;
  else if (row.kind === "stripes") {
    const pts = row.series[0].points.filter((p): p is [number, number] => p[1] !== null);
    const lo = Math.min(...pts.map((p) => p[1]));
    const hi = Math.max(...pts.map((p) => p[1]));
    body = pts.map(([yr, v]) => <rect key={yr} x={x(yr)} y={0} width={Math.max(1, x(yr + 1) - x(yr)) + 0.5} height={h} fill={stripeColour(v, lo, hi)} />);
  } else if (row.kind === "stacked") {
    const years = [...new Set(row.series.flatMap((s) => s.points.map((p) => p[0])))].sort((a, b) => a - b);
    const table = years.map((yr) => {
      const r: Record<string, number> = { x: yr };
      for (const s of row.series) {
        const p = s.points.find((q) => q[0] === yr);
        r[s.key] = p && p[1] !== null ? p[1] : Number.NaN;
      }
      return r;
    });
    const layers = d3stack<Record<string, number>>()
      .keys(row.series.map((s) => s.key))
      .value((d, k) => d[k])
      .order(stackOrderNone)
      .offset(stackOffsetNone)(table);
    const top = Math.max(...layers.flatMap((l) => l.map((d) => d[1]).filter(Number.isFinite)));
    const y = scaleLinear().domain([0, top]).range([h, pad]);
    body = layers.map((layer, i) => (
      <path
        key={row.series[i].key}
        d={
          d3area<(typeof layer)[number]>()
            .defined((d) => Number.isFinite(d[0]) && Number.isFinite(d[1]))
            .x((d) => x(d.data.x))
            .y0((d) => y(d[0]))
            .y1((d) => y(d[1]))(layer) ?? ""
        }
        fill={row.series[i].colour}
      />
    ));
  } else {
    // Every row starts at zero (or below, for a value that goes negative), so no change looks bigger than it is.
    const ys = row.series.flatMap((s) => s.points.flatMap((p) => (p[1] === null ? [] : [p[1]])));
    const y = scaleLinear().domain([Math.min(0, ...ys), Math.max(...ys)]).range([h, pad]);
    body = row.series.map((s) => {
      const line = d3line<[number, number | null]>()
        .defined((p) => p[1] !== null)
        .x((p) => x(p[0]))
        .y((p) => y(p[1] as number));
      const fill = d3area<[number, number | null]>()
        .defined((p) => p[1] !== null)
        .x((p) => x(p[0]))
        .y0(h)
        .y1((p) => y(p[1] as number));
      return (
        <g key={s.key}>
          <path d={fill(s.points) ?? ""} fill={s.colour} fillOpacity={0.12} />
          <path d={line(s.points) ?? ""} fill="none" stroke={s.colour} strokeWidth={2} strokeLinejoin="round" />
        </g>
      );
    });
  }

  return (
    <svg ref={ref} width="100%" height="100%" className="absolute inset-0 block" aria-hidden>
      <defs>
        <clipPath id={clipId}>
          <motion.rect x={0} y={0} height={h} width={reveal} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>{body}</g>
      <motion.line x1={reveal} x2={reveal} y1={0} y2={h} stroke="var(--foreground)" strokeWidth={1.5} strokeOpacity={0.6} />
    </svg>
  );
}

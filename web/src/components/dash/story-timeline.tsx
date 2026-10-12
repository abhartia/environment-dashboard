"use client";

import { area as d3area, line as d3line, stack as d3stack, stackOffsetNone, stackOrderNone } from "d3-shape";
import { scaleLinear } from "d3-scale";
import { RotateCcw } from "lucide-react";
import { animate, motion, useMotionValue, useMotionValueEvent, useReducedMotion, useTransform, type MotionValue } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";

import type { StoryBand, StoryRow, StoryValue } from "@/lib/dash/story";
import type { SeriesPoint } from "@/lib/dash/types";
import { formatReadable } from "@/lib/format";
import { dataPath } from "@/lib/routes";
import { cn } from "@/lib/utils";

const RDBU = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"];
const SWEEP_SECONDS = 7;
const EASE_SWEEP = [0.45, 0, 0.25, 1] as const;
/** The story's two columns (words, charts), shared by the grid, the list and each row so they line up exactly. */
const COLUMNS = "grid-cols-[8.5rem_minmax(0,1fr)] sm:grid-cols-[15rem_minmax(0,1fr)] lg:grid-cols-[19rem_minmax(0,1fr)]";
/** The landing beat: bands settle into ink one after another, this far apart. */
const STAGGER_MS = 80;

/**
 * The climate story on one screen: seven published series on one time axis, in causal order, each with a band under
 * its chart saying what that change means for people. On arrival a cursor sweeps from 1850 to today, each line drawing
 * behind it and each number reading the value at that moment; a band appears once its own record (or its claim)
 * begins, so the change is drawn first and what it means lands at the end. Moving across a chart travels in time;
 * selecting a row opens its chapter, and a band opens the view it quotes. Every number is a published value and links
 * to its source, whatever moment it shows.
 */
export function StoryTimeline({ rows, from, to }: { rows: StoryRow[]; from: number; to: number }) {
  const reduce = useReducedMotion();
  const router = useRouter();
  const cursor = useMotionValue(to);
  const [t, setT] = useState(to);
  // Once the sweep lands on today the bands settle into ink; while it travels they are drawn in the muted colour. The
  // settling is staggered once, on landing (beat); scrubbing shows and hides bands at once.
  const [landed, setLanded] = useState(true);
  const [beat, setBeat] = useState(false);
  const sweep = useRef<ReturnType<typeof animate> | null>(null);
  const restTimer = useRef<number | null>(null);
  const beatTimer = useRef<number | null>(null);
  useMotionValueEvent(cursor, "change", (v) => setT(v));

  function run(delay: number) {
    sweep.current?.stop();
    cursor.set(from);
    let started = false;
    sweep.current = animate(cursor, to, {
      duration: SWEEP_SECONDS,
      ease: EASE_SWEEP,
      delay,
      onUpdate: () => {
        if (started) return;
        started = true;
        setLanded(false);
      },
      onComplete: () => {
        setLanded(true);
        setBeat(true);
        if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
        beatTimer.current = window.setTimeout(() => setBeat(false), rows.length * STAGGER_MS + 300);
      },
    });
  }

  function play() {
    if (reduce) {
      sweep.current?.stop();
      cursor.set(to);
      setLanded(true);
      return;
    }
    run(0);
  }

  useEffect(() => {
    if (reduce) return;
    run(0.4);
    return () => {
      sweep.current?.stop();
      if (restTimer.current !== null) window.clearTimeout(restTimer.current);
      if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    };
    // The sweep runs once on arrival; replays go through play().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursor, from, to, reduce]);

  function scrub(e: React.PointerEvent<HTMLElement>) {
    if (restTimer.current !== null) {
      window.clearTimeout(restTimer.current);
      restTimer.current = null;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    sweep.current?.stop();
    setLanded(true);
    cursor.set(from + frac * (to - from));
  }

  function rest() {
    if (restTimer.current !== null) {
      window.clearTimeout(restTimer.current);
      restTimer.current = null;
    }
    sweep.current?.stop();
    setLanded(true);
    sweep.current = animate(cursor, to, { duration: reduce ? 0 : 0.8, ease: [0.22, 1, 0.36, 1] });
  }

  /** Leaving one chart for the next is not leaving the story: rest only if no chart is entered again soon. */
  function leave() {
    restTimer.current = window.setTimeout(rest, 120);
  }

  /** Keyboard focus ends the sweep at once, so every number and band is there to read and reach. */
  function settle(e: React.FocusEvent<HTMLElement>) {
    if (atRest || !(e.target as HTMLElement).matches(":focus-visible")) return;
    if (restTimer.current !== null) {
      window.clearTimeout(restTimer.current);
      restTimer.current = null;
    }
    sweep.current?.stop();
    cursor.set(to);
    setLanded(true);
  }

  const atRest = Math.abs(t - to) < 1e-6;
  const ticks = scaleLinear().domain([from, to]).ticks(6).filter(Number.isInteger);

  return (
    <div className="flex h-full flex-col py-3 sm:py-5" onFocus={settle}>
      <div className="flex items-end justify-between gap-4 pb-2 sm:pb-4">
        <div>
          <h1 className="text-2xl sm:text-4xl">The climate, {from} to today</h1>
          <p className="mt-1 hidden text-sm text-muted-foreground sm:block [@media(max-height:600px)]:hidden">
            One story in seven measurements, and what they mean for people. Move across them to travel in time; select one to dig in.
          </p>
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

      <div className={cn("grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto]", COLUMNS)}>
        {/*
          One list, a row per step: its words and number, then its chart and band, so keyboard order runs row by row.
          Below a usable height (landscape phones) the rows keep a floor and the list scrolls, never the page.
        */}
        <ol className={cn("relative col-span-2 grid min-h-0 auto-rows-fr [@media(max-height:640px)]:auto-rows-[minmax(4rem,1fr)] [@media(max-height:640px)]:overflow-y-auto", COLUMNS)}>
          <span aria-hidden className="absolute top-4 bottom-4 left-[5px] w-px bg-border" />
          {rows.map((row, i) => (
            <li key={row.key} className={cn("col-span-2 grid min-h-0 border-b border-border/60 last:border-b-0", COLUMNS)}>
              <div className="relative flex min-h-0 min-w-0 flex-col justify-center gap-0.5 pr-2 pl-5 sm:pr-3 [@media(max-height:760px)]:gap-0">
                <span aria-hidden className="absolute top-1/2 left-0 size-[11px] -translate-y-1/2 rounded-full border-2 border-background" style={{ background: row.series.filter((x) => !x.context).at(-1)!.colour }} />
                <Link href={row.href} className="block text-[11px] leading-tight font-semibold break-words hover:underline sm:text-sm [@media(max-height:760px)]:leading-none">
                  {row.phrase}
                </Link>
                <Reading row={row} t={t} atRest={atRest} />
              </div>
              <div className="relative flex min-h-0 touch-none flex-col" onPointerMove={scrub} onPointerDown={scrub} onPointerLeave={leave}>
                <button
                  type="button"
                  tabIndex={-1}
                  aria-hidden
                  onClick={() => router.push(row.href)}
                  className="relative min-h-0 flex-1 cursor-pointer hover:bg-accent/40"
                >
                  <RowChart row={row} from={from} to={to} cursor={cursor} />
                </button>
                {row.band ? <Band band={row.band} index={i} from={from} to={to} cursor={cursor} t={t} atRest={atRest} landed={landed} stagger={beat} onRest={rest} /> : null}
              </div>
            </li>
          ))}
        </ol>

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

/** A value as published: thousands read without decimals, never with more than the producer gives. */
function shown(v: StoryValue): string {
  return formatReadable(v.value, Math.abs(v.value) >= 1000 ? 0 : v.decimals);
}

/** A traced number: the link the Trace listener opens as the value's source panel (its data page without JavaScript). */
function Traced({ v, label, className, band, dated = false }: { v: StoryValue; label: string; className: string; band?: string; dated?: boolean }) {
  const text = shown(v);
  const status = v.status === "projection" ? "projected" : v.status === "preliminary" ? "preliminary" : null;
  return (
    <a
      href={dataPath(v.indicator, v.period)}
      data-indicator={v.indicator}
      data-period={v.period}
      data-entity={v.entity}
      data-sowhat-of={band}
      aria-label={`${text} ${label}${v.period && !dated ? `, ${v.period}` : ""}${status ? ` (${status})` : ""}, show source`}
      aria-haspopup="dialog"
      className={cn("num hover:underline", className)}
    >
      {text}
    </a>
  );
}

function Reading({ row, t, atRest }: { row: StoryRow; t: number; atRest: boolean }) {
  const v = atRest ? row.values.at(-1)! : valueAt(row.values, t);
  if (!v) {
    return (
      <p className="text-xs text-muted-foreground sm:text-sm">
        <span className="text-xl font-black text-border sm:text-3xl [@media(max-height:760px)]:text-lg">—</span> records from {row.values[0].period.slice(0, 4)}
      </p>
    );
  }
  const unit = row.context ? `${row.unitLabel} ${row.context}` : row.unitLabel;
  return (
    <p className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
      <Traced
        v={v}
        label={unit}
        className="text-xl font-black tracking-tighter sm:text-3xl lg:text-4xl [@media(max-height:760px)]:text-lg [@media(max-height:760px)]:leading-none sm:[@media(max-height:760px)]:text-2xl lg:[@media(max-height:760px)]:text-3xl"
      />
      <span className="line-clamp-2 text-[10px] leading-tight text-muted-foreground sm:text-xs sm:[@media(max-height:760px)]:line-clamp-1">
        {unit}
        {row.note ? <span className="hidden sm:inline">; {row.note}</span> : null}
        {v.status === "preliminary" ? (
          <span className="ml-1 font-semibold tracking-wide uppercase">
            <span className="sm:hidden">prelim.</span>
            <span className="hidden sm:inline">preliminary</span>
          </span>
        ) : null}
      </span>
    </p>
  );
}

/**
 * What the change means: the quoted view's number (traced) and its words (a link to that view), with that view's own
 * series drawn faintly on the same time axis. It shows once its record or its claim begins, and stops a tap or a drag
 * on its words from moving the cursor, so the words open their view.
 */
function Band({
  band,
  index,
  from,
  to,
  cursor,
  t,
  atRest,
  landed,
  stagger,
  onRest,
}: {
  band: StoryBand;
  index: number;
  from: number;
  to: number;
  cursor: MotionValue<number>;
  t: number;
  atRest: boolean;
  landed: boolean;
  stagger: boolean;
  onRest: () => void;
}) {
  const v = atRest ? band.values.at(-1)! : valueAt(band.values, t);
  const visible = v !== null;
  const shownValue = v ?? band.values.at(-1)!;
  const year = shownValue.period.slice(0, 4);
  const [before, after] = band.words.includes("{year}") ? band.words.split("{year}") : [band.words, ""];
  const words = `${band.unit ? `${band.unitLabel} ` : ""}${before}${band.words.includes("{year}") ? year : ""}${after}`;
  // The words keep clear of the quoted series, which starts late on the axis; with no series they may use the width.
  const first = band.points[0]?.[0];
  const room = first === undefined ? "calc(100% - 0.5rem)" : `calc(${((first - from) / (to - from)) * 100}% - 0.75rem)`;
  const stop = (e: React.PointerEvent) => e.stopPropagation();
  return (
    <div data-sowhat={band.key} className="relative flex h-[clamp(1.5rem,32%,2.25rem)] shrink-0 items-center border-t border-dotted border-border pl-1">
      {band.points.length > 0 ? <BandLine id={`band-${band.key}`} points={band.points} from={from} to={to} cursor={cursor} /> : null}
      <p
        onPointerDown={stop}
        onPointerMove={stop}
        onPointerEnter={onRest}
        style={{ "--room": room, transitionDelay: stagger ? `${index * STAGGER_MS}ms` : "0ms" } as React.CSSProperties}
        className={cn(
          "relative line-clamp-2 max-w-[calc(100%-0.5rem)] rounded-sm bg-background/75 pr-1 text-[10px] leading-[1.15] motion-safe:transition-[opacity,transform,color,visibility] motion-safe:duration-300 sm:max-w-(--room) sm:bg-transparent sm:pr-0 sm:text-xs",
          // A band with no value at this moment hides at once, so it never shows another moment's number.
          visible ? "visible opacity-100" : "invisible opacity-0 transition-none",
          landed ? "translate-y-0 text-foreground" : "translate-y-1 text-muted-foreground",
        )}
      >
        <Traced
          v={shownValue}
          label={words}
          band={band.key}
          dated={band.words.includes("{year}") || band.points.length === 0}
          className="font-black tracking-tight focus-visible:outline-offset-[-2px]"
        />{" "}
        <Link href={band.href} className="font-medium hover:underline focus-visible:outline-offset-[-2px]">
          {words}
        </Link>
        {shownValue.status === "projection" ? (
          <>
            {" "}
            <span className="hidden font-semibold tracking-wide text-muted-foreground uppercase sm:inline">projected</span>
          </>
        ) : null}
      </p>
    </div>
  );
}

/** The quoted view's own series as a faint line on the story's time axis, drawn behind the same cursor. */
function BandLine({ id, points, from, to, cursor }: { id: string; points: SeriesPoint[]; from: number; to: number; cursor: MotionValue<number> }) {
  const { ref, size } = useSize();
  const w = size?.w ?? 0;
  const h = size?.h ?? 0;
  const x = scaleLinear().domain([from, to]).range([0, w]);
  const reveal = useTransform(cursor, (c) => Math.max(0, x(c)));
  const pts = points.filter((p): p is [number, number] => p[1] !== null);
  const ys = pts.map((p) => p[1]);
  const y = scaleLinear().domain([Math.min(0, ...ys), Math.max(...ys)]).range([h - 3, 3]);
  const clipId = `clip-${id}`;
  return (
    <svg ref={ref} width="100%" height="100%" className="absolute inset-0 block" aria-hidden>
      {size ? (
        <>
          <defs>
            <clipPath id={clipId}>
              <motion.rect x={0} y={0} height={h} width={reveal} />
            </clipPath>
          </defs>
          <g clipPath={`url(#${clipId})`} className="text-foreground">
            {pts.length === 1 ? (
              <circle cx={x(pts[0][0])} cy={y(pts[0][1])} r={2.5} fill="currentColor" />
            ) : (
              <>
                <path d={d3area<[number, number]>().x((p) => x(p[0])).y0(h).y1((p) => y(p[1]))(pts) ?? ""} fill="currentColor" fillOpacity={0.08} />
                <path d={d3line<[number, number]>().x((p) => x(p[0])).y((p) => y(p[1]))(pts) ?? ""} fill="none" stroke="currentColor" strokeWidth={1.5} strokeOpacity={0.7} />
              </>
            )}
          </g>
        </>
      ) : null}
    </svg>
  );
}

function useSize() {
  const ref = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(50, Math.round(e.contentRect.width)), h: Math.max(16, Math.round(e.contentRect.height)) }));
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
    const y = scaleLinear().domain([Math.min(0, ...ys), Math.max(0, ...ys)]).range([h, pad]);
    body = row.series.map((s) => {
      const line = d3line<[number, number | null]>()
        .defined((p) => p[1] !== null)
        .x((p) => x(p[0]))
        .y((p) => y(p[1] as number));
      const fill = d3area<[number, number | null]>()
        .defined((p) => p[1] !== null)
        .x((p) => x(p[0]))
        .y0(y(0))
        .y1((p) => y(p[1] as number));
      if (s.context) {
        return (
          <g key={s.key} className="text-muted-foreground">
            <path d={line(s.points) ?? ""} fill="none" stroke="currentColor" strokeOpacity={0.5} strokeWidth={1.25} strokeLinejoin="round" />
          </g>
        );
      }
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

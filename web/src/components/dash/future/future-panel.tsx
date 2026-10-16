"use client";

import { ArrowLeft, ChevronDown } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

import { headlineFor, measureOf } from "@/lib/dash/future-select";
import type { Drill, FuturePayload, FuturePlace, Headline } from "@/lib/dash/types";
import { formatReadable } from "@/lib/format";
import { dataPath } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { TracedValue } from "../traced-value";
import { WindowChart } from "./window-chart";

/** A small traced number in a line of text: it opens its source like every number on the site. */
function TracedText({ h, className }: { h: Headline; className?: string }) {
  const text = formatReadable(h.value, Math.abs(h.value) >= 1000 ? 0 : h.decimals);
  return (
    <a
      href={dataPath(h.indicator, h.period)}
      data-indicator={h.indicator}
      data-period={h.period}
      data-entity={h.entity}
      data-slice={h.sliceLabel}
      aria-label={`${text} ${h.unitLabel}, ${h.period.replace("/", " to ")}${h.status === "projection" ? " (projected)" : ""}${h.sliceLabel ? `, ${h.sliceLabel}` : ""}, show source`}
      aria-haspopup="dialog"
      className={cn("font-semibold text-foreground num hover:underline", className)}
    >
      {text}
    </a>
  );
}

/** "2040/2059" as the reader reads it, one string (so it is one text node, never split by the renderer). */
const span = (period: string) => period.replace("/", "–");

/**
 * What the chosen place looks like in the chosen window on the chosen path, for the chosen measure: the published
 * median (big, traced), what it is (window, path, the range across the climate models, the models' simulation of
 * 1995–2014 it compares with, all traced, and what it is averaged over), the windows chart, and the other measures for
 * the same place as a list that also switches the map. Every number is chosen from the node's payload, never computed.
 * On a tablet the two halves sit side by side; on a phone they stack and the panel scrolls inside itself if it must.
 */
export function FuturePanel({
  payload,
  place,
  country,
  trail,
  measureKey,
  period,
  path,
  ranked,
  drills,
  onPeriod,
  onMeasure,
  onUp,
  onPlace,
}: {
  payload: FuturePayload;
  place: FuturePlace;
  /** The country of a region's view (its line is drawn faint behind), or null. */
  country: FuturePlace | null;
  trail: { label: string; onClick: () => void }[];
  measureKey: string;
  period: string;
  path: string;
  /** The place was chosen because it ranks first for this measure and window (the world view before any choice), alone or
   * tied with others; null when the reader chose it. */
  ranked: "first" | "tied" | null;
  drills: Drill[];
  onPeriod: (period: string) => void;
  onMeasure: (key: string) => void;
  onUp: (() => void) | null;
  onPlace: (entity: string) => void;
}) {
  const measure = measureOf(payload, measureKey);
  const pathInfo = payload.paths.find((p) => p.id === path)!;
  const h = headlineFor(payload, measure, place, period, path);
  const lower = headlineFor(payload, measure, place, period, path, "lower");
  const upper = headlineFor(payload, measure, place, period, path, "upper");
  const base = measure.baseline ? headlineFor(payload, measure, place, payload.baseline.period, payload.baseline.scenario) : null;
  const source = "the World Bank's Climate Change Knowledge Portal";

  return (
    <section
      data-probe
      aria-label={`${place.name}: ${measure.kicker}`}
      className="grid h-full min-h-0 content-start gap-x-6 gap-y-2 overflow-y-auto pr-1 max-sm:pb-6 max-sm:[mask-image:linear-gradient(to_bottom,black_calc(100%-1.5rem),transparent)] sm:grid-cols-2 lg:flex lg:flex-col"
    >
      <div className="flex min-w-0 flex-col gap-2 [@media(min-height:760px)]:gap-3">
        <nav aria-label="Where you are" className="flex min-h-7 flex-wrap items-center gap-x-2 text-sm">
          {onUp ? (
            <button type="button" onClick={onUp} aria-label="Up a level" className="grid size-7 shrink-0 place-items-center rounded-full border border-border hover:border-foreground">
              <ArrowLeft aria-hidden className="size-3.5" />
            </button>
          ) : null}
          {trail.map((t, i) => (
            <span key={t.label} className="flex items-center gap-2">
              {i > 0 ? <span aria-hidden className="h-px w-3 bg-border" /> : null}
              <button type="button" onClick={t.onClick} className="font-medium text-muted-foreground hover:text-foreground">
                {t.label}
              </button>
            </span>
          ))}
          {trail.length ? <span aria-hidden className="h-px w-3 bg-border" /> : null}
          <span>
            <span className="font-semibold" aria-current="page">
              {place.name}
            </span>
            {ranked ? <span className="text-muted-foreground">{ranked === "tied" ? ", tied for the most of any country" : ", the most of any country"}</span> : null}
          </span>
        </nav>

        <div className="flex flex-col gap-1">
          <h2 className="text-base leading-tight font-bold sm:text-xl">{measure.kicker}</h2>
          {h ? (
            <TracedValue
              h={h}
              suffix={measure.unit}
              className="gap-2 text-4xl leading-none font-black tracking-tighter sm:text-5xl [@media(min-height:800px)]:sm:text-6xl"
              statusClassName="text-[0.25em] text-muted-foreground"
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              No data for {place.name} in {source}.
            </p>
          )}
          <p className="hidden text-xs text-muted-foreground sm:block [@media(max-height:760px)]:hidden">{measure.unitLabel}</p>
        </div>

        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
          {/* On a phone the dial naming the years sits right above the map. */}
          <dt className="text-muted-foreground max-sm:hidden">Years</dt>
          <dd className="max-sm:hidden">{`${span(period)}, projected`}</dd>
          <dt className="text-muted-foreground">Path</dt>
          <dd>{pathInfo.label}</dd>
          <dt className="text-muted-foreground">Models</dt>
          <dd>
            {`The ${payload.statistics.value}`}
            {lower && upper ? (
              <>
                {`; from the ${payload.statistics.lower} to the ${payload.statistics.upper} percentile, `}
                <TracedText h={lower} /> to <TracedText h={upper} /> {measure.unit}
              </>
            ) : null}
          </dd>
          {base ? (
            <>
              <dt className="text-muted-foreground">Past</dt>
              <dd>
                <TracedText h={base} /> {measure.unit} {`in ${span(payload.baseline.period)}, as the models simulate it`}
              </dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Where</dt>
          <dd>Averaged over the land of {place.name}, not weighted by where people live</dd>
        </dl>
      </div>

      <div className="flex min-w-0 flex-col gap-2 [@media(min-height:760px)]:gap-3">
        <div className="h-14 min-h-14 shrink-0 [@media(min-height:800px)]:h-24">
          <WindowChart payload={payload} measure={measure} entity={place.entity} countryEntity={country?.entity ?? null} period={period} path={path} onPeriod={onPeriod} />
        </div>

        <MeasureList payload={payload} place={place} current={measure.key} period={period} path={path} onMeasure={onMeasure} />

        {drills.length ? (
          <ul aria-label={`More on ${place.name}`} className="flex flex-wrap gap-1.5">
            {drills.map((d) => (
              <li key={d.to}>
                <a href={d.to} className="block rounded-md border border-border px-2 py-1 text-xs font-semibold hover:border-foreground">
                  {d.label}
                </a>
              </li>
            ))}
          </ul>
        ) : null}

        {payload.unmatched.length ? (
          <Collapsible className="text-xs text-muted-foreground">
            <CollapsibleTrigger className="group flex items-center gap-1 font-medium hover:text-foreground">
              <ChevronDown aria-hidden className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
              Regions not on this map (their shapes do not match the source&apos;s)
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                {payload.unmatched.map((e) => (
                  <li key={e}>
                    <button type="button" onClick={() => onPlace(e)} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
                      {payload.places.find((x) => x.entity === e)?.name ?? e}
                    </button>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </div>
    </section>
  );
}

/**
 * The other measures for the same place, window and path: each row names the measure, shows its traced value and
 * colours the map by it. The number and the switch are siblings (a link, and a button stretched over the row), never
 * one inside the other. On a phone the rows become a strip of small cards.
 */
function MeasureList({ payload, place, current, period, path, onMeasure }: { payload: FuturePayload; place: FuturePlace; current: string; period: string; path: string; onMeasure: (key: string) => void }) {
  return (
    <ul aria-label="Colour the map by" data-scroll="x" className="-mx-1 flex shrink-0 gap-2 overflow-x-auto px-1 pb-1 sm:mx-0 sm:flex-col sm:gap-0 sm:overflow-visible sm:p-0">
      {payload.measures
        .filter((m) => m.key !== current)
        .map((m) => {
          const h = headlineFor(payload, m, place, period, path);
          return (
            <li
              key={m.key}
              className="relative flex w-36 shrink-0 flex-col justify-between gap-1 rounded-lg border border-border p-2 hover:bg-accent/60 sm:w-auto sm:flex-row sm:items-baseline sm:gap-3 sm:rounded-md sm:border-0 sm:px-2 sm:py-0.5 sm:[@media(min-height:760px)]:py-1"
            >
              <button
                type="button"
                onClick={() => onMeasure(m.key)}
                className="line-clamp-2 text-left text-xs leading-tight font-medium after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring sm:line-clamp-none"
              >
                {m.kicker}
              </button>
              <span className="relative z-10 flex shrink-0 items-baseline gap-1 whitespace-nowrap">
                {h ? <TracedText h={h} className="text-sm" /> : <span className="text-xs text-muted-foreground">No data</span>}
                <span className="text-[11px] text-muted-foreground">{m.unit}</span>
              </span>
            </li>
          );
        })}
    </ul>
  );
}

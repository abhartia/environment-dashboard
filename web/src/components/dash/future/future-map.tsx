"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { Fragment, useId, useMemo, useState } from "react";
import type { Topology } from "topojson-specification";

import { getRegionShapesOptions, getWorldShapesOptions } from "@/gen/hey-api/@tanstack/react-query.gen";
import { headlineFor, measureOf, sliceKey, type FutureState } from "@/lib/dash/future-select";
import { crossHref } from "@/lib/dash/href";
import type { DrillNode, FuturePayload, FuturePlace } from "@/lib/dash/types";
import { formatReadable } from "@/lib/format";
import { dataPath } from "@/lib/routes";

import { scaleFor } from "./colour";
import { FuturePanel } from "./future-panel";
import { MapLegend } from "./map-legend";
import { MapView } from "./map-view";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

const nodeQuery = (id: string) => ({
  queryKey: ["dash", "future", id],
  queryFn: () => fetchJson<DrillNode>(`/dash-data/future/${id}.json`),
  staleTime: Number.POSITIVE_INFINITY,
});


/**
 * The future, on a map: every country coloured by the chosen measure in the chosen 20-year window on the chosen emissions
 * path, with a panel that reads one place in full. Hovering, focusing or tapping a place reads it; selecting it opens
 * its own map of states and provinces (where the source's regions have shapes), and a region opens the same way. The
 * reader's choices live in the URL, so the back button walks back out and any view can be shared.
 */
export function FutureMap({
  state,
  onChange,
}: {
  state: FutureState;
  onChange: (changes: Record<string, string | null>, push: boolean) => void;
}) {
  const reduce = useReducedMotion();
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  // A place read on one map means nothing on the next: moving between the world, a country and a region forgets the
  // place last hovered or tapped (a finger never leaves a place, so nothing else would), and a new country also forgets
  // the keyboard's place.
  const [shown, setShown] = useState({ country: state.country, region: state.region });
  if (shown.country !== state.country || shown.region !== state.region) {
    setShown({ country: state.country, region: state.region });
    setHovered(null);
    if (shown.country !== state.country) setFocused(null);
  }
  // Whether the country's map opened from the keyboard, so focus can move onto it.
  const hatch = useId();
  const [openedByKey, setOpenedByKey] = useState(false);
  const root = useQuery(nodeQuery("root"));
  const country = useQuery({ ...nodeQuery(`c-${state.country ?? ""}`), enabled: state.country !== null });
  // The shapes come through the data API's own query options (pipeline/schema/openapi.json); a country's regions only
  // when its node says it has a map of them.
  const world = useQuery({ ...getWorldShapesOptions(), staleTime: Number.POSITIVE_INFINITY, enabled: Boolean(root.data?.future?.geo) });
  const regionsFor = country.data?.future?.geo ? country.data.future.place : null;
  const regions = useQuery({
    ...getRegionShapesOptions({ path: { entity: regionsFor ?? "" } }),
    staleTime: Number.POSITIVE_INFINITY,
    enabled: regionsFor !== null,
  });

  const rootPayload = root.data?.future;
  const countryPayload = state.country ? country.data?.future : undefined;
  const payload: FuturePayload | undefined = countryPayload ?? rootPayload;

  const measure = rootPayload ? measureOf(rootPayload, state.measure) : null;
  const scale = useMemo(() => (measure ? scaleFor(measure) : null), [measure]);

  if (root.isError) {
    return <p className="grid h-full place-items-center text-muted-foreground">The map of the future could not be loaded ({String(root.error.message)}).</p>;
  }
  if (!rootPayload || !measure || !scale) {
    return (
      <p className="grid h-full place-items-center text-sm text-muted-foreground" aria-busy>
        Loading the map…
      </p>
    );
  }

  const slice = sliceKey(state.period, state.path);
  const fillFrom = (p: FuturePayload) => (id: string) => {
    const i = p.places.findIndex((x) => x.entity === id);
    const c = i >= 0 ? p.values[measure.key]?.[slice]?.[i] : null;
    return c ? scale.colour(c[0]) : null;
  };
  const nameIn = (p: FuturePayload) => (id: string) => p.places.find((x) => x.entity === id)?.name ?? id;

  // Before any choice, the world view reads the country with the largest value for this measure and window (chosen
  // from the published values, never computed). Countries sharing that value are a tie, and the panel says so.
  const ranked = (() => {
    let best: { place: FuturePlace; v: number } | null = null;
    let tied = false;
    rootPayload.places.forEach((pl, i) => {
      const c = rootPayload.values[measure.key]?.[slice]?.[i];
      if (pl.kind !== "country" || !c) return;
      if (!best || c[0] > best.v) {
        best = { place: pl, v: c[0] };
        tied = false;
      } else if (c[0] === best.v) {
        tied = true;
        if (pl.entity < best.place.entity) best = { place: pl, v: c[0] };
      }
    });
    const b = best as { place: FuturePlace; v: number } | null;
    return b ? { place: b.place, tied } : null;
  })();

  const level = state.country && countryPayload ? countryPayload : rootPayload;
  // Only a place the payloads hold is ever read: an unknown or stale place in the URL says so, and never borrows
  // another place's values. The top-ranked country is read only when nothing at all is chosen.
  const known = (id: string | null) => (id ? (level.places.find((p) => p.entity === id) ?? rootPayload.places.find((p) => p.entity === id)) : undefined);
  const chosen = state.region ?? state.country;
  const readPlace = known(focused) ?? known(hovered) ?? (chosen ? known(chosen) : ranked?.place) ?? null;
  const pending = state.country !== null && country.isPending;
  const readPayload = level.places.some((p) => p.entity === readPlace?.entity) ? level : rootPayload;
  const countryPlace = state.country ? (rootPayload.places.find((p) => p.entity === state.country) ?? null) : null;
  const isRegion = readPlace?.kind === "region";

  const win = rootPayload.periods.find((p) => p.period === state.period)!;
  const pathInfo = rootPayload.paths.find((p) => p.id === state.path)!;
  const description = `${measure.kicker}, ${win.from} to ${win.to}, ${pathInfo.label}, projected. Arrow keys move between places, Enter opens one, Escape goes back.`;

  // Going up a level removes the control that did it (the trail, "Up a level"), so the focus moves onto the map the
  // reader lands on rather than falling to the page.
  const focusMap = (...names: string[]) =>
    requestAnimationFrame(() => {
      for (const n of names) {
        const svg = document.querySelector<SVGSVGElement>(`svg[data-map="${n}"]`);
        if (svg) return svg.focus();
      }
    });
  const toWorld = () => {
    onChange({ c: null, r: null }, true);
    focusMap("world");
  };
  const toCountry = () => {
    onChange({ r: null }, true);
    focusMap("regions", "world");
  };
  const trail: { label: string; onClick: () => void }[] = [];
  if (state.country) trail.push({ label: "World", onClick: toWorld });
  if (state.region && countryPlace) trail.push({ label: countryPlace.name, onClick: toCountry });
  const up = state.region ? toCountry : state.country ? toWorld : null;

  // What the arrow keys moved to, said aloud (the map itself is one stop with a fixed name).
  const focusedPlace = known(focused);
  const focusedValue = focusedPlace ? headlineFor(readPayload, measure, focusedPlace, state.period, state.path) : null;
  const announce = focusedPlace
    ? `${focusedPlace.name}: ${focusedValue ? `${formatReadable(focusedValue.value, focusedValue.decimals)} ${measure.unitLabel}` : "no data"}`
    : "";

  const drills = (country.data && state.country && !state.region ? country.data.drills : [])
    .map((d) => ({ ...d, to: crossHref(d.to) ?? d.to }))
    .filter((d) => d.to.startsWith("/"));

  // One credit per producer and licence (every measure here comes from the same portal).
  const credit = (state.country && country.data ? country.data.credit : root.data!.credit).filter(
    (c, i, all) => all.findIndex((d) => d.producers === c.producers && d.licence === c.licence) === i,
  );
  const geoCredit = payload!.geoCredit;

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* The hatch that marks a place with no value, once for both maps and the legend. */}
      <svg width="0" height="0" aria-hidden className="absolute">
        <defs>
          <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--background)" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--muted-foreground)" strokeOpacity={0.45} strokeWidth="1.5" />
          </pattern>
        </defs>
      </svg>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,5fr)_auto_minmax(0,6fr)] gap-2 lg:grid-cols-[minmax(0,4fr)_minmax(0,9fr)] lg:grid-rows-[minmax(0,1fr)_auto] lg:gap-x-8">
        <div className="relative min-h-0 lg:col-start-2 lg:row-start-1">
          {world.data ? (
            <MapView
              topology={world.data as unknown as Topology}
              object="countries"
              disputedObject="disputed"
              centred={false}
              fill={fillFrom(rootPayload)}
              label={nameIn(rootPayload)}
              focused={focused}
              selected={state.country}
              onHover={(id) => !state.country && setHovered(id)}
              onSelect={(id, byKey) => {
                setOpenedByKey(byKey);
                onChange({ c: id, r: null }, true);
              }}
              onFocusPlace={setFocused}
              onEscape={() => up?.()}
              description={description}
              hatch={hatch}
              zoomTo={state.country}
              name="world"
              // Under a country's own map the world is a picture, not a second map to tab into.
              inert={Boolean(state.country && regions.data && countryPayload)}
            />
          ) : null}
          {state.country && regions.data && countryPayload ? (
            <motion.div
              key={state.country}
              className="absolute inset-0"
              initial={{ opacity: reduce ? 1 : 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: reduce ? 0 : 0.35, delay: reduce ? 0 : 0.3 }}
            >
              <MapView
                topology={regions.data as unknown as Topology}
                object="regions"
                disputedObject="disputed"
                centred
                fill={fillFrom(countryPayload)}
                label={(id) => (id.startsWith("V1:") ? `A World Bank shape with no region in the source (record ${id.slice(3)})` : nameIn(countryPayload)(id))}
                // A shape no region of the source matches is drawn (hatched, with its name on hover) but has nothing to
                // read: it is never hovered into the panel, focused or opened.
                readable={(id) => !id.startsWith("V1:")}
                focused={focused}
                selected={state.region}
                onHover={setHovered}
                onSelect={(id) => onChange({ r: id }, true)}
                onFocusPlace={setFocused}
                onEscape={() => up?.()}
                description={`${countryPlace?.name ?? ""}: ${description}`}
                hatch={hatch}
                name="regions"
                autoFocus={openedByKey}
              />
            </motion.div>
          ) : null}
        </div>
        <div className="lg:col-start-2 lg:row-start-2">
          <MapLegend measure={measure} scale={scale} hatch={hatch} />
        </div>
        <div className="min-h-0 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          {pending && !readPlace ? (
            <p className="text-sm text-muted-foreground" aria-busy>
              Loading…
            </p>
          ) : !readPlace ? (
            <section data-probe aria-label="No such place" className="flex flex-col gap-2 text-sm">
              {up ? (
                <button type="button" onClick={up} className="self-start text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground">
                  Up a level
                </button>
              ) : null}
              <p>
                No data for {chosen} in the World Bank&apos;s Climate Change Knowledge Portal.
              </p>
            </section>
          ) : (
            <FuturePanel
              payload={readPayload}
              place={readPlace}
              country={isRegion ? countryPlace : null}
              trail={trail}
              measureKey={measure.key}
              period={state.period}
              path={state.path}
              ranked={!state.country && !hovered && !focused && readPlace.entity === ranked?.place.entity ? (ranked.tied ? "tied" : "first") : null}
              drills={drills}
              onPeriod={(p) => onChange({ p: p.replace("/", "-") }, false)}
              onMeasure={(m) => onChange({ m }, true)}
              onUp={up}
              onPlace={(e) => onChange({ r: e }, true)}
            />
          )}
        </div>
      </div>
      <p data-probe className="text-[11px] leading-snug text-muted-foreground">
        {credit.length === 1 && credit[0].producers === geoCredit.producers && credit[0].licence === geoCredit.licence ? (
          <>
            Data and{" "}
            <Link href={`/sources/${geoCredit.source}`} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
              shapes
            </Link>
            :{" "}
            <Link href={dataPath(credit[0].indicator)} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
              {credit[0].producers}
            </Link>{" "}
            ({credit[0].licence}).
          </>
        ) : (
          <>
            Data:{" "}
            {credit.map((c, i) => (
              <Fragment key={c.indicator}>
                {i > 0 ? " · " : null}
                <Link href={dataPath(c.indicator)} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
                  {c.producers}
                </Link>{" "}
                ({c.licence})
              </Fragment>
            ))}
            {" · Shapes: "}
            <Link href={`/sources/${geoCredit.source}`} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
              {geoCredit.producers}
            </Link>{" "}
            ({geoCredit.licence}).
          </>
        )}{" "}
        Projections, not forecasts of any one year. Select any number for its source.
      </p>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announce}
      </p>
    </div>
  );
}

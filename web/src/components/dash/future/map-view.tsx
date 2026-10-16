"use client";

import { geoCentroid, geoEqualEarth, geoPath, type GeoPermissibleObjects } from "d3-geo";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import { feature, mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";

import { nextPlace, type Direction } from "@/lib/dash/spatial-nav";
import { cn } from "@/lib/utils";

import { useSize } from "../use-size";

/**
 * One map layer: the shapes of a topology object drawn at the container's size in an Equal Earth projection, each
 * filled by the colour its place's published value falls in (the caller decides the colour; a missing value is hatched,
 * a disputed area grey and dashed). A place too small to see is a dot with a finger-sized target. Borders are one mesh
 * of shared edges, so neighbours never draw a line twice and nothing traces a coastline.
 *
 * The world is fitted to every country but Antarctica (no residents, no values); a country's own map is rotated to its
 * centre first, so a country crossing the 180° line (Fiji, Russia) is drawn whole.
 *
 * A mouse reads a place by hovering and opens it with a click. A finger has no hover, so its first tap on a place reads
 * it and a second tap on the same place opens it.
 */
export type Shape = { id: string; d: string; x: number; y: number; area: number; disputed: boolean; name?: string };

type Props = {
  topology: Topology;
  object: string;
  /** Also draw this object's shapes (disputed areas) under the others, without values. */
  disputedObject?: string;
  /** Rotate to the shapes' centre before fitting (a country's own map). */
  centred: boolean;
  fill: (id: string) => string | null;
  label: (id: string) => string;
  focused: string | null;
  selected: string | null;
  onHover: (id: string | null) => void;
  /** A place opened: by the keyboard (Enter) or by a pointer. */
  onSelect: (id: string, byKey: boolean) => void;
  onFocusPlace: (id: string | null) => void;
  onEscape: () => void;
  /** Words for screen readers: what the map shows (measure, window, path). */
  description: string;
  /** Shapes shown faded (the rest of the world behind a country). */
  zoomTo?: string | null;
  /** Places with something to read; others are drawn but never hovered into the panel, focused or opened. */
  readable?: (id: string) => boolean;
  /** Names the map's svg (data-map), so the caller can move the focus back to it. */
  name: string;
  /** Covered by another map: drawn, but out of the tab order and deaf to the pointer. */
  inert?: boolean;
  /** Take the keyboard focus when drawn (a map opened from the keyboard). */
  autoFocus?: boolean;
  /** The id of the hatch pattern that marks a place with no value (defined once for the maps and the legend). */
  hatch: string;
};

const SKIP = new Set(["ATA"]);
const TINY = 12;

export function MapView(props: Props) {
  const { topology, object, disputedObject, centred, fill, label, focused, selected, onHover, onSelect, onFocusPlace, onEscape, description, zoomTo, name, inert, autoFocus, hatch } = props;
  const readable = props.readable ?? (() => true);
  const ownSvg = useRef<SVGSVGElement | null>(null);
  const reduce = useReducedMotion();
  const { ref, size } = useSize<HTMLDivElement>({ w: 120, h: 80 });
  // How the last press was made, and the place a first tap has read (written by handlers only, never drawn).
  const press = useRef<{ type: string; armed: string | null }>({ type: "mouse", armed: null });

  function choose(id: string) {
    if (!readable(id)) return;
    if (press.current.type === "touch" && press.current.armed !== id) {
      press.current.armed = id;
      onHover(id);
      return;
    }
    press.current.armed = null;
    onSelect(id, false);
  }

  const shapes = useMemo(() => {
    if (!size) return null;
    const fc = feature(topology, topology.objects[object] as GeometryCollection) as unknown as GeoJSON.FeatureCollection;
    const features = fc.features.filter((f) => !SKIP.has(String(f.id)));
    const disputedFc = disputedObject && topology.objects[disputedObject] ? (feature(topology, topology.objects[disputedObject] as GeometryCollection) as unknown as GeoJSON.FeatureCollection) : null;
    const projection = geoEqualEarth();
    if (centred) {
      const [lon] = geoCentroid({ type: "FeatureCollection", features } as GeoPermissibleObjects);
      projection.rotate([-lon, 0]);
    }
    const pad = 6;
    projection.fitExtent(
      [
        [pad, pad],
        [size.w - pad, size.h - pad],
      ],
      { type: "FeatureCollection", features } as GeoPermissibleObjects,
    );
    const path = geoPath(projection);
    const toShape = (f: GeoJSON.Feature, disputed: boolean): Shape => {
      const id = String(f.id ?? (f.properties as { name?: string } | null)?.name ?? "");
      const rp = (f.properties as { rp?: [number, number] } | null)?.rp;
      const [x, y] = rp ? (projection(rp) ?? path.centroid(f)) : path.centroid(f);
      return { id, d: path(f) ?? "", x, y, area: path.area(f), disputed, name: (f.properties as { name?: string } | null)?.name };
    };
    const borders = path(mesh(topology, topology.objects[object] as GeometryCollection, (a, b) => a !== b)) ?? "";
    return {
      places: features.map((f) => toShape(f, false)),
      disputed: disputedFc ? disputedFc.features.map((f) => toShape(f, true)) : [],
      borders,
    };
  }, [topology, object, disputedObject, centred, size]);

  const zoom = useMemo(() => {
    if (!shapes || !zoomTo || !size) return { x: 0, y: 0, scale: 1 };
    const s = shapes.places.find((p) => p.id === zoomTo);
    if (!s) return { x: 0, y: 0, scale: 1 };
    // Zoom the world on the chosen country's centre, enough to fill the box with it, never past 8 times.
    const scale = Math.min(8, Math.max(1.5, Math.sqrt((size.w * size.h) / Math.max(1, s.area)) * 0.35));
    return { x: size.w / 2 - s.x * scale, y: size.h / 2 - s.y * scale, scale };
  }, [shapes, zoomTo, size]);

  function onKeyDown(e: React.KeyboardEvent) {
    const dirs: Record<string, Direction> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
    if (dirs[e.key] && shapes) {
      e.preventDefault();
      // Travel starts from the place in focus, or else from the open one, so the keys leave it for its neighbours.
      const points = shapes.places.filter((p) => readable(p.id)).map((p) => ({ id: p.id, x: p.x, y: p.y }));
      onFocusPlace(nextPlace(points, focused ?? selected, dirs[e.key]));
    } else if (e.key === "Enter" && focused) {
      e.preventDefault();
      onSelect(focused, true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onEscape();
    }
  }

  // A map opened from the keyboard takes the focus, so the arrow keys go on working on it.
  const drawn = Boolean(shapes && size);
  useEffect(() => {
    if (autoFocus && drawn) ownSvg.current?.focus();
  }, [autoFocus, drawn]);

  const highlight = shapes?.places.find((p) => p.id === (focused ?? selected));

  return (
    // Covered by a country's own map, the world fades out entirely: two maps of one country at two scales never show.
    <div ref={ref} className={cn("relative h-full min-h-0 w-full motion-safe:transition-opacity motion-safe:duration-500", inert && "opacity-0")} inert={inert}>
      {shapes && size ? (
        <svg
          width={size.w}
          height={size.h}
          role="group"
          ref={ownSvg}
          data-map={name}
          tabIndex={0}
          aria-label={description}
          onKeyDown={onKeyDown}
          onBlur={() => onFocusPlace(null)}
          onPointerDown={(e) => {
            press.current.type = e.pointerType;
          }}
          onPointerLeave={(e) => e.pointerType !== "touch" && onHover(null)}
          className="block touch-manipulation outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {/* The zoom is worked out in the svg's own coordinates, so it scales from the svg's corner (motion would
              otherwise scale an svg group from its own box). */}
          <motion.g
            initial={false}
            animate={{ x: zoom.x, y: zoom.y, scale: zoom.scale }}
            transition={{ duration: reduce ? 0 : 0.45, ease: [0.22, 1, 0.36, 1] }}
            style={{ originX: 0, originY: 0, transformBox: "view-box" }}
          >
            {shapes.disputed.map((s) => (
              <path key={`disputed-${s.id}`} opacity={zoomTo ? 0.18 : 1} d={s.d} fill="var(--muted)" stroke="var(--muted-foreground)" strokeOpacity={0.6} strokeDasharray="2 2" strokeWidth={0.75} vectorEffect="non-scaling-stroke">
                <title>{`${s.name ?? s.id}: disputed area (World Bank), not coloured`}</title>
              </path>
            ))}
            {shapes.places.map((s) => {
              const f = fill(s.id);
              const tiny = s.area < TINY;
              return (
                <g
                  key={s.id}
                  data-id={s.id}
                  onPointerEnter={(e) => e.pointerType !== "touch" && onHover(readable(s.id) ? s.id : null)}
                  onClick={() => choose(s.id)}
                  // Zoomed to a country, the rest of the world fades behind it; the country itself stays as it is.
                  opacity={zoomTo && s.id !== zoomTo ? 0.18 : 1}
                  className="cursor-pointer motion-safe:transition-opacity motion-safe:duration-500"
                >
                  {/* A light edge round every place, so a place at the bottom of the ramp (near white) still shows its
                      coast; the shared borders are drawn again in the background colour on top. */}
                  <path d={s.d} fill={f ?? `url(#${hatch})`} stroke="var(--border)" strokeWidth={0.6} vectorEffect="non-scaling-stroke" className="motion-safe:transition-[fill] motion-safe:duration-500">
                    <title>{label(s.id)}</title>
                  </path>
                  {tiny ? (
                    <>
                      <circle cx={s.x} cy={s.y} r={2.5} fill={f ?? "var(--muted-foreground)"} stroke="var(--background)" strokeWidth={0.75} vectorEffect="non-scaling-stroke" />
                      <circle cx={s.x} cy={s.y} r={10} fill="transparent" />
                    </>
                  ) : null}
                </g>
              );
            })}
            <path d={shapes.borders} fill="none" stroke="var(--background)" strokeWidth={0.6} vectorEffect="non-scaling-stroke" pointerEvents="none" />
            {highlight ? (
              <path d={highlight.d} fill="none" stroke="var(--foreground)" strokeWidth={1.75} vectorEffect="non-scaling-stroke" pointerEvents="none" />
            ) : null}
          </motion.g>
        </svg>
      ) : null}
    </div>
  );
}

import { interpolateRgbBasis } from "d3-interpolate";
import { scaleLinear, scaleSqrt } from "d3-scale";

import type { FutureMeasure } from "@/lib/dash/types";

/**
 * Map colours are presentation, not data: a measure's published values are placed on one continuous ramp between the
 * smallest and largest published value over every place, window and path (both chosen from the data, never typed), so
 * a colour means the same everywhere and a map that darkens from one window to the next has really changed. Counts of
 * days spread on a square-root scale from zero, where most places have few; temperatures spread linearly.
 */

const RAMPS: Record<FutureMeasure["ramp"], string[]> = {
  // The warm half of the site's red-blue scale (the stripes), from pale to darkest red.
  warm: ["#fff5f0", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"],
  // The blue half: wetter is darker.
  wet: ["#f7fbff", "#d1e5f0", "#92c5de", "#4393c3", "#2166ac", "#053061"],
  // Brown for dry spells: longer is darker.
  dry: ["#fdf6e3", "#f6e8c3", "#dfc27d", "#bf812d", "#8c510a", "#543005"],
};

export type ColourScale = {
  /** Where a value sits along the ramp, 0 to 1. */
  position: (v: number) => number;
  colour: (v: number) => string;
  /** Readable values to label the legend with, inside the range. */
  ticks: number[];
  /** The ramp's stops, for drawing the legend's gradient. */
  stops: string[];
  min: number;
  max: number;
};

export function scaleFor(measure: Pick<FutureMeasure, "ramp" | "spread" | "min" | "max">): ColourScale {
  const { min, max } = measure;
  const scale = (measure.spread === "sqrt" ? scaleSqrt() : scaleLinear()).domain([min, max]).range([0, 1]).clamp(true);
  const ramp = interpolateRgbBasis(RAMPS[measure.ramp]);
  const position = (v: number) => (max === min ? 1 : scale(v));
  return {
    position,
    colour: (v) => ramp(position(v)),
    ticks: scaleLinear().domain([min, max]).ticks(4),
    stops: RAMPS[measure.ramp],
    min,
    max,
  };
}

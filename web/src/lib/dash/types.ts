/**
 * The dashboard's view model: a drill-down tree where each node is one idea shown as one chart and one big number,
 * and each child is exactly one further disaggregation. Nodes are built at build time from data/ (lib/dash/*-tree.ts)
 * and served as small static JSON files (/dash-data/<chapter>/<node>.json), so the browser never computes a
 * published number: it only animates between nodes.
 */

/** A traced headline number: everything <a data-indicator> needs, so the Trace panel works on it. */
export type Headline = {
  indicator: string;
  entity: string;
  period: string;
  value: number;
  decimals: number;
  unit: string;
  unitLabel: string;
  status: "final" | "preliminary" | "projection";
  /** The dimension slice the value was read from (absent when the indicator has none), so a copy can be matched. */
  dims?: Record<string, string>;
  /** That slice in the data's own words ("SSP2-4.5, middle emissions"), so the Trace panel can say which it is. */
  sliceLabel?: string;
};

export type SeriesPoint = [year: number, value: number | null];

export type Series = {
  key: string;
  label: string;
  colour: string;
  points: SeriesPoint[];
  /** Node id to open when this series is selected (one more disaggregation). */
  drill?: string;
};

/**
 * One ranked bar. `inner` draws a second published value inside the bar (e.g. today's impact inside the achievable
 * one), named in the chart's legend. Bars are as long as the size of the value, so a cut (negative) reads as a bar;
 * the number shown keeps its sign.
 */
export type Bar = { key: string; label: string; value: number; colour: string; inner?: number; drill?: string };

export type Chart =
  | { kind: "area"; stacked: boolean; series: Series[]; unit: string; decimals: number; from: number; to: number }
  | { kind: "line"; series: Series[]; unit: string; decimals: number; from: number; to: number }
  | { kind: "bars"; bars: Bar[]; unit: string; decimals: number; period: string; note: string; legend?: { label: string; colour: string }[] };

/** A thumbnail of a node's chart, small enough to ship with its parent: the shape of where a choice leads. */
export type Preview =
  | { kind: "lines"; stacked: boolean; series: { colour: string; points: SeriesPoint[] }[] }
  | { kind: "bars"; bars: { key: string; value: number; colour: string }[] };

/**
 * How a consequence relates to the measurement it follows, shown over its "so what" card (docs/style.md): caused by
 * the warming (the producer attributes it), heat of any cause, a harm of the burning itself, or people at risk.
 */
export type Relation = "caused" | "linked" | "burning" | "exposed";

export type Drill = {
  label: string;
  to: string;
  /** Filled by the chapter from the target node: its crumb, its idea and the shape of its chart. */
  crumb?: string;
  kicker?: string;
  preview?: Preview;
  /**
   * What this measurement means for people: the target node's own traced headline, copied when the node is resolved
   * (lib/dash/chapters.ts), never computed. At most one per node, shown first.
   */
  soWhat?: { relation: Relation; headline?: Headline };
};

/** One data credit: the producers and licence in short, linking to the data page that carries the full attribution. */
export type Credit = { indicator: string; producers: string; licence: string; attribution: string };

export type DrillNode = {
  id: string;
  parent: string | null;
  /** Short label for the breadcrumb, e.g. "By fuel", "Coal", "China". */
  crumb: string;
  /** Ancestors from the root, for the breadcrumb (filled by the tree, so a deep link shows its path). */
  trail: { id: string; crumb: string }[];
  /** The idea in a few words, shown above the number. */
  kicker: string;
  headline: Headline;
  /** One short line after the number (no numbers in it: the only number is the traced headline). */
  sentence: string;
  chart: Chart;
  /** The next disaggregations, one per button. */
  drills: Drill[];
  /** The data shown, credited in short; each links to its data page, which carries the licence's full attribution. */
  credit: Credit[];
  /** Indicator ids shown on this node, for the source link. */
  indicators: string[];
  /** A future-mode view (the home's world map and each country's map): every value the reader can choose between. */
  future?: FuturePayload;
};

/** A 20-year projection window, as the data names it ("2040/2059") and as the URL and the dial name it ("2040-2059"). */
export type FuturePeriod = { id: string; period: string; from: number; to: number };

/** An emissions path, labelled from the data (e.g. "SSP2-4.5, middle emissions"); `tier` chooses the sketch of its emissions on the path picker. */
export type FuturePath = { id: string; tier: "low" | "middle" | "very-high"; label: string };

/**
 * One measure a reader can colour the map by: its country and region indicators (each value traces to one of them),
 * the words and unit from the data, and the largest published value over every place, window and path, so a colour means
 * the same everywhere and a darker map between windows is a real change.
 */
export type FutureMeasure = {
  key: string;
  countries: string;
  regions: string;
  kicker: string;
  unit: string;
  unitLabel: string;
  decimals: number;
  ramp: "warm" | "wet" | "dry";
  /**
   * How colours spread over the values: a count of days from zero on a square-root scale (so a few days and a few dozen
   * look different where most places have few), a temperature linearly between the smallest and largest value.
   */
  spread: "sqrt" | "linear";
  /** The smallest and largest published median over every place, window and path (chosen, not computed). */
  min: number;
  max: number;
  /** The model simulation of the baseline window exists for this measure (warming is itself a change from it). */
  baseline: boolean;
};

export type FuturePlace = { entity: string; name: string; kind: "country" | "territory" | "region"; onMap: boolean };

/** A published median with its model range (10th and 90th percentiles), or null where the source has no value. */
export type FutureCell = [value: number, lower: number | null, upper: number | null] | null;

export type FuturePayload = {
  level: "world" | "country";
  /** The country this view is about (null for the world). */
  place: string | null;
  periods: FuturePeriod[];
  paths: FuturePath[];
  measures: FutureMeasure[];
  /** The model simulation of the past every window is compared with ("1995/2014"), and its scenario id. */
  baseline: { period: string; scenario: string; label: string };
  /** Which statistic of the climate models each of a cell's values is, in the indicator's own words ("median", and the
   * percentiles its range runs between, "10th" and "90th"). */
  statistics: { value: string; lower: string; upper: string };
  places: FuturePlace[];
  /** measure key -> "<period>|<scenario>" -> one cell per entry of `places`, in the same order. */
  values: Record<string, Record<string, FutureCell[]>>;
  /** The shapes for this view (a path under /data/v1/geo/), or null when there is no map for it. */
  geo: string | null;
  /** Regions with values but no shape on the map: listed beside it, never guessed onto one. */
  unmatched: string[];
  /** The shapes' producer and licence, crediting the source page (shapes are not an indicator). */
  geoCredit: { source: string; producers: string; licence: string; attribution: string };
};

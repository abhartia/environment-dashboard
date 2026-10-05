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

export type Bar = { key: string; label: string; value: number; colour: string; drill?: string };

export type Chart =
  | { kind: "area"; stacked: boolean; series: Series[]; unit: string; decimals: number; from: number; to: number }
  | { kind: "line"; series: Series[]; unit: string; decimals: number; from: number; to: number }
  | { kind: "bars"; bars: Bar[]; unit: string; decimals: number; period: string; note: string; legend?: { label: string; colour: string }[] };

/** A thumbnail of a node's chart, small enough to ship with its parent: the shape of where a choice leads. */
export type Preview =
  | { kind: "lines"; stacked: boolean; series: { colour: string; points: SeriesPoint[] }[] }
  | { kind: "bars"; bars: { key: string; value: number; colour: string }[] };

export type Drill = {
  label: string;
  to: string;
  /** Filled by the chapter from the target node: its crumb, its idea and the shape of its chart. */
  crumb?: string;
  kicker?: string;
  preview?: Preview;
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
};

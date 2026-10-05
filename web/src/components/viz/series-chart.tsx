import { formatValue } from "@/lib/format";
import { linePath, linear, r1 } from "@/lib/viz/scale";

export type Point = { x: number; y: number | null; lo?: number | null; hi?: number | null };
export type Series = { key: string; label: string; points: Point[] };

const W = 720;
const H = 320;
const M = { top: 16, right: 16, bottom: 32, left: 56 };
const COLOURS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

/**
 * A server-rendered line chart (no client JavaScript): one line per series, an uncertainty band where the data has
 * one, round-number ticks. Decorative to assistive tech; the figure's caption and table carry its content.
 */
export function SeriesChart({
  series,
  decimals,
  unit,
  yZero = false,
}: {
  series: Series[];
  decimals: number;
  unit: string;
  /** Start the y axis at zero (for quantities, not anomalies). */
  yZero?: boolean;
}) {
  const all = series.flatMap((s) => s.points);
  const ys = all.flatMap((p) => [p.y, p.lo, p.hi]).filter((v): v is number => typeof v === "number");
  const xs = all.map((p) => p.x);
  if (ys.length === 0) throw new Error("SeriesChart: no values to draw");
  const [xMin, xMax] = [Math.min(...xs), Math.max(...xs)];
  let [yMin, yMax] = [Math.min(...ys), Math.max(...ys)];
  if (yZero) yMin = Math.min(0, yMin);
  const pad = (yMax - yMin) * 0.06 || Math.abs(yMax) * 0.1 || 1;
  if (!yZero) yMin -= pad;
  yMax += pad;
  const x = linear([xMin, xMax], [M.left, W - M.right]);
  const y = linear([yMin, yMax], [H - M.bottom, M.top]);
  const yTicks = y.ticks(5);
  const xTicks = x.ticks(xMax - xMin > 60 ? 6 : 8).filter((t) => Number.isInteger(t));
  const tickDecimals = Math.max(0, Math.min(decimals, -Math.floor(Math.log10(Math.abs(yTicks[1] - yTicks[0] || 1)))));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" aria-hidden="true" focusable="false">
      {yTicks.map((t) => (
        <g key={`y${t}`}>
          <line x1={M.left} x2={W - M.right} y1={r1(y(t))} y2={r1(y(t))} stroke="var(--grid)" strokeWidth={1} />
          <text x={M.left - 8} y={r1(y(t))} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[11px] num">
            {formatValue(t, tickDecimals)}
          </text>
        </g>
      ))}
      {yMin < 0 && yMax > 0 ? (
        <line x1={M.left} x2={W - M.right} y1={r1(y(0))} y2={r1(y(0))} stroke="var(--muted-foreground)" strokeWidth={1} />
      ) : null}
      {xTicks.map((t) => (
        <text key={`x${t}`} x={r1(x(t))} y={H - 10} textAnchor="middle" className="fill-muted-foreground text-[11px] num">
          {t}
        </text>
      ))}
      <text x={M.left} y={10} className="fill-muted-foreground text-[11px]">
        {unit}
      </text>
      {series.map((s, i) => {
        const colour = COLOURS[i % COLOURS.length];
        const band = s.points.filter((p) => typeof p.lo === "number" && typeof p.hi === "number");
        const bandPath =
          band.length > 1
            ? `M${band.map((p) => `${r1(x(p.x))} ${r1(y(p.hi as number))}`).join("L")}L${[...band]
                .reverse()
                .map((p) => `${r1(x(p.x))} ${r1(y(p.lo as number))}`)
                .join("L")}Z`
            : null;
        return (
          <g key={s.key}>
            {bandPath ? <path d={bandPath} fill={colour} opacity={0.15} /> : null}
            <path
              d={linePath(s.points.map((p) => (p.y === null ? null : ([x(p.x), y(p.y)] as const))))}
              fill="none"
              stroke={colour}
              strokeWidth={series.length > 1 ? 1.75 : 2}
              strokeLinejoin="round"
            />
          </g>
        );
      })}
    </svg>
  );
}

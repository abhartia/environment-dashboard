"use client";

import { motion, useReducedMotion } from "motion/react";

import type { Chart } from "@/lib/dash/types";
import { formatReadable } from "@/lib/format";

type BarsSpec = Extract<Chart, { kind: "bars" }>;

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Ranked horizontal bars that share out the height they are given (the dashboard never scrolls). Bars are keyed by
 * entity, so moving between two rankings of the same places (totals and per person) slides each bar to its new rank
 * and length. A bar with somewhere to go is a button.
 */
export function BarChart({ chart, onSelect, onPeek }: { chart: BarsSpec; onSelect: (id: string) => void; onPeek: (id: string) => void }) {
  const reduce = useReducedMotion();
  const max = Math.max(...chart.bars.map((b) => Math.abs(b.value)));
  const duration = reduce ? 0 : 0.8;
  return (
    <figure className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-1 text-xs font-medium text-muted-foreground">
        {chart.legend?.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm" style={{ background: l.colour }} />
            {l.label}
          </span>
        ))}
        <span className="ml-auto">{chart.unit}</span>
      </div>
      <ol className="grid min-h-0 flex-1 auto-rows-fr">
        {chart.bars.map((b, i) => {
          const value = formatReadable(b.value, Math.abs(b.value) >= 1000 ? 0 : chart.decimals);
          const inner = (
            <>
              <span className="line-clamp-2 w-24 shrink-0 text-left text-xs leading-tight font-semibold sm:w-44 sm:text-sm" title={b.label}>
                {b.label}
              </span>
              <span className="relative h-[70%] max-h-8 min-h-2 flex-1">
                <motion.span
                  className="absolute inset-y-0 left-0 rounded-[3px]"
                  style={{ background: b.colour, opacity: b.inner === undefined ? 1 : 0.35 }}
                  initial={{ width: "0%" }}
                  animate={{ width: `${(Math.abs(b.value) / max) * 100}%` }}
                  transition={{ duration, ease: EASE, delay: reduce ? 0 : i * 0.03 }}
                />
                {b.inner !== undefined ? (
                  <motion.span
                    className="absolute inset-y-0 left-0 rounded-[3px]"
                    style={{ background: b.colour }}
                    initial={{ width: "0%" }}
                    animate={{ width: `${(Math.abs(b.inner) / max) * 100}%` }}
                    transition={{ duration, ease: EASE, delay: reduce ? 0 : 0.3 + i * 0.03 }}
                  />
                ) : null}
              </span>
              <span className="w-14 shrink-0 text-right text-xs font-semibold num sm:w-16 sm:text-sm">{value}</span>
            </>
          );
          return (
            <motion.li key={b.key} layout={!reduce} transition={{ duration, ease: EASE }} className="min-h-0">
              {b.drill ? (
                <button
                  type="button"
                  onPointerEnter={() => onPeek(b.drill!)}
                  onFocus={() => onPeek(b.drill!)}
                  onClick={() => onSelect(b.drill!)}
                  aria-label={`${b.label}, ${value} ${chart.unit}: open`}
                  className="flex h-full w-full items-center gap-2 rounded-md px-1.5 hover:bg-accent focus-visible:bg-accent focus-visible:outline-2 sm:gap-3"
                >
                  {inner}
                </button>
              ) : (
                <div className="flex h-full items-center gap-2 px-1.5 sm:gap-3">{inner}</div>
              )}
            </motion.li>
          );
        })}
      </ol>
      <figcaption className="pt-1 text-xs text-muted-foreground">{chart.note}</figcaption>
    </figure>
  );
}

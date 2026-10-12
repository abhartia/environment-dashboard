"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect, useLayoutEffect } from "react";

import type { Headline } from "@/lib/dash/types";
import { formatReadable, readable } from "@/lib/format";
import { dataPath } from "@/lib/routes";
import { cn } from "@/lib/utils";

/**
 * The node's one big number, as a traced link (the page's Trace listener opens its source panel; without JavaScript
 * it is a link to the number's data page). When the reader drills, it counts from the old value to the new one; the
 * number it settles on is the published value, formatted by the same formatter as everywhere else. With `from`, it
 * counts up from that value once, `delay` seconds after it appears (the page itself still renders the published value).
 * `suffix` is a short unit set beside the number ("deaths", "×") where the unit in words has no room; the link's label
 * always carries the unit in words.
 */
export function TracedValue({
  h,
  className,
  from,
  delay = 0,
  statusClassName = "text-sm text-muted-foreground",
  suffix,
}: {
  h: Headline;
  className?: string;
  from?: number;
  delay?: number;
  statusClassName?: string;
  suffix?: string;
}) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(h.value);
  // Millions and billions read as words; the word follows the target value so it never flips mid-count.
  const word = readable(h.value, h.decimals).word;
  const text = useTransform(mv, (v) => readable(v, h.decimals, h.value).number);

  // Before the first paint (client only), so the server's published value never flashes before a count-up.
  useLayoutEffect(() => {
    if (from !== undefined && !reduce) mv.set(from);
  }, [from, mv, reduce]);

  useEffect(() => {
    if (reduce) {
      mv.set(h.value);
      return;
    }
    const controls = animate(mv, h.value, { duration: 0.9, ease: [0.22, 1, 0.36, 1], delay });
    return () => controls.stop();
  }, [h.value, mv, reduce, delay]);

  const status = h.status === "final" ? null : h.status === "projection" ? "projected" : "preliminary";
  return (
    <a
      href={dataPath(h.indicator, h.period)}
      data-indicator={h.indicator}
      data-period={h.period}
      data-entity={h.entity}
      aria-label={`${formatReadable(h.value, h.decimals)} ${h.unitLabel}${status ? ` (${status})` : ""}, show source`}
      aria-haspopup="dialog"
      className={cn("group inline-flex items-baseline gap-3 no-underline outline-none", className)}
    >
      <motion.span className="num decoration-[0.06em] underline-offset-[0.12em] group-hover:underline group-focus-visible:underline">{text}</motion.span>
      {word ? <span className="text-[0.4em] font-bold tracking-tight">{word}</span> : null}
      {suffix ? <span className="text-[0.4em] font-bold tracking-tight">{suffix}</span> : null}
      {status ? <span className={cn("font-semibold tracking-wide uppercase", statusClassName)}>{status}</span> : null}
    </a>
  );
}

"use client";

import { RadioGroup } from "radix-ui";

import type { FuturePath } from "@/lib/dash/types";

/**
 * A rough sketch of each path's carbon dioxide emissions over the century (IPCC AR6 WGI, Figure SPM.4): the low path
 * falls, the middle one stays near today's level and then eases, the very high one keeps rising. Decorative: each
 * button's name is the path's own label from the data.
 */
const CURVE: Record<FuturePath["tier"], string> = {
  low: "M2 5 C8 6, 14 11, 22 13",
  middle: "M2 5 C9 5, 15 5, 22 8",
  "very-high": "M2 7 C9 6, 15 3, 22 1",
};

/**
 * The emissions path the map shows, as three small shapes (no words to read before choosing): low, middle and very high
 * emissions. A radio group (Radix): the arrow keys move between them and choose; each says its full name from the data
 * when focused or hovered, and the panel names the chosen one in words.
 */
export function PathPicker({ paths, value, onChange }: { paths: FuturePath[]; value: string; onChange: (path: string) => void }) {
  return (
    <RadioGroup.Root aria-label="Emissions path" orientation="horizontal" loop value={value} onValueChange={onChange} className="flex items-center gap-1">
      {paths.map((p) => (
        <RadioGroup.Item
          key={p.id}
          value={p.id}
          aria-label={p.label}
          title={p.label}
          data-path={p.id}
          // Selection follows the keyboard's focus (the radio pattern). Radix checks an item only while the arrow key is
          // still held when its delayed focus lands, which a quick press misses.
          onFocus={(e) => {
            if (e.currentTarget.matches(":focus-visible") && p.id !== value) onChange(p.id);
          }}
          className="group grid h-7 w-8 place-items-center rounded-md border border-transparent text-muted-foreground transition-colors outline-none hover:border-border hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:border-foreground data-[state=checked]:text-foreground"
        >
          <svg viewBox="0 0 24 14" className="h-3.5 w-6" aria-hidden>
            <path d={CURVE[p.tier]} fill="none" stroke="currentColor" strokeLinecap="round" className="stroke-[1.75] group-data-[state=checked]:stroke-[2.25]" />
          </svg>
        </RadioGroup.Item>
      ))}
    </RadioGroup.Root>
  );
}

"use client";

import { Earth, History } from "lucide-react";

/**
 * Between the story so far and what's coming: one round icon beside replay, the same size and weight. It is a link (the
 * mode lives in the URL, so either view can be shared and opened in a new tab); a plain click switches in place.
 */
export function ModeSwitch({ mode, href, onSwitch }: { mode: "past" | "future"; href: string; onSwitch: () => void }) {
  const toFuture = mode === "past";
  const label = toFuture ? "Show the future: what's coming, place by place" : "Show the story so far, 1850 to today";
  return (
    <a
      href={href}
      aria-label={label}
      title={label}
      onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        onSwitch();
      }}
      className="grid size-8 place-items-center rounded-full border border-border text-muted-foreground hover:border-foreground hover:text-foreground focus-visible:outline-2"
    >
      {toFuture ? <Earth aria-hidden className="size-4" /> : <History aria-hidden className="size-4" />}
    </a>
  );
}

"use client";

import { animate, useMotionValue, useMotionValueEvent, useReducedMotion, type MotionValue } from "motion/react";
import { useEffect, useRef, useState } from "react";

const SWEEP_SECONDS = 7;
const EASE_SWEEP = [0.45, 0, 0.25, 1] as const;
/** The landing beat: bands settle into ink one after another, this far apart. */
export const STAGGER_MS = 80;

export type Sweep = {
  cursor: MotionValue<number>;
  /** The cursor's position, mirrored into React state for the numbers that read it. */
  t: number;
  /** At (or past) today: every number shows its latest published value. */
  atRest: boolean;
  /** The bands are in ink (the sweep has landed, or the reader is moving through time); muted while it travels. */
  landed: boolean;
  /** The one staggered settling of the bands, just after the sweep lands. */
  beat: boolean;
  play: () => void;
  scrub: (e: React.PointerEvent<HTMLElement>) => void;
  rest: () => void;
  leave: () => void;
  settle: (e: React.FocusEvent<HTMLElement>) => void;
  /** Stop the sweep where it is (another animation takes the cursor on). */
  stop: () => void;
};

/**
 * The story's clock: a cursor that sweeps from `from` to `to` on arrival (unless `autoplay` is off or motion is
 * reduced), that the reader can scrub, and that rests on today. `onLanded` fires when an arrival or replay sweep reaches
 * today; `onInteract` fires when the reader takes the clock (scrubbing, keyboard focus), so whatever was waiting on the
 * sweep can stand down.
 */
export function useStorySweep({
  from,
  to,
  bands,
  autoplay,
  onLanded,
  onInteract,
}: {
  from: number;
  to: number;
  bands: number;
  autoplay: boolean;
  onLanded?: () => void;
  onInteract?: () => void;
}): Sweep {
  const reduce = useReducedMotion();
  const cursor = useMotionValue(to);
  const [t, setT] = useState(to);
  const [landed, setLanded] = useState(true);
  const [beat, setBeat] = useState(false);
  const sweep = useRef<ReturnType<typeof animate> | null>(null);
  const restTimer = useRef<number | null>(null);
  const beatTimer = useRef<number | null>(null);
  // The latest callbacks, read when the animation completes (not the ones captured when it started).
  const landedRef = useRef(onLanded);
  const interactRef = useRef(onInteract);
  useEffect(() => {
    landedRef.current = onLanded;
    interactRef.current = onInteract;
  });
  useMotionValueEvent(cursor, "change", (v) => setT(v));

  function clearRest() {
    if (restTimer.current !== null) {
      window.clearTimeout(restTimer.current);
      restTimer.current = null;
    }
  }

  function run(delay: number) {
    sweep.current?.stop();
    cursor.set(from);
    let started = false;
    sweep.current = animate(cursor, to, {
      duration: SWEEP_SECONDS,
      ease: EASE_SWEEP,
      delay,
      onUpdate: () => {
        if (started) return;
        started = true;
        setLanded(false);
      },
      onComplete: () => {
        setLanded(true);
        setBeat(true);
        if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
        beatTimer.current = window.setTimeout(() => setBeat(false), bands * STAGGER_MS + 300);
        landedRef.current?.();
      },
    });
  }

  function play() {
    if (reduce) {
      sweep.current?.stop();
      cursor.set(to);
      setLanded(true);
      return;
    }
    run(0);
  }

  // Whether the arrival sweep has had its chance. Written by the effect only, never drawn.
  const arrived = useRef(false);
  useEffect(() => {
    if (reduce || !autoplay) return;
    if (arrived.current) {
      // Back to the story later (the switch, or the back button): it rests on today rather than sweeping again.
      sweep.current?.stop();
      cursor.set(to);
      setLanded(true);
      return;
    }
    arrived.current = true;
    run(0.4);
    return () => {
      sweep.current?.stop();
      if (restTimer.current !== null) window.clearTimeout(restTimer.current);
      if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    };
    // The sweep runs once on arrival; replays go through play().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursor, from, to, reduce, autoplay]);

  function scrub(e: React.PointerEvent<HTMLElement>) {
    clearRest();
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    sweep.current?.stop();
    setLanded(true);
    interactRef.current?.();
    cursor.set(from + frac * (to - from));
  }

  function rest() {
    clearRest();
    sweep.current?.stop();
    setLanded(true);
    sweep.current = animate(cursor, to, { duration: reduce ? 0 : 0.8, ease: [0.22, 1, 0.36, 1] });
  }

  /** Leaving one chart for the next is not leaving the story: rest only if no chart is entered again soon. */
  function leave() {
    restTimer.current = window.setTimeout(rest, 120);
  }

  const atRest = t >= to - 1e-6;

  /**
   * Keyboard focus ends the sweep at once, so every number and band is there to read and reach. It reads the live
   * cursor, not the last render: a carry-on roll past today is stopped by onInteract and brought back to today too.
   */
  function settle(e: React.FocusEvent<HTMLElement>) {
    if (!(e.target as HTMLElement).matches(":focus-visible")) return;
    interactRef.current?.();
    if (cursor.get() === to) return;
    clearRest();
    sweep.current?.stop();
    cursor.set(to);
    setLanded(true);
  }

  function stop() {
    clearRest();
    sweep.current?.stop();
  }

  return { cursor, t, atRest, landed, beat, play, scrub, rest, leave, settle, stop };
}

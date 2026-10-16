"use client";

import { RotateCcw } from "lucide-react";
import { animate, motion, useReducedMotion, useTransform } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";

import { QueryProvider } from "@/components/query-provider";
import { parseFuture, periodId, type FutureFrame } from "@/lib/dash/future-select";
import type { StoryRow } from "@/lib/dash/story";
import { setSearch, useSearch } from "@/lib/dash/url-state";

import { PathPicker } from "./future/path-picker";
import { PeriodDial } from "./future/period-dial";
import { ModeSwitch } from "./mode-switch";
import { useStorySweep } from "./story-sweep";
import { StoryTimeline } from "./story-timeline";

const FutureMap = dynamic(() => import("./future/future-map").then((m) => m.FutureMap), { ssr: false });

/** How long the story rests on today before it carries on into the future, and how long the year takes to roll on. */
const HOLD_MS = 2500;
const ROLL_SECONDS = 1.4;

/**
 * The home page on one screen: the header (what this is, the switch between the story so far and the future, replay,
 * and the year or window the view reads) over either the climate story from 1850 to today or the map of what's coming.
 * The canvas owns the story's clock, so on arrival the same cursor sweeps to today, rests, and then rolls on into the
 * first window of the future, where the map takes over. Any move by the reader (scrubbing, focusing, choosing a mode)
 * stops that carry-on; reduced motion never starts it. The mode and every choice on the map live in the URL.
 */
export function HomeCanvas({ rows, from, to, frame }: { rows: StoryRow[]; from: number; to: number; frame?: FutureFrame }) {
  const reduce = useReducedMotion();
  const search = useSearch();
  const state = frame ? parseFuture(search, frame) : null;
  // Whether the story should carry on into the future when it lands: only on a plain arrival (no mode in the URL), and
  // only until the reader does anything. Read by timers and animations, never drawn, so it is a ref.
  const carryOn = useRef(frame !== undefined);
  const hold = useRef<number | null>(null);
  const roll = useRef<ReturnType<typeof animate> | null>(null);
  const future = state?.mode === "future";

  const sweep = useStorySweep({
    from,
    to,
    bands: rows.filter((r) => r.band).length,
    autoplay: !future,
    onLanded: () => startHold(),
    onInteract: () => cancelCarryOn(),
  });

  function cancelCarryOn() {
    carryOn.current = false;
    if (hold.current !== null) window.clearTimeout(hold.current);
    hold.current = null;
    roll.current?.stop();
  }

  function startHold() {
    if (!frame || !carryOn.current || reduce) return;
    if (new URLSearchParams(window.location.search).get("mode")) return;
    const first = frame.periods.find((p) => p.period === frame.defaults.period)!;
    const go = () => {
      if (document.visibilityState !== "visible") {
        hold.current = window.setTimeout(go, 500);
        return;
      }
      roll.current = animate(sweep.cursor, first.from, {
        duration: ROLL_SECONDS,
        ease: [0.45, 0, 0.25, 1],
        onComplete: () => {
          if (!carryOn.current) return;
          setSearch({ mode: "future", p: periodId(frame.defaults.period), s: frame.defaults.path }, false);
        },
      });
    };
    hold.current = window.setTimeout(go, HOLD_MS);
  }

  useEffect(
    () => () => {
      if (hold.current !== null) window.clearTimeout(hold.current);
      roll.current?.stop();
    },
    [],
  );

  // Any move by the reader anywhere on the page (a press, a key, a scroll of the wheel, a touch, focus moving) ends the
  // carry-on, not only a move over the charts: someone reading the words keeps the story.
  useEffect(() => {
    const stop = () => {
      if (carryOn.current) cancelCarryOn();
    };
    const events = ["pointerdown", "keydown", "wheel", "touchstart", "focusin"] as const;
    for (const e of events) document.addEventListener(e, stop, { capture: true, passive: true });
    return () => {
      for (const e of events) document.removeEventListener(e, stop, { capture: true });
    };
    // cancelCarryOn only touches refs and timers, so the listener set once stays right.
  }, []);

  // Arriving in the future any other way (the switch, the search, a link, the back button) ends the carry-on.
  useEffect(() => {
    if (future) cancelCarryOn();
  });

  // A shared future link hid the story before React arrived (see page.tsx); from here the mode decides.
  useEffect(() => {
    document.getElementById("home-future")?.remove();
  }, []);

  // The story's rows fade as the year rolls on past today.
  const storyOpacity = useTransform(sweep.cursor, (c) => (c <= to ? 1 : Math.max(0, 1 - (c - to) / 4)));

  function switchMode() {
    if (!frame || !state) return;
    cancelCarryOn();
    if (future) {
      setSearch({ mode: "past", c: null, r: null }, true);
      sweep.stop();
      sweep.cursor.set(to);
    } else {
      setSearch({ mode: "future", p: periodId(state.period), s: state.path }, true);
    }
  }

  function replay() {
    cancelCarryOn();
    if (frame && future) setSearch({ mode: null, p: null, s: null, m: null, c: null, r: null }, true);
    carryOn.current = frame !== undefined;
    sweep.play();
  }

  const year = Math.floor(sweep.t);
  const modeHref = frame && state ? (future ? "/?mode=past" : `/?mode=future&p=${periodId(state.period)}&s=${state.path}`) : "/";

  return (
    <div className="flex h-full flex-col py-3 sm:[@media(min-height:761px)]:py-5">
      <div data-probe className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2 pb-2 sm:flex-nowrap sm:[@media(min-height:761px)]:pb-4">
        <div className={future ? "min-w-0 basis-full sm:basis-auto" : "min-w-0"}>
          {future ? (
            <>
              <h1 className="text-lg sm:text-3xl lg:text-4xl">The climate ahead, place by place</h1>
              <p className="mt-1 hidden text-sm text-muted-foreground sm:block [@media(max-height:720px)]:hidden">
                Projected by the world&apos;s climate models, as the World Bank&apos;s Climate Change Knowledge Portal publishes them. Select a country, then a state or province.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl sm:text-4xl">The climate, {from} to today</h1>
              <p className="mt-1 hidden text-sm text-muted-foreground sm:block [@media(max-height:600px)]:hidden">
                One story in seven measurements, and what they mean for people. Move across them to travel in time; select one to dig in.
              </p>
            </>
          )}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {frame && state ? <ModeSwitch mode={future ? "future" : "past"} href={modeHref} onSwitch={switchMode} /> : null}
          <button
            type="button"
            onClick={replay}
            aria-label="Play the story again"
            className="grid size-8 place-items-center rounded-full border border-border text-muted-foreground hover:border-foreground hover:text-foreground"
          >
            <RotateCcw aria-hidden className="size-4" />
          </button>
          {future && frame && state ? (
            <div className="flex flex-row-reverse items-center gap-2 sm:gap-3">
              <PeriodDial periods={frame.periods} value={state.period} onChange={(p, commit) => setSearch({ p: periodId(p) }, commit)} />
              <PathPicker paths={frame.paths} value={state.path} onChange={(s) => setSearch({ s }, true)} />
            </div>
          ) : (
            <p className="text-4xl font-black tracking-tighter num sm:text-6xl" aria-live="off">
              {year}
            </p>
          )}
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <motion.div
          data-home-past
          className="absolute inset-0"
          style={{ opacity: future ? 0 : storyOpacity }}
          inert={future}
          aria-hidden={future || undefined}
        >
          <StoryTimeline rows={rows} from={from} to={to} sweep={sweep} />
        </motion.div>
        {future && state ? (
          <motion.div className="absolute inset-0" initial={{ opacity: reduce ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: reduce ? 0 : 0.6 }}>
            <QueryProvider>
              <FutureMap state={state} onChange={setSearch} />
            </QueryProvider>
          </motion.div>
        ) : null}
      </div>
    </div>
  );
}

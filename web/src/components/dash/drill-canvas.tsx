"use client";

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { Fragment, useCallback, useState, useSyncExternalStore } from "react";

import { QueryProvider } from "@/components/query-provider";
import { Button } from "@/components/ui/button";
import type { DrillNode } from "@/lib/dash/types";
import { dataPath } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { BarChart } from "./bar-chart";
import { Thumb } from "./thumb";
import { TimeChart } from "./time-chart";
import { TracedValue } from "./traced-value";

const EASE = [0.22, 1, 0.36, 1] as const;
const NAV_EVENT = "dash:navigate";

/**
 * One chapter of the dashboard, on one screen: the idea (a few words, one big traced number, one line), its chart, and
 * where the thread goes next, shown as the shapes of the next charts. Selecting a band, a bar or a next chart opens it;
 * the path so far reads across the top. The open node lives in the URL (?v=<node>), so the back button walks back up
 * and any view can be shared. Other nodes are small static files, prefetched when a pointer rests on what opens them.
 */
export function DrillCanvas({ chapter, initial }: { chapter: string; initial: DrillNode }) {
  return (
    <QueryProvider>
      <Canvas chapter={chapter} initial={initial} />
    </QueryProvider>
  );
}

function nodeUrl(chapter: string, id: string): string {
  return `/dash-data/${chapter}/${id}.json`;
}

async function fetchNode(chapter: string, id: string): Promise<DrillNode> {
  const res = await fetch(nodeUrl(chapter, id));
  if (!res.ok) throw new Error(`${nodeUrl(chapter, id)}: HTTP ${res.status}`);
  return (await res.json()) as DrillNode;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(NAV_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAV_EVENT, onChange);
  };
}

function hrefFor(id: string, rootId: string): string {
  return id === rootId ? "?" : `?v=${encodeURIComponent(id)}`;
}

function Canvas({ chapter, initial }: { chapter: string; initial: DrillNode }) {
  const reduce = useReducedMotion();
  const queryClient = useQueryClient();
  const [moved, setMoved] = useState(false);
  const id = useSyncExternalStore(
    subscribe,
    () => new URLSearchParams(window.location.search).get("v") ?? initial.id,
    () => initial.id,
  );

  const query = useQuery({
    queryKey: ["dash", chapter, id],
    queryFn: () => fetchNode(chapter, id),
    initialData: id === initial.id ? initial : undefined,
    placeholderData: keepPreviousData,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const peek = useCallback(
    (next: string) => {
      void queryClient.prefetchQuery({ queryKey: ["dash", chapter, next], queryFn: () => fetchNode(chapter, next), staleTime: Number.POSITIVE_INFINITY });
    },
    [chapter, queryClient],
  );

  const go = useCallback(
    (next: string) => {
      const url = new URL(window.location.href);
      if (next === initial.id) url.searchParams.delete("v");
      else url.searchParams.set("v", next);
      window.history.pushState(null, "", url);
      setMoved(true);
      window.dispatchEvent(new Event(NAV_EVENT));
    },
    [initial.id],
  );

  /** Plain clicks navigate in place; modified clicks (new tab) follow the href. */
  function onLink(e: React.MouseEvent, next: string) {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    go(next);
  }

  if (query.isError && !query.data) {
    return (
      <div className="grid h-full content-center gap-4">
        <p className="text-2xl font-bold tracking-tight">This view could not be loaded.</p>
        <p className="text-muted-foreground">
          The file <code className="code-id">{nodeUrl(chapter, id)}</code> did not load ({String(query.error.message)}).
        </p>
        <div>
          <Button onClick={() => go(initial.id)}>Start again</Button>
        </div>
      </div>
    );
  }

  const node = query.data ?? initial;
  const loading = query.isPlaceholderData || query.isFetching;
  // A shared link (?v=…) opens on the server-rendered first node until its own node arrives; hide that stale view
  // rather than flash a different idea. Once the reader has moved, the previous node stays visible while loading.
  const stale = node.id !== id && !query.isError && node.id === initial.id && !moved;
  const parent = node.trail.at(-1);
  const t = { duration: reduce ? 0 : 0.45, ease: EASE };

  return (
    <div className="flex h-full flex-col gap-3 py-3 sm:gap-4 sm:py-5" aria-busy={loading}>
      {/* The path so far: each earlier idea, then this one. */}
      <nav aria-label="The path so far" className="flex min-h-8 items-center gap-2 overflow-x-auto text-sm whitespace-nowrap">
        {parent ? (
          <a
            href={hrefFor(parent.id, initial.id)}
            onClick={(e) => onLink(e, parent.id)}
            onPointerEnter={() => peek(parent.id)}
            aria-label={`Back to ${parent.crumb}`}
            className="grid size-8 shrink-0 place-items-center rounded-full border border-border hover:border-foreground"
          >
            <ArrowLeft aria-hidden className="size-4" />
          </a>
        ) : null}
        <ol className="flex items-center gap-1.5">
          {node.trail.map((c) => (
            <Fragment key={c.id}>
              <li>
                <a
                  href={hrefFor(c.id, initial.id)}
                  onClick={(e) => onLink(e, c.id)}
                  onPointerEnter={() => peek(c.id)}
                  className="font-medium text-muted-foreground hover:text-foreground"
                >
                  {c.crumb}
                </a>
              </li>
              <li aria-hidden className="h-px w-4 bg-border" />
            </Fragment>
          ))}
          <li aria-current="page" className="font-semibold">
            {node.crumb}
          </li>
        </ol>
        <motion.span className="ml-auto h-1 w-16 shrink-0 overflow-hidden rounded-full bg-muted" initial={false} animate={{ opacity: loading ? 1 : 0 }} aria-hidden>
          <motion.span
            className="block h-full w-1/2 rounded-full bg-foreground"
            animate={loading && !reduce ? { x: ["-100%", "200%"] } : { x: "-100%" }}
            transition={{ repeat: Number.POSITIVE_INFINITY, duration: 0.9, ease: "linear" }}
          />
        </motion.span>
      </nav>

      <div className={cn("grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-3 lg:grid-cols-[minmax(0,4fr)_minmax(0,9fr)] lg:grid-rows-1 lg:gap-10", stale && "invisible")}>
        {/* Keyed by node: a new idea remounts and slides in (no exit phase, so a fast drill can never leave it blank). */}
        <motion.header
          key={node.id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={t}
          className="flex flex-col gap-1 sm:gap-2 lg:justify-center"
        >
          <h1 className="text-2xl sm:text-4xl">{node.kicker}</h1>
          <p className="flex flex-wrap items-baseline gap-x-3 lg:flex-col lg:gap-1">
            <TracedValue h={node.headline} className="text-5xl font-black tracking-tighter sm:text-7xl xl:text-8xl" />
            <span className="text-sm font-semibold sm:text-lg">{node.headline.unitLabel}</span>
          </p>
          <p className="line-clamp-3 max-w-prose text-sm text-muted-foreground sm:text-base lg:line-clamp-none">{node.sentence}</p>
        </motion.header>

        <section aria-label="Chart" className="relative min-h-0">
          {/* Same kind of chart: it morphs in place. A different kind fades in fresh (no exit phase to get stuck). */}
          <motion.div key={node.chart.kind} className="h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={t}>
            {node.chart.kind === "bars" ? (
              <BarChart chart={node.chart} onSelect={go} onPeek={peek} />
            ) : (
              <TimeChart chart={node.chart} onSelect={go} onPeek={peek} />
            )}
          </motion.div>
        </section>
      </div>

      {node.drills.length > 0 ? (
        <nav aria-label="Where this leads" className={cn("-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0", stale && "invisible")}>
          <motion.ul key={node.id} className="flex gap-2 sm:gap-3" initial="hidden" animate="shown">
            {node.drills.map((d, i) => (
              <motion.li
                key={d.to}
                className="shrink-0"
                variants={{ hidden: { opacity: 0, y: 10 }, shown: { opacity: 1, y: 0 } }}
                transition={{ ...t, delay: reduce ? 0 : 0.15 + i * 0.05 }}
              >
                <a
                  href={hrefFor(d.to, initial.id)}
                  onClick={(e) => onLink(e, d.to)}
                  onPointerEnter={() => peek(d.to)}
                  onFocus={() => peek(d.to)}
                  aria-label={d.kicker ?? d.label}
                  className="group flex h-24 w-44 flex-col gap-1 rounded-xl border border-border bg-card p-2.5 transition-colors hover:border-foreground focus-visible:border-foreground focus-visible:outline-2 sm:h-28 sm:w-52"
                >
                  <span className="line-clamp-2 text-xs leading-tight font-semibold sm:text-sm">{d.kicker ?? d.label}</span>
                  {d.preview ? (
                    <span className="min-h-0 flex-1 opacity-80 transition-opacity group-hover:opacity-100">
                      <Thumb preview={d.preview} delay={0.2 + i * 0.05} />
                    </span>
                  ) : null}
                </a>
              </motion.li>
            ))}
          </motion.ul>
        </nav>
      ) : null}

      <p className="truncate text-[11px] text-muted-foreground" title={node.credit.map((c) => c.attribution).join(" ")}>
        Data:{" "}
        {node.credit.map((c, i) => (
          <Fragment key={c.indicator}>
            {i > 0 ? " · " : null}
            <Link href={dataPath(c.indicator)} className="underline decoration-dotted underline-offset-2 hover:text-foreground">
              {c.producers}
            </Link>{" "}
            ({c.licence})
          </Fragment>
        ))}
        . Select any number for its source.
      </p>
    </div>
  );
}

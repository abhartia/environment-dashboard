"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Copy, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState, useSyncExternalStore } from "react";

import { getCatalogOptions } from "@/gen/hey-api/@tanstack/react-query.gen";
import type { CatalogEntry } from "@/gen/hey-api/types.gen";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { formatPeriod } from "@/lib/format";
import { citeAs, licenceSentence, producers } from "@/lib/provenance";
import { dataPath } from "@/lib/routes";
import { reportProblemUrl } from "@/lib/site";

import type { TraceTarget } from "./trace-listener";

/** One client per panel instance (the panel is mounted once per page, on first use). The catalogue never changes under a deploy. */
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: Number.POSITIVE_INFINITY, retry: 1 } } });

export function TracePanel(props: { target: TraceTarget; onClose: () => void }) {
  return (
    <QueryClientProvider client={queryClient}>
      <Panel {...props} />
    </QueryClientProvider>
  );
}

function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia("(min-width: 768px)");
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia("(min-width: 768px)").matches,
    () => true,
  );
}

function Panel({ target, onClose }: { target: TraceTarget; onClose: () => void }) {
  const wide = useWide();
  // A new click mounts a new panel (keyed by the click), so the panel starts open on its own anchor.
  const [open, setOpen] = useState(true);
  const anchorRef = useRef<HTMLElement | null>(target.anchor);
  const { data, isPending, isError } = useQuery({ ...getCatalogOptions(), throwOnError: false });
  const entry = useMemo(() => data?.indicators.find((e) => e.id === target.id), [data, target.id]);
  const close = (o: boolean) => {
    setOpen(o);
    if (!o) {
      onClose();
      target.anchor.focus();
    }
  };

  const body = isPending ? (
    <p className="text-sm text-muted-foreground">Loading the source…</p>
  ) : isError || !entry ? (
    <p className="text-sm">
      The source details could not be loaded. <Link href={dataPath(target.id)}>Open the data page</Link> instead.
    </p>
  ) : (
    <TraceBody entry={entry} target={target} />
  );

  if (wide) {
    return (
      <Popover open={open} onOpenChange={close}>
        <PopoverAnchor virtualRef={anchorRef as React.RefObject<HTMLElement>} />
        <PopoverContent align="start" className="w-[26rem] max-w-[calc(100vw-2rem)] p-4" aria-label="Where this number comes from">
          {body}
        </PopoverContent>
      </Popover>
    );
  }
  return (
    <Drawer open={open} onOpenChange={close}>
      <DrawerContent>
        <DrawerHeader className="text-left">
          <DrawerTitle className="sr-only">Where this number comes from</DrawerTitle>
          <DrawerDescription className="sr-only">The producer, version, licence and files behind this number.</DrawerDescription>
        </DrawerHeader>
        <div className="max-h-[70vh] overflow-y-auto px-4 pb-6">{body}</div>
      </DrawerContent>
    </Drawer>
  );
}

function TraceBody({ entry, target }: { entry: CatalogEntry; target: TraceTarget }) {
  const p = entry.provenance;
  const [copied, setCopied] = useState(false);
  const citation = citeAs(entry);
  return (
    <div className="grid gap-3 text-sm">
      <div className="grid gap-1">
        <p className="eyebrow">Where this number comes from</p>
        <p className="font-medium text-foreground">{entry.title}</p>
        <p className="text-muted-foreground">
          {producers(entry).join(" and ")} · {p.scope.geography}
          {target.period ? ` · ${formatPeriod(target.period)}` : ""} · version {entry.vintage} · {licenceSentence(entry)}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm">
          <Link href={dataPath(entry.id, target.period || undefined)}>See the data</Link>
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            await navigator.clipboard.writeText(citation);
            setCopied(true);
          }}
        >
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? "Citation copied" : "Copy citation"}
        </Button>
      </div>
      <Collapsible>
        <CollapsibleTrigger className="group flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
          <ChevronDown aria-hidden="true" className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
          Technical provenance
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 grid gap-3 text-xs">
          {p.origins.map((o) => (
            <div key={o.sha256} className="grid gap-0.5">
              <p className="text-foreground">{o.title}</p>
              {o.url_download ? (
                <a href={o.url_download} rel="noopener" className="code-id text-link underline">
                  {o.url_download}
                </a>
              ) : (
                <p className="text-muted-foreground">Downloaded by hand from {o.url_main}</p>
              )}
              <p className="text-muted-foreground">
                Fetched {o.date_accessed} · <span className="code-id">sha256 {o.sha256}</span>
              </p>
              <p className="flex flex-wrap gap-x-3">
                {o.wayback_url ? (
                  <a href={o.wayback_url} rel="noopener" className="inline-flex items-center gap-1 text-link underline">
                    Archived copy <ExternalLink aria-hidden="true" className="size-3" />
                  </a>
                ) : null}
                {o.r2_url ? (
                  <a href={o.r2_url} rel="noopener" className="inline-flex items-center gap-1 text-link underline">
                    Our copy of the file <ExternalLink aria-hidden="true" className="size-3" />
                  </a>
                ) : null}
              </p>
            </div>
          ))}
          <div className="grid gap-1">
            <p className="text-foreground">What was done</p>
            <ol className="list-decimal pl-4 text-muted-foreground">
              {p.processing.map((s) => (
                <li key={s.transform_sha256 + s.description}>{s.description}</li>
              ))}
            </ol>
          </div>
          <a href={reportProblemUrl(entry.id)} rel="noopener" className="text-link underline">
            Report a problem with this number
          </a>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

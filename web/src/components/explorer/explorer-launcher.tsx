"use client";

import dynamic from "next/dynamic";
import { BarChart3 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export type ExplorerSpec = {
  id: string;
  label: string;
  title: string;
  unit: string;
  decimals: number;
  headlineEntity: string;
  countries: boolean;
  dimension: { id: string; label: string; values: { id: string; label: string }[] } | null;
  initial: string[];
  fixedDims: Record<string, string>;
};

// Recharts, TanStack Query and the toggle UI load only when someone opens the Explorer.
const ExplorerIsland = dynamic(() => import("./explorer-island").then((m) => m.ExplorerIsland), {
  ssr: false,
  loading: () => <p className="p-4 text-sm text-muted-foreground">Loading the explorer…</p>,
});

export function ExplorerLauncher({ spec }: { spec: ExplorerSpec }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="not-prose my-8 rounded-xl border border-border bg-card" aria-label={`Explore: ${spec.label}`} data-explorer={spec.id}>
      {open ? (
        <ExplorerIsland spec={spec} />
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm">
            <span className="font-medium">Explore:</span> {spec.label}
          </p>
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            <BarChart3 aria-hidden="true" /> Open the explorer
          </Button>
        </div>
      )}
    </section>
  );
}

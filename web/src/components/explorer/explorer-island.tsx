"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { getIndicatorOptions } from "@/gen/hey-api/@tanstack/react-query.gen";
import type { Observation } from "@/gen/hey-api/types.gen";
import { calendarPeriod, formatValue } from "@/lib/format";
import { expandIndicator } from "@/lib/indicator-table";

import type { ExplorerSpec } from "./explorer-launcher";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: Number.POSITIVE_INFINITY, retry: 1 } } });
const MAX_LINES = 5;

export function ExplorerIsland({ spec }: { spec: ExplorerSpec }) {
  return (
    <QueryClientProvider client={queryClient}>
      <Island spec={spec} />
    </QueryClientProvider>
  );
}

function matches(o: Observation, entity: string, fixed: Record<string, string>): boolean {
  return o.entity === entity && Object.entries(fixed).every(([k, v]) => o.dims[k] === v);
}

function Island({ spec }: { spec: ExplorerSpec }) {
  const { data, isPending, isError } = useQuery({ ...getIndicatorOptions({ path: { id: spec.id } }), select: expandIndicator, throwOnError: false });
  const [selected, setSelected] = useState<string[]>(spec.initial);
  const dim = spec.dimension;
  const keys = useMemo(() => (dim ? selected : ["value"]), [dim, selected]);

  const rows = useMemo(() => {
    if (!data) return [];
    const byPeriod = new Map<string, Record<string, number | string | null>>();
    for (const o of data.observations) {
      if (!matches(o, spec.headlineEntity, spec.fixedDims)) continue;
      const key = dim ? o.dims[dim.id] : "value";
      if (!keys.includes(key)) continue;
      const period = calendarPeriod(o);
      const row = byPeriod.get(period) ?? { period };
      row[key] = o.value;
      byPeriod.set(period, row);
    }
    return [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)));
  }, [data, dim, keys, spec.fixedDims, spec.headlineEntity]);

  const config: ChartConfig = Object.fromEntries(
    keys.map((k, i) => [k, { label: dim?.values.find((v) => v.id === k)?.label ?? spec.title, color: `var(--chart-${(i % 5) + 1})` }]),
  );

  if (isPending) return <p className="p-4 text-sm text-muted-foreground">Loading the data…</p>;
  if (isError || !data) {
    return (
      <p className="p-4 text-sm">
        The data file could not be loaded. It is at <a href={`/data/v1/indicators/${spec.id}.json`}>/data/v1/indicators/{spec.id}.json</a>.
      </p>
    );
  }

  return (
    <div className="grid gap-4 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">{spec.title}</p>
        <p className="text-xs text-muted-foreground">
          {spec.unit} · version {data.vintage}
        </p>
      </div>
      {dim ? (
        <div className="grid gap-1.5">
          <p className="text-xs text-muted-foreground" id={`${spec.id}-dim`}>
            {dim.label} (up to {MAX_LINES})
          </p>
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            aria-labelledby={`${spec.id}-dim`}
            value={selected}
            onValueChange={(v) => v.length > 0 && v.length <= MAX_LINES && setSelected(v)}
            className="flex flex-wrap justify-start"
          >
            {dim.values.map((v) => (
              <ToggleGroupItem key={v.id} value={v.id} className="text-xs">
                {v.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      ) : null}
      <Tabs defaultValue="chart">
        <TabsList>
          <TabsTrigger value="chart">Chart</TabsTrigger>
          <TabsTrigger value="table">Table</TabsTrigger>
        </TabsList>
        <TabsContent value="chart">
          <ChartContainer config={config} className="aspect-[16/9] min-h-56 w-full">
            <LineChart data={rows} margin={{ left: 8, right: 8, top: 8 }} accessibilityLayer>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={32} />
              <YAxis tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => formatValue(v, Math.min(spec.decimals, 2))} />
              <ChartTooltip content={<ChartTooltipContent formatter={(v) => `${formatValue(Number(v), spec.decimals)} ${spec.unit}`} />} />
              {keys.map((k) => (
                <Line key={k} dataKey={k} type="linear" stroke={`var(--color-${k})`} strokeWidth={2} dot={false} connectNulls={false} />
              ))}
            </LineChart>
          </ChartContainer>
        </TabsContent>
        <TabsContent value="table">
          <div className="max-h-96 overflow-auto rounded-lg border border-border">
            <Table className="text-xs">
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead className="sticky left-0 bg-card">Period</TableHead>
                  {keys.map((k) => (
                    <TableHead key={k} className="text-right">
                      {String(config[k]?.label)} ({spec.unit})
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={String(r.period)}>
                    <TableCell className="sticky left-0 bg-card num">{r.period}</TableCell>
                    {keys.map((k) => (
                      <TableCell key={k} className="num text-right">
                        {typeof r[k] === "number" ? formatValue(r[k] as number, spec.decimals) : ""}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

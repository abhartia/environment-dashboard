import type { ReactNode } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/** `note` is shown above the table (e.g. that a very long series shows only its latest rows here). */
export type FigureTable = { caption: string; columns: string[]; rows: ReactNode[][]; note?: string };

/**
 * The frame every data figure sits in (pattern from gigabiome's figure.tsx): a title, the chart, a written takeaway
 * (the figcaption, which the chart's aria-describedby points at), a table of the same values, and the source line
 * with the credit its licence requires.
 */
export function Figure({
  id,
  title,
  takeaway,
  source,
  table,
  className,
  children,
}: {
  id: string;
  title: string;
  takeaway: ReactNode;
  source: ReactNode;
  table: FigureTable;
  className?: string;
  children: ReactNode;
}) {
  return (
    <figure id={id} data-figure className={cn("overflow-hidden rounded-xl border border-border bg-card", className)}>
      <div className="border-b border-border px-4 py-3">
        <p className="text-sm font-medium">{title}</p>
      </div>
      <div className="p-3 sm:p-4" role="img" aria-labelledby={`${id}-title`} aria-describedby={`${id}-takeaway`}>
        <span id={`${id}-title`} className="sr-only">
          {title}
        </span>
        {children}
      </div>
      <figcaption id={`${id}-takeaway`} className="border-t border-border px-4 py-3 text-sm">
        {takeaway}
      </figcaption>
      <details className="group border-t border-border" data-figure-table>
        <summary className="cursor-pointer px-4 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground">
          Show as a table
        </summary>
        <div className="max-h-96 overflow-auto px-4 pb-4">
          {table.note ? <p className="pb-2 text-xs text-muted-foreground">{table.note}</p> : null}
          <Table className="text-xs">
            <caption className="sr-only">{table.caption}</caption>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                {table.columns.map((c, i) => (
                  <TableHead key={i} className={cn(i === 0 && "sticky left-0 bg-card")}>
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.rows.map((row, i) => (
                <TableRow key={i}>
                  {row.map((cell, j) => (
                    <TableCell key={j} className={cn("num", j === 0 && "sticky left-0 bg-card", j > 0 && "text-right")}>
                      {cell}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </details>
      <div className="border-t border-border bg-paper px-4 py-2.5 text-xs text-muted-foreground" data-figure-source>
        {source}
      </div>
    </figure>
  );
}

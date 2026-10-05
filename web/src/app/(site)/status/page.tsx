import type { Metadata } from "next";
import Link from "next/link";

import { StatusAge } from "@/components/data/status-age";
import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { source, status } from "@/lib/data";
import { sourcePath } from "@/lib/routes";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Status",
  description: "How each data source fared in the latest weekly check: fetched, unchanged, failed, or downloaded by hand.",
  alternates: canonical("/status"),
};

const STATE_WORDS = { ok: "New version fetched", unchanged: "Unchanged", failed: "Failed", manual: "Downloaded by hand" } as const;

export default function Page() {
  const st = status();
  const rows = Object.entries(st.sources).sort(([, a], [, b]) => (a.state === "failed" ? -1 : 0) - (b.state === "failed" ? -1 : 0));
  const failed = rows.filter(([, r]) => r.state === "failed").length;
  return (
    <>
      <PageHeader
        eyebrow="Status"
        title="Is the data up to date?"
        lede={
          <p>
            Every source is checked weekly. When a check fails, the site keeps showing the last version that passed all
            our checks, and says so here. This page was generated from the check of{" "}
            <time dateTime={st.generated_at}>{st.generated_at.slice(0, 16).replace("T", " ")} UTC</time>
            {st.run_url ? (
              <>
                {" "}(
                <a href={st.run_url} rel="noopener" className="text-link underline">
                  run log
                </a>
                )
              </>
            ) : null}
            .
          </p>
        }
      />
      <Container className="grid gap-6">
        <StatusAge generatedAt={st.generated_at} />
        <p className="text-sm">
          {rows.length} sources checked; {failed === 0 ? "none failed." : `${failed} failed.`}
        </p>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-card">Source</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Checked</TableHead>
                <TableHead>Last success</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(([id, r]) => (
                <TableRow key={id}>
                  <TableCell className="sticky left-0 bg-card">
                    <Link href={sourcePath(id)} className="text-link underline">
                      {source(id).title}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {STATE_WORDS[r.state]}
                    {r.reason ? <span className="block max-w-md text-xs text-muted-foreground">{r.reason}</span> : null}
                  </TableCell>
                  <TableCell className="num">{r.vintage ?? "none yet"}</TableCell>
                  <TableCell className="num whitespace-nowrap">{r.checked_at.slice(0, 10)}</TableCell>
                  <TableCell className="num whitespace-nowrap">{r.last_success?.slice(0, 10) ?? "never"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Container>
    </>
  );
}

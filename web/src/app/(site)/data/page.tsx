import type { Metadata } from "next";
import Link from "next/link";

import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { catalog } from "@/lib/data";
import { formatValue, formatWhen } from "@/lib/format";
import { producers } from "@/lib/provenance";
import { dataPath } from "@/lib/routes";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Data",
  description: "Every number published on the site, with its producer, version, licence and a page tracing it to the original file.",
  alternates: canonical("/data"),
};

export default function Page() {
  const entries = [...catalog().indicators].sort((a, b) => a.title.localeCompare(b.title));
  return (
    <>
      <PageHeader
        eyebrow="Data"
        title="Every number, and where it comes from"
        lede={
          <p>
            Each row opens a page with the values, the exact file they came from, every step applied, and the licence.
            Numbers whose producers allow it can be downloaded there as CSV or JSON, and the full set is described in a
            machine-readable <a href="/data/v1/catalog.json" className="text-link underline">catalogue</a>.
          </p>
        }
      />
      <Container>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-card">Indicator</TableHead>
                <TableHead>Latest</TableHead>
                <TableHead>Producer</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Download</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="sticky left-0 bg-card">
                    <Link href={dataPath(e.id)} className="text-link underline">
                      {e.title}
                    </Link>
                  </TableCell>
                  <TableCell className="num whitespace-nowrap">
                    {e.latest ? `${formatValue(e.latest.value, e.display.decimals)} ${e.unit.short}, ${formatWhen(e.latest)}` : "on its page"}
                  </TableCell>
                  <TableCell>{producers(e).join(", ")}</TableCell>
                  <TableCell className="num">{e.vintage}</TableCell>
                  <TableCell>{e.downloadable ? "CSV, JSON" : "shown only"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Container>
    </>
  );
}

import type { CatalogEntry } from "@/gen/hey-api/types.gen";
import { dataPath } from "@/lib/routes";
import { absoluteUrl } from "@/lib/site-url";

/** Plain-language provenance shared by the Trace panel and the data pages (no server-only imports: used client-side). */

export function producers(entry: CatalogEntry): string[] {
  return [...new Set(entry.provenance.origins.map((o) => o.producer))];
}

const CLASS_WORDS: Record<CatalogEntry["licence_class"], string> = {
  open: "free to reuse with credit",
  "share-alike": "free to reuse with credit, under the same licence",
  noncommercial: "free to reuse with credit, non-commercially",
  "no-derivatives": "shown as published; not to be redistributed or recalculated",
  "display-only": "shown under its terms; not to be redistributed",
  excluded: "not used",
};

export function licenceSentence(entry: CatalogEntry): string {
  return `${entry.provenance.licence.name} (${CLASS_WORDS[entry.licence_class]})`;
}

/** The producer's own citation first, then how to cite this site's copy (vintage and access date included). */
export function citeAs(entry: CatalogEntry): string {
  const cites = [...new Set(entry.provenance.origins.map((o) => o.citation_full))];
  const accessed = entry.provenance.origins.map((o) => o.date_accessed).sort().at(-1);
  return `${cites.join("\n")}\nVia Environment Dashboard, ${absoluteUrl(dataPath(entry.id))} (version ${entry.vintage}, data accessed ${accessed}).`;
}

/** Short labels for a licence class, for badges and tables. */
export const CLASS_LABEL: Record<CatalogEntry["licence_class"], string> = {
  open: "Free to reuse with credit",
  "share-alike": "Reuse with credit, same licence",
  noncommercial: "Non-commercial reuse with credit",
  "no-derivatives": "Shown as published only",
  "display-only": "Shown only, not redistributed",
  excluded: "Not used",
};

import type { MetadataRoute } from "next";

import { catalog, sources } from "@/lib/data";
import { STATIC_PAGES } from "@/lib/pages";
import { dataPath, sourcePath } from "@/lib/routes";
import { absoluteUrl } from "@/lib/site-url";

export const dynamic = "force-static";

/** A data page changes when its data does: its lastmod is the newest access date among its input files. */
export default function sitemap(): MetadataRoute.Sitemap {
  const entries = catalog().indicators;
  const lastData = (ids: string[]) =>
    entries
      .filter((e) => ids.includes(e.id))
      .flatMap((e) => e.provenance.origins.map((o) => o.date_accessed))
      .sort()
      .at(-1);
  return [
    ...STATIC_PAGES.map((p) => ({ url: absoluteUrl(p.path), lastModified: p.updated, priority: p.priority })),
    ...entries.map((e) => ({ url: absoluteUrl(dataPath(e.id)), lastModified: lastData([e.id]), priority: 0.6 })),
    ...sources().map((s) => ({
      url: absoluteUrl(sourcePath(s.id)),
      lastModified: lastData(entries.filter((e) => e.source_ids.includes(s.id)).map((e) => e.id)) ?? s.evidence.checked_on,
      priority: 0.4,
    })),
  ];
}

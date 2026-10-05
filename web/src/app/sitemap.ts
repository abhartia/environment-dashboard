import type { MetadataRoute } from "next";

import { STATIC_PAGES } from "@/lib/pages";
import { absoluteUrl } from "@/lib/site-url";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return STATIC_PAGES.map((p) => ({ url: absoluteUrl(p.path), lastModified: p.updated, priority: p.priority }));
}

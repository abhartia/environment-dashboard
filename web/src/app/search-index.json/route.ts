import { catalog, sources } from "@/lib/data";
import { producers } from "@/lib/provenance";
import { dataPath, sourcePath } from "@/lib/routes";
import { futurePlaces } from "@/lib/dash/future-tree";
import { CHAPTER_META } from "@/lib/dash/meta";

export const dynamic = "force-static";

export type SearchItem = { kind: "chapter" | "place" | "data" | "source" | "page"; title: string; detail: string; href: string };

/**
 * The ⌘K search index, built with the site: the dashboard chapters, every place the future map opens on, every
 * published number and every source.
 */
export function GET() {
  const items: SearchItem[] = [
    ...CHAPTER_META.map((c) => ({ kind: "chapter" as const, title: c.question, detail: c.title, href: `/${c.slug}` })),
    ...futurePlaces().map((p) => ({ kind: "place" as const, ...p })),
    ...catalog().indicators.map((e) => ({ kind: "data" as const, title: e.title, detail: producers(e).join(", "), href: dataPath(e.id) })),
    ...sources().map((s) => ({ kind: "source" as const, title: s.title, detail: s.publisher, href: sourcePath(s.id) })),
    { kind: "page", title: "Methods: how every number is sourced and checked", detail: "About the data", href: "/methods" },
    { kind: "page", title: "Status: is the data up to date?", detail: "About the data", href: "/status" },
  ];
  return Response.json(items);
}

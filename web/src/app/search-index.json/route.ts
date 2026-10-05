import { catalog, sources } from "@/lib/data";
import { producers } from "@/lib/provenance";
import { dataPath, sourcePath } from "@/lib/routes";
import { SECTIONS } from "@/lib/sections";

export const dynamic = "force-static";

export type SearchItem = { kind: "story" | "section" | "data" | "source" | "page"; title: string; detail: string; href: string };

/** The ⌘K search index, built with the site: stories, every published number and every source. */
export function GET() {
  const items: SearchItem[] = [
    ...SECTIONS.map((s) => ({ kind: "section" as const, title: s.question, detail: s.label, href: s.href })),
    ...SECTIONS.flatMap((s) =>
      s.stories.filter((st) => st.ready).map((st) => ({ kind: "story" as const, title: st.question, detail: `${s.label} · ${st.title}`, href: `${s.href}/${st.slug}` })),
    ),
    ...catalog().indicators.map((e) => ({ kind: "data" as const, title: e.title, detail: producers(e).join(", "), href: dataPath(e.id) })),
    ...sources().map((s) => ({ kind: "source" as const, title: s.title, detail: s.publisher, href: sourcePath(s.id) })),
    { kind: "page", title: "Methods: how every number is sourced and checked", detail: "About the data", href: "/methods" },
    { kind: "page", title: "Status: is the data up to date?", detail: "About the data", href: "/status" },
  ];
  return Response.json(items);
}

import { catalog } from "@/lib/data";
import { producers } from "@/lib/provenance";
import { SECTIONS } from "@/lib/sections";
import { renderOgImage } from "@/lib/seo/og-image";
import { BRAND } from "@/lib/site";
import { STORIES, story } from "@/lib/stories";

/**
 * Social images as real .png files (pattern from gigabiome): a metadata opengraph-image exports to an extensionless
 * file that Cloudflare Pages serves as application/octet-stream; a route handler whose last segment ends in .png is
 * written as a .png.
 */
export const dynamic = "force-static";
export const dynamicParams = false;

type Card = { eyebrow: string; title: string };

function cards(): Record<string, Card> {
  return {
    "home.png": { eyebrow: BRAND.tagline, title: "What is changing the climate, what it is doing, and what can be done" },
    ...Object.fromEntries(SECTIONS.map((s) => [`${s.href.slice(1)}.png`, { eyebrow: s.label, title: s.question }])),
    ...Object.fromEntries(
      STORIES.map((s) => {
        const st = story(s.section, s.slug);
        return [`${s.section}/${s.slug}.png`, { eyebrow: st.title, title: st.question }];
      }),
    ),
    ...Object.fromEntries(
      catalog().indicators.map((e) => [`data/${e.id.split(".").join("/")}.png`, { eyebrow: `Data · ${producers(e).join(", ")}`, title: e.title }]),
    ),
  };
}

export function generateStaticParams() {
  return Object.keys(cards()).map((k) => ({ path: k.split("/") }));
}

export async function GET(_req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const card = cards()[path.join("/")];
  if (!card) return new Response("Not found", { status: 404 });
  return renderOgImage(card);
}

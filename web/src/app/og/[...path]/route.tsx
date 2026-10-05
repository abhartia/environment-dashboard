import { catalog } from "@/lib/data";
import { producers } from "@/lib/provenance";
import { CHAPTER_META } from "@/lib/dash/meta";
import { renderOgImage } from "@/lib/seo/og-image";
import { BRAND } from "@/lib/site";

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
    "home.png": { eyebrow: BRAND.tagline, title: "The climate, 1850 to today" },
    ...Object.fromEntries(CHAPTER_META.map((c) => [`${c.slug}.png`, { eyebrow: c.title, title: c.question }])),
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

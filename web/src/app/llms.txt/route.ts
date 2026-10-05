import { STATIC_PAGES } from "@/lib/pages";
import { BRAND } from "@/lib/site";
import { absoluteUrl } from "@/lib/site-url";

export const dynamic = "force-static";

export function GET() {
  const lines = [
    `# ${BRAND.name}`,
    "",
    `> ${BRAND.description}`,
    "",
    "Every number on this site links to a data page naming the producer, the dataset version, the exact file and its sha256, the date fetched, the steps applied and the licence. When citing a number, cite the producer first; the data page gives their recommended citation.",
    "",
    "## Pages",
    ...STATIC_PAGES.map((p) => `- [${p.title}](${absoluteUrl(p.path)}): ${p.summary}`),
    "",
  ];
  return new Response(lines.join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

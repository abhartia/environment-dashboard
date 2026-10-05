import { CHAPTERS } from "@/lib/dash/chapters";

/**
 * Each dashboard node as a small static JSON file: /dash-data/<chapter>/<node>.json. The browser fetches the next
 * node when someone drills, so a page carries only the node it opens on.
 */
export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return Object.entries(CHAPTERS).flatMap(([chapter, c]) => c.ids().map((id) => ({ path: [chapter, `${id}.json`] })));
}

export async function GET(_req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const [chapter, file] = (await params).path;
  const c = CHAPTERS[chapter];
  if (!c || !file?.endsWith(".json")) return new Response("Not found", { status: 404 });
  return Response.json(c.node(file.slice(0, -".json".length)));
}

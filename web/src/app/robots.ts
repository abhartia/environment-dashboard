import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/site-url";

// Static export: metadata routes must be forced static or the build fails.
export const dynamic = "force-static";

// AI crawlers are named explicitly and allowed: being cited accurately in AI answers is part of the point (gigabiome).
const AI_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot",
  "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot"];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }, ...AI_CRAWLERS.map((ua) => ({ userAgent: ua, allow: "/" }))],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: absoluteUrl("/"),
  };
}

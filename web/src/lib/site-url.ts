/**
 * Single source of truth for the site's public origin (pattern from wadecv).
 *
 * Every absolute URL a crawler sees — canonical, og:url, JSON-LD @id, sitemap,
 * robots — derives from here. An invalid origin is a build failure, not a
 * string that quietly reads "https://undefined".
 */

function resolveSiteUrl(): string {
  // Literal member expression so Next inlines it at build time.
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  const raw = (configured ?? "https://environmentdashboard.org").trim().replace(/\/+$/, "");
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`NEXT_PUBLIC_SITE_URL is not a valid absolute URL: ${JSON.stringify(configured)}`);
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error(`NEXT_PUBLIC_SITE_URL must be http(s), got ${parsed.protocol}`);
  }
  if (!parsed.hostname || parsed.hostname === "undefined" || parsed.hostname === "null") {
    throw new Error(`NEXT_PUBLIC_SITE_URL resolved to a placeholder hostname: ${raw}`);
  }
  return parsed.origin;
}

/** Public origin, no trailing slash, e.g. `https://environmentdashboard.org`. */
export const SITE_URL = resolveSiteUrl();

export function absoluteUrl(path: string): string {
  if (path === "/" || path === "") return SITE_URL;
  if (!path.startsWith("/")) {
    throw new Error(`absoluteUrl() expects a site-relative path starting with "/", got "${path}"`);
  }
  return `${SITE_URL}${path.replace(/\/+$/, "")}`;
}

/** `alternates` block declaring a page its own canonical. */
export function canonical(path: string) {
  return { canonical: absoluteUrl(path) };
}

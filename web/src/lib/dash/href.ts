/**
 * A drill target in another chapter is written "chapter:node" ("people:hw-IND"); this is the URL that opens it. The
 * future's views live on the home page, in its URL: "future:root" is the world map, "future:c-IND" India's.
 */
export function crossHref(to: string): string | null {
  const m = to.match(/^([a-z]+):(.+)$/);
  if (!m) return null;
  if (m[1] === "future") {
    if (m[2] === "root") return "/?mode=future";
    const c = m[2].match(/^c-([A-Z0-9_]+)$/);
    if (!c) throw new Error(`crossHref: ${to} is not a future view`);
    return `/?mode=future&c=${c[1]}`;
  }
  return m[2] === "root" ? `/${m[1]}` : `/${m[1]}?v=${encodeURIComponent(m[2])}`;
}

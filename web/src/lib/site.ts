/** Site facts used across pages and structured data. Nothing here may be embellished. */

export const BRAND = {
  name: "Environment Dashboard",
  tagline: "Climate data, traced to its source",
  description:
    "Explore what is causing climate change, what it is doing, and what can be done. Every number links to the data it came from.",
  email: "hello@environmentdashboard.org",
  repo: "https://github.com/abhartia/environment-dashboard",
} as const;

/** Primary navigation: the three questions. Countries joins when its pages exist (milestone 6). */
export const NAV = [
  { href: "/causes", label: "Causes" },
  { href: "/consequences", label: "Consequences" },
  { href: "/action", label: "What can be done" },
] as const;

/** Footer: where the evidence and the rules live. */
export const FOOTER_NAV = [
  { href: "/data", label: "Data" },
  { href: "/sources", label: "Sources" },
  { href: "/methods", label: "Methods" },
  { href: "/status", label: "Status" },
  { href: "/corrections", label: "Corrections" },
  { href: "/about", label: "About" },
  { href: "/privacy", label: "Privacy" },
  { href: "/accessibility", label: "Accessibility" },
] as const;

/** Pre-filled GitHub issue for a problem with a specific number. */
export function reportProblemUrl(indicatorId?: string, page?: string): string {
  const url = new URL(`${BRAND.repo}/issues/new`);
  url.searchParams.set("template", "data-problem.yml");
  if (indicatorId) url.searchParams.set("indicator", indicatorId);
  if (page) url.searchParams.set("page", page);
  return url.toString();
}

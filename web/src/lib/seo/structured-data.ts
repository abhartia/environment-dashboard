/**
 * JSON-LD builders (pattern from gigabiome). Only facts: no ratings, reviews, counts or awards.
 */
import { BRAND } from "@/lib/site";
import { SITE_URL, absoluteUrl } from "@/lib/site-url";

export const ORG_ID = `${SITE_URL}/#organization`;
export const SITE_ID = `${SITE_URL}/#website`;

export function siteGraph() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": ORG_ID,
        name: BRAND.name,
        url: SITE_URL,
        email: BRAND.email,
        description: BRAND.description,
        publishingPrinciples: absoluteUrl("/methods"),
        correctionsPolicy: absoluteUrl("/corrections"),
        sameAs: [BRAND.repo],
      },
      {
        "@type": "WebSite",
        "@id": SITE_ID,
        url: SITE_URL,
        name: BRAND.name,
        publisher: { "@id": ORG_ID },
        inLanguage: "en",
      },
    ],
  };
}

export function breadcrumbs(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: absoluteUrl(it.path),
    })),
  };
}

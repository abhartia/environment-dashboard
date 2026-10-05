/**
 * Every indexable static page with the date its content last really changed. The sitemap and llms.txt read this;
 * data-driven pages (stories, /data, /sources, countries) add their own entries dated by data vintage.
 * Never bump a date without a real change: a lastmod that moves on every deploy teaches crawlers to ignore it.
 */
import { SECTIONS } from "@/lib/sections";

export type StaticPage = { path: string; title: string; summary: string; updated: string; priority: number };

const SITE_START = "2026-10-04";

export const STATIC_PAGES: StaticPage[] = [
  { path: "/", title: "Home", summary: "The three questions and how to check any number.", updated: SITE_START, priority: 1 },
  ...SECTIONS.map((s) => ({ path: s.href, title: s.label, summary: `${s.question} ${s.intro}`, updated: SITE_START, priority: 0.9 })),
  { path: "/methods", title: "Methods", summary: "How every number is sourced, fetched, archived, transformed, checked and licensed.", updated: SITE_START, priority: 0.7 },
  { path: "/about", title: "About", summary: "Why the site exists and how it is kept honest.", updated: SITE_START, priority: 0.5 },
  { path: "/corrections", title: "Corrections", summary: "Our mistakes and method changes, with dates and before-and-after values.", updated: SITE_START, priority: 0.4 },
  { path: "/privacy", title: "Privacy", summary: "Cookieless, aggregate page counts only.", updated: SITE_START, priority: 0.2 },
  { path: "/accessibility", title: "Accessibility", summary: "WCAG 2.2 AA target and known gaps.", updated: SITE_START, priority: 0.2 },
];

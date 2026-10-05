import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("emissions").title,
  description: "The carbon dioxide the world emits, split one way at a time: by source, by fuel, by country and per person. Every number links to its source.",
  alternates: { canonical: "/emissions" },
};

export default function EmissionsPage() {
  return <ChapterPage slug="emissions" />;
}

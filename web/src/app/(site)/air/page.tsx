import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("air").title,
  description: "Carbon dioxide, methane and nitrous oxide in the air, from today back 800,000 years, and the heat they trap. Every number links to its source.",
  alternates: { canonical: "/air" },
};

export default function AirPage() {
  return <ChapterPage slug="air" />;
}

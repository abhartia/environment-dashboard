import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("food").title,
  description: "Greenhouse gases from food and farming, by country, from livestock and lost food; diets compared; land use and species at risk. Every number links to its source.",
  alternates: { canonical: "/food" },
};

export default function FoodPage() {
  return <ChapterPage slug="food" />;
}

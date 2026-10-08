/**
 * The dashboard's chapters as the reader sees them: URL segment, name and the question each answers. Client-safe
 * (no data): the header, the home grid and the chapter pages share it. The trees are in lib/dash/<slug>-tree.ts.
 */
export const CHAPTER_META = [
  { slug: "emissions", title: "Emissions", question: "How much greenhouse gas do we put into the air, and from where?" },
  { slug: "energy", title: "Energy", question: "How fast is the switch to clean energy?" },
  { slug: "air", title: "Greenhouse gases", question: "How much has built up in the air?" },
  { slug: "heat", title: "Heat", question: "How much warmer is it, and who caused it?" },
  { slug: "oceans", title: "Seas and ice", question: "How much has the sea risen and the ice melted?" },
  { slug: "people", title: "People", question: "What is heat doing to people?" },
  { slug: "food", title: "Food and land", question: "What does feeding ourselves do to the climate and the land?" },
  { slug: "action", title: "What can be done", question: "Which choices cut emissions most, and how much carbon is left?" },
  { slug: "zero", title: "Getting to zero", question: "What would it take to go from today's emissions to zero?" },
] as const;

export type ChapterSlug = (typeof CHAPTER_META)[number]["slug"];

export function chapterMeta(slug: ChapterSlug) {
  const m = CHAPTER_META.find((c) => c.slug === slug);
  if (!m) throw new Error(`unknown chapter ${slug}`);
  return m;
}

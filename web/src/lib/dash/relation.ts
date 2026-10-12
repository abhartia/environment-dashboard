import type { Relation } from "@/lib/dash/types";

/**
 * The few words over a "so what" card: how the consequence relates to the measurement on screen. Each says only what
 * its producer measured (docs/style.md): "caused" only for values attributed to the warming (lib/dash/chapters.ts
 * checks), heat of any cause, a harm of burning fuel itself rather than of the warming, or people living in harm's way.
 */
export const RELATION_EYEBROW: Record<Relation, string> = {
  caused: "Caused by the warming",
  linked: "Heat of any cause",
  burning: "From the burning itself",
  exposed: "People at risk",
};

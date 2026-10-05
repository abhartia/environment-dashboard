import "server-only";

import { action } from "@/lib/dash/action-tree";
import { air } from "@/lib/dash/air-tree";
import { emissions } from "@/lib/dash/emissions-tree";
import { energy } from "@/lib/dash/energy-tree";
import { food } from "@/lib/dash/food-tree";
import { heat } from "@/lib/dash/heat-tree";
import { oceans } from "@/lib/dash/oceans-tree";
import { people } from "@/lib/dash/people-tree";
import type { DrillNode } from "@/lib/dash/types";

export type Chapter = { ids: () => string[]; node: (id: string) => DrillNode };

/** Every dashboard chapter, by its URL segment. Each is a drill-down tree of nodes (lib/dash/<chapter>-tree.ts). */
export const CHAPTERS: Record<string, Chapter> = { emissions, air, heat, oceans, energy, people, food, action };

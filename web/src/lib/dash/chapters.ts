import "server-only";

import { action } from "@/lib/dash/action-tree";
import { air } from "@/lib/dash/air-tree";
import { emissions } from "@/lib/dash/emissions-tree";
import { energy } from "@/lib/dash/energy-tree";
import { food } from "@/lib/dash/food-tree";
import { future } from "@/lib/dash/future-tree";
import { heat } from "@/lib/dash/heat-tree";
import { credit, preview } from "@/lib/dash/kit";
import { oceans } from "@/lib/dash/oceans-tree";
import { ATTRIBUTED, people } from "@/lib/dash/people-tree";
import type { Drill, DrillNode, Headline } from "@/lib/dash/types";
import { zero } from "@/lib/dash/zero-tree";

export type Chapter = { ids: () => string[]; node: (id: string) => DrillNode };

/**
 * Every dashboard chapter, by its URL segment. Each is a drill-down tree of nodes (lib/dash/<chapter>-tree.ts). The
 * future has no page of its own (it is the home page's future mode, lib/dash/href.ts), so it is not in CHAPTER_META.
 */
export const CHAPTERS: Record<string, Chapter> = { emissions, air, heat, oceans, energy, people, food, action, zero, future };

const idsCache = new Map<string, Set<string>>();
/** A chapter's published node ids, read once per build. */
function idsOf(slug: string): Set<string> {
  let ids = idsCache.get(slug);
  if (!ids) idsCache.set(slug, (ids = new Set(CHAPTERS[slug].ids())));
  return ids;
}

/** Whether the producer attributes this value to human-caused warming (the only values a "caused" card may show). */
function attributed(h: Headline): boolean {
  return ATTRIBUTED.some((a) => a.indicator === h.indicator && Object.entries(a.dims ?? {}).every(([k, v]) => h.dims?.[k] === v));
}

/**
 * A node as it is published: each drill into another chapter ("people:coasts") carries that node's crumb, kicker and
 * chart shape, and a "so what" also carries the target's own headline (copied, never computed) and its credit, since
 * the number is shown on this screen. Targets are built but not resolved themselves, so resolution stops after one
 * level and two chapters can point at each other.
 */
export function resolvedNode(slug: string, id: string): DrillNode {
  const node = CHAPTERS[slug].node(id);
  const credits = [...node.credit];
  const indicators = [...node.indicators];
  const drills = node.drills.map((d): Drill => {
    const m = d.to.match(/^([a-z]+):(.+)$/);
    if (!m || (d.kicker && !d.soWhat)) return d;
    const c = CHAPTERS[m[1]];
    if (!c) throw new Error(`${slug}/${id}: the drill to ${d.to} names no chapter`);
    if (!idsOf(m[1]).has(m[2])) throw new Error(`${slug}/${id}: the drill to ${d.to} names a view ${m[1]} does not publish`);
    const target = c.node(m[2]);
    // A future target is the home page's map of a place, whose node kicker names only the measure it lands on: the
    // drill's own label says what the card opens.
    const filled = { ...d, crumb: target.crumb, kicker: m[1] === "future" ? d.label : target.kicker, preview: preview(target.chart) };
    if (!d.soWhat) return filled;
    const h = target.headline;
    if (d.soWhat.relation === "caused" && !attributed(h)) {
      throw new Error(`${slug}/${id}: ${d.to} shows ${h.indicator}, which its producer does not attribute to the warming`);
    }
    if (!credits.some((x) => x.indicator === h.indicator)) credits.push(...credit(h.indicator));
    if (!indicators.includes(h.indicator)) indicators.push(h.indicator);
    return { ...filled, soWhat: { ...d.soWhat, headline: h } };
  });
  const so = drills.filter((d) => d.soWhat);
  if (so.length > 1) throw new Error(`${slug}/${id}: ${so.length} "so what" cards; a view has at most one`);
  return { ...node, drills: [...so, ...drills.filter((d) => !d.soWhat)], credit: credits, indicators };
}

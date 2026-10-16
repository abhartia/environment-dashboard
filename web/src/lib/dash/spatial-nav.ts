/**
 * Keyboard travel on a map: from the focused place, an arrow key moves to the nearest place whose centre lies in that
 * direction (within a 45° cone either side), preferring places straight ahead over ones off to the side. With nothing
 * focused, any arrow starts at the place nearest the middle.
 */
export type NavPoint = { id: string; x: number; y: number };
export type Direction = "left" | "right" | "up" | "down";

export function nextPlace(points: NavPoint[], current: string | null, dir: Direction): string | null {
  if (points.length === 0) return null;
  const from = current ? points.find((p) => p.id === current) : undefined;
  if (!from) {
    const cx = points.reduce((a, p) => a + p.x, 0) / points.length;
    const cy = points.reduce((a, p) => a + p.y, 0) / points.length;
    return points.reduce((best, p) => (Math.hypot(p.x - cx, p.y - cy) < Math.hypot(best.x - cx, best.y - cy) ? p : best)).id;
  }
  let best: { id: string; score: number } | null = null;
  for (const p of points) {
    if (p.id === from.id) continue;
    const dx = p.x - from.x;
    const dy = p.y - from.y;
    const ahead = dir === "right" ? dx : dir === "left" ? -dx : dir === "down" ? dy : -dy;
    const side = dir === "right" || dir === "left" ? Math.abs(dy) : Math.abs(dx);
    if (ahead <= 0 || side > ahead) continue;
    // Distance ahead, with sideways distance counting double: the eye reads "to the right" as roughly level.
    const score = ahead + 2 * side;
    if (!best || score < best.score || (score === best.score && p.id < best.id)) best = { id: p.id, score };
  }
  return best ? best.id : from.id;
}

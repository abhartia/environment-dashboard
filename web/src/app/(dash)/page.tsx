import { HomeCanvas } from "@/components/dash/home-canvas";
import { Container } from "@/components/site/container";
import { futureFrame } from "@/lib/dash/future-tree";
import { STORY_FROM, storyRows } from "@/lib/dash/story";

/**
 * A link to the future mode (?mode=future) must not flash the story first: before the page paints, this hides the
 * story's rows (the canvas removes the style once it has read the URL). A style in the head, not an attribute on
 * <html>, so hydration sees the same markup it rendered.
 */
const HIDE_PAST = `if(new URLSearchParams(location.search).get("mode")==="future"){var s=document.createElement("style");s.id="home-future";s.textContent="[data-home-past]{visibility:hidden}";document.head.appendChild(s)}`;

/**
 * Home: the climate story on one screen. Seven published series on one time axis, in causal order, swept from 1850 to
 * today, each with a band saying what its change means for people; each opens its chapter. The sweep then carries on
 * into the future: a world map of what the climate models project, country by country and region by region. Every
 * number opens its source.
 */
export default function Home() {
  const rows = storyRows();
  const to = Math.max(...rows.flatMap((r) => [...r.values.map((v) => v.x), ...r.series.flatMap((s) => s.points.map((p) => p[0]))]));
  return (
    <Container className="h-full max-w-7xl">
      <script dangerouslySetInnerHTML={{ __html: HIDE_PAST }} />
      <HomeCanvas rows={rows} from={STORY_FROM} to={to} frame={futureFrame()} />
    </Container>
  );
}

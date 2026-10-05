import { StoryTimeline } from "@/components/dash/story-timeline";
import { Container } from "@/components/site/container";
import { STORY_FROM, storyRows } from "@/lib/dash/story";

/**
 * Home: the climate story on one screen. Six published series on one time axis, in causal order, swept from 1850 to
 * today; each opens its chapter. Every number opens its source.
 */
export default function Home() {
  const rows = storyRows();
  const to = Math.max(...rows.flatMap((r) => [...r.values.map((v) => v.x), ...r.series.flatMap((s) => s.points.map((p) => p[0]))]));
  return (
    <Container className="h-full max-w-7xl">
      <StoryTimeline rows={rows} from={STORY_FROM} to={to} />
    </Container>
  );
}

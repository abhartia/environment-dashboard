# The dashboard

The site is a dashboard you drill into, not a collection of articles. The owner chose the "Atlas" direction (white
ground, heavy Inter, colour only where it carries data) and asked for "graphics and animations heavy" pages that drill
down "one idea/disaggregation at a time", that never need scrolling, with no "boring buttons", where the reader can
"follow a narrative in the representation of the data".

## Shape

- **Home** (`/`): the climate story on one screen. Six published series share one time axis in causal order: we burn
  coal, oil and gas; carbon dioxide builds up in the air; the world warms (the stripes); the seas rise; the Arctic ice
  shrinks; and the switch to clean power. On arrival a cursor sweeps from 1850 to today, each row drawing behind it
  and each number reading the latest published value at that moment (never interpolated; before a record begins the
  row says when it starts). Moving across the rows travels in time; selecting a row opens its chapter
  (`lib/dash/story.ts`, `components/dash/story-timeline.tsx`).
- **Chapter** (`/emissions`, `/energy`, `/air`, `/heat`, `/oceans`, `/people`, `/food`, `/action`): a drill-down tree on
  one screen. Each **node** is one idea: a kicker (the page's `h1`), one big traced number, one sentence and one chart.
  The path so far reads across the top. There are no text buttons: a band, a line or a bar opens the next idea when
  it has one, and the other directions show as small cards carrying the next idea's kicker and the shape of its chart.
  The open node is in the URL (`?v=<node>`), so the back button walks back up and any view can be shared.
- **Data and sources** (`/data/...`, `/sources/...`) stay as they are: every number links to its data page and the
  Trace panel. The one-line credit under each view names the producers and licences and links to the data pages,
  which carry each licence's full attribution.
- **One screen, no footer.** Home and the chapters live in the `(dash)` route group, whose layout is exactly the
  viewport (`h-svh`, overflow hidden): views fill the space left under the header with `h-full`, never a calc. The
  reference pages (`(site)`: data, sources, methods, about) scroll as documents. There is no footer anywhere: the
  header menu holds the reference links and the disclaimers, every page links to `/about`, and `/about` carries the
  disclaimers (check-build enforces both).

## How a node is made

`web/src/lib/dash/<chapter>-tree.ts` builds every node at build time from `data/` through `web/src/lib/dash/kit.ts`
(`points`, `headline`, `ranking`, `area`, `line`, `bars`, `credit`, `dimLabel`, `chapter`). The kit only selects,
orders and labels published observations:

- Missing values stay missing. A stacked chart orders its bands by the first year each has data, so nothing is ever
  stacked on a gap.
- Ranked bars show countries and territories only (never aggregates), ties broken by code.
- Big numbers are shown with fewer decimals than published when they are in the thousands, never more.
- Node files are public (`/dash-data/<chapter>/<node>.json`), so the kit throws on any `no-derivatives` or
  `display-only` indicator.

`chapter()` also gives each choice the next node's crumb, kicker and a thumbnail of its chart (every k-th point, or
the first few bars), so the cards can show where they lead before anything is fetched.
`web/src/app/dash-data/[...path]/route.ts` writes one static JSON file per node; `web/src/lib/dash/chapters.ts` lists
the chapters and `web/src/lib/dash/meta.ts` their titles. The page server-renders the chapter's first node; the client
(`components/dash/drill-canvas.tsx`) fetches other nodes with TanStack Query and prefetches the one a pointer rests on.

## Motion

Charts are SVG drawn with d3-shape at their container's own pixel size and animated with `motion`: a band or line that
stays between two nodes morphs, a new one grows from the baseline, ranked bars slide to their new rank, the big number
counts to its new value, and axis ticks glide. Every time axis starts at zero (or below, for values that go negative),
so no change looks larger than it is. Everything respects `prefers-reduced-motion` (no movement, same content).

## Adding a chapter

1. Write `web/src/lib/dash/<chapter>-tree.ts` with `ids()` (every node, so every drill target exists) and `build(id)`.
2. Add it to `chapters.ts` and `meta.ts`, and a `web/src/app/(site)/<chapter>/page.tsx` using `ChapterPage`.
3. `npm run build`: every node is built, so a missing value, an unknown entity or a falsified kicker fails the build.

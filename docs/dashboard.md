# The dashboard

The site is a dashboard you drill into, not a collection of articles. The owner chose the "Atlas" direction (white
ground, heavy Inter, colour only where it carries data) and asked for "graphics and animations heavy" pages that drill
down "one idea/disaggregation at a time", that never need scrolling, with no "boring buttons", where the reader can
"follow a narrative in the representation of the data".

## Shape

- **Home** (`/`): the climate story on one screen. Seven published series share one time axis in causal order: we
  burn coal, oil and gas; carbon dioxide builds up in the air; the world warms (the stripes); its hottest days get
  hotter; ice on land melts; the seas rise; and the switch to clean power. Each number says what it is measured against
  (read from the producer's stated baseline: "above 1850–1900", "above the 1993 average"). Under each chart a **band**
  says what that change means for people (for carbon dioxide, how unusual it is): the headline of the view it opens,
  with that view's series drawn faintly on the same axis. On arrival a cursor sweeps from 1850 to today, each row
  drawing behind it and each number reading the latest published value at that moment (never interpolated; before a
  record begins the row says when it starts); a band appears once its own record begins, or once its claim became
  true (the air passing the highest level in Antarctic ice); a value that belongs to a level of warming rather than a
  year (the extremes band) appears only when the story comes to rest, since a level of warming is never turned into a
  year. So the change is drawn first and what it means lands at the end. Moving across a chart travels in time;
  selecting a row opens its chapter and a band opens the view it quotes (`lib/dash/story.ts`,
  `components/dash/story-timeline.tsx`).
- **Chapter** (`/emissions`, `/energy`, `/air`, `/heat`, `/oceans`, `/people`, `/food`, `/action`, `/zero`): a drill-down tree on
  one screen. Each **node** is one idea: a kicker (the page's `h1`), one big traced number, one sentence and one chart.
  The path so far reads across the top. There are no text buttons: a band, a line or a bar opens the next idea when
  it has one, and the other directions show as small cards carrying the next idea's kicker and the shape of its chart.
  A view whose change matters to people shows that first, as an ink **"so what" card**: the consequence view's own
  traced number and its idea, under a few words saying how the two relate ("Caused by the warming", "Heat of any
  cause", "From the burning itself", "People at risk"). The open node is in the URL (`?v=<node>`), so the back button
  walks back up and any view can be shared.
- **Data and sources** (`/data/...`, `/sources/...`) stay as they are: every number links to its data page and the
  Trace panel. The one-line credit under each view names the producers and licences and links to the data pages,
  which carry each licence's full attribution.
- **One screen, no footer.** Home and the chapters live in the `(dash)` route group, whose layout is exactly the
  viewport (`h-svh`, overflow hidden): views fill the space left under the header with `h-full`, never a calc. The
  reference pages (`(site)`: data, sources, methods, about) scroll as documents. There is no footer anywhere: the
  header menu holds the reference links and the disclaimers, every page links to `/about`, and `/about` carries the
  disclaimers (check-build enforces both).

## What each chapter opens on

- **Emissions** opens on all greenhouse gases by FAO's six IPCC sectors (they add up to FAO's all-sector total, the
  same total behind food's share). Food and farming is not a seventh band: its emissions run through several bands,
  so it is its own view, linked to the food chapter. Below come the split by gas (carbon dioxide, methane, nitrous
  oxide, fluorinated gases), methane by sector, countries, each country's average per person (labelled as a national
  average), one person's footprint (Sweden, by what households and the public sector consume) and the UK's footprint
  by use. Carbon dioxide alone (Global Carbon Project) is the `co2` view, on its own basis: never added to or
  subtracted from FAO's totals.
- **Food and land** opens on food's emissions and splits them by stage (on the farm, clearing land for farming,
  before and after the farm), by process within each stage, by food (farm-gate emissions of FAO's 14 commodities, and
  per kilogram) and methane by animal; each stack adds up to FAO's published total. Land leads to forests: FAO's forest
  area and its net change, then tree cover lost each year (Global Forest Watch: all loss and the part due to fire), what
  drove it, where, and humid tropical primary forest; clearing land for farming links to the same view.
- **Getting to zero** represents the frameworks of Bill Gates's *How to Avoid a Climate Disaster* (2021) from primary
  producers (his own figures, Rhodium Group's and Breakthrough Energy's, cannot be republished). It opens on Climate
  TRACE's emissions grouped into his five activities (making things, plugging in, growing things, getting around,
  keeping warm and cool), grouped in the pipeline the way Rhodium grouped his numbers; each subsector carries its
  activity in the data, so the tree only selects. Its cards are his five questions: how much of the total (shares of
  the five), the plan for cement (making things, and the premium for clean steel and cement), how much power (the
  world, a city, a home), how much space (land per unit of electricity), and how much it costs (the Green Premium:
  stated premiums, then one producer's clean and fossil costs side by side per activity). Then the strategy: net zero
  targets, electrifying, capturing what is left and removing carbon, research budgets, and adapting (farms by size).

A drill target written `chapter:node` opens another chapter's view (`crossDrill` in `kit.ts` carries its title and
chart shape).

- **People** opens on hot extremes becoming more frequent: how many times as often a once-a-decade hottest day
  comes at each level of warming (IPCC AR6 Figure SPM.6 data, modelled), with the hottest day of each year, heavy
  downpours and drought one level down and, below each, the observed series (Lancet Countdown), plus where the IPCC found these extremes increasing
  since the 1950s and its confidence in a human role (SPM.3). Its other views are what the changes mean for people:
  heatwave days caused by the warming (and for babies and people over 65), deaths from heat of any cause and work lost,
  children's lifetimes (Grant and others, 2025, projected), times people were forced from home by weather disasters
  (IDMC, labelled as movements and not a trend, since monitoring grew), people living below high tide (Kulp and
  Strauss, exposure, not flooding), early deaths from the smoke of burning coal, oil and gas (a harm of the burning
  itself, not of the warming), and fires and their smoke. Each links back to the change it follows. Below the world's
  heatwave days, **where you live** ranks countries by heatwave days caused by the warming and opens each country's
  own view (every country the Lancet Countdown gives): its heatwave days with and without the warming, its work hours
  lost per worker (heat of any cause) and its people below high tide (Kulp and Strauss's country rows, in people). A
  value a source does not give is said in words ("No data for Andorra in the Lancet Countdown's work hours"), never
  filled. Each heat country view (`heat:c-<ISO3>`) opens on that country's heatwave days caused by the warming as its
  "so what" card.

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
- Every indicator we may redistribute is shown by at least one node: check-build fails on a published dataset that
  no node draws. A new dataset goes one level below the node it explains, never onto an existing screen. The one
  exception is a "so what" (a home band or a chapter card): it shows another view's own headline and kicker, copied
  when the node is resolved and never computed, so a change and what it means are on one screen.
- `crossTo` and `soWhat` name a node in another chapter (`people:coasts`) without building it; `resolvedNode`
  (`lib/dash/chapters.ts`) fills it in one level deep when the node file is written, so two chapters can point at each
  other. It throws on a node with more than one "so what", and on a "caused by the warming" card whose value the
  producer does not attribute to the warming. The home bands check the same way that their latest value is the target
  view's headline, and their words carry no digit.

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

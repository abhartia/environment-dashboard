# Working in this repo

Environment Dashboard lets the public drill down from the causes of climate change, through its consequences, to what
can be done. It is a **dashboard, not a set of articles**: each chapter (`/emissions`, `/energy`, `/air`, `/heat`,
`/oceans`, `/people`, `/food`, `/action`) shows one idea at a time as one big traced number and one animated chart, and
each choice splits it one more way (`docs/dashboard.md`). **Every number on the site must be traceable to its primary source**: the publisher, dataset version,
exact file, fetch date, sha256, the transformation applied, and the licence. That promise is what the code protects.

| | |
|---|---|
| `pipeline/` | Python (uv). Fetches sources, snapshots raw bytes, transforms, validates, and exports to `data/`. The only door data comes through. |
| `data/` | Pipeline output, committed. Never edit by hand. |
| `web/` | Next.js 16 static export on Cloudflare Pages. Renders `data/`; never computes a published number itself. |
| `docs/` | `runbook.md` (setup and operations), `sources.md` (source registry rules and decisions), `licensing.md`, `style.md` (voice), `dashboard.md` (how chapters and drill-downs work), `research/` (dated evidence). |

## Rules

1. **Static export.** `web/` is Next.js 16 with `output: "export"`. Read `web/AGENTS.md` and
   `web/node_modules/next/dist/docs/` before changing Next code. No `headers()`, `redirects()`, rewrites, proxies or
   server actions. Metadata and GET route handlers need `export const dynamic = "force-static"`. Headers live in
   `web/public/_headers`; host redirects are Cloudflare rules.
2. **UI is shadcn/ui.** Client-side data goes through the generated TanStack Query `queryOptions` factories over
   `/data/v1/*` (`npm run gen:api` after any change to `pipeline/schema/openapi.json`). Content pages render on the
   server and do not ship the query runtime.
3. **Never type a data number in TSX or MDX.** Use `<Num id="…"/>`, which renders from `data/` and links to the
   number's provenance. Prose that asserts a rank, record or threshold declares it in frontmatter `claims`, which
   tests evaluate against the current data.
4. **Never hand-edit `data/`.** Run `cd pipeline && uv run envdash build`.
5. **New source = licence first.** Add a `docs/sources.md` entry and `pipeline/sources/<id>.yaml` with `terms_url`,
   a verbatim `licence_quote` and `checked_on` before writing any fetch code. If the terms forbid what we need,
   record it under Rejected with the clause and stop. Assign the licence class from the producer's own terms, never
   from an aggregator's metadata (OWID, HDX).
6. **Licence classes decide behaviour.** `no-derivatives` and `display-only` values never go into `data/`, a
   download, an RSC client prop, the public R2 bucket or a Zenodo deposit. check-build enforces this.
7. **No scraping workarounds.** If a host blocks automated access, a person downloads the file and records it with
   `uv run envdash snapshot add --source <id> --file <path>`.
8. **No heuristic fallbacks.** No interpolation, no default values, no substituting another source or a regional or
   world value for a missing one. A failed source keeps its last validated vintage and says so; the UI says
   "No data for X in <source>".
9. **Fixtures are real.** Test fixtures are byte-exact slices of real snapshots of open-licence sources, each with a
   `.provenance.json` sidecar (full-file sha256, URL, date accessed, rows kept, the slicing command). Hand-written
   fixtures are forbidden. Never add mock or invented data anywhere.
10. **Secrets live in the macOS Keychain** and reach CI only as GitHub secrets piped from it. Service names and the
    mapping to secret names are in `docs/runbook.md`.
11. **Dashboard nodes only select and label.** A chapter tree (`web/src/lib/dash/<chapter>-tree.ts`) picks published
    observations through `lib/dash/kit.ts`; it never computes a value. Its sentence carries no typed data number, and
    a kicker that asserts something ("X is the largest source") is derived from the data or checked by the tree so
    a refresh that falsifies it fails the build. Node files are public downloads, so the kit refuses `no-derivatives`
    and `display-only` indicators.
12. **Voice** follows `docs/style.md`: plain words, units spelled out, options described by their measured effect
    and range, never in the imperative. No "live" or "real-time" claims. **No financial advice**: no savings,
    payback, tariff or investment guidance.

## Commits

No branches or PRs: a push to `main` is a release. Verify locally first (`uv run pytest`, `npm run typecheck`,
`npm run lint`, `npm test`, `npm run build`). Commit subjects are sentence case with no prefix; bodies explain why,
with the numbers that motivated the change.

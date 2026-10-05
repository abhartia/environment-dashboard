# Environment Dashboard: platform, provenance and visualization research (verified 2026-10-04)

All facts below were checked on the web today unless marked otherwise. Bundle sizes are my own measurements: I downloaded each library's published bundle from jsDelivr and compressed it with `gzip -9`.

## 0. How the sibling repos are built
- **gigabiome** is the closest match. `gigabiome/web/next.config.ts` uses `output: "export"`, `images: { unoptimized: true }` and MDX. A comment in that file says the static site is on Cloudflare Pages, the API is FastAPI on Cloud Run, headers live in `public/_headers`, and the www-to-apex redirect is a Cloudflare redirect rule.
- **Shared stack across gigabiome, simmerlist and wadecv:** Next 16.3.x, `@tanstack/react-query` ^5.104, the shadcn CLI ^4.21, `radix-ui`, Tailwind 4, recharts ^3.10.1, vitest 5 and next-themes. wadecv adds Playwright plus build-time check scripts such as `check-canonicals`, `check-host-redirect` and `check-cache-headers` (see `wadecv/frontend/package.json`).
- **Gotcha for file limits:** gigabiome's export (`gigabiome/web/out`) has 205 files for 25 HTML routes, including 119 `.txt` RSC payload files. That is roughly 5 `.txt` files per route. Cloudflare's free tier allows 20,000 files per deploy, so about 3,000 static routes is the practical ceiling. Do not pre-render every country × indicator page. Use one route per indicator, put the country in the query string, and fetch the data as JSON or Parquet.

## 1. Cloudflare

**Pages vs Workers Static Assets**
- Cloudflare now recommends Workers for new projects. The Pages docs banner says: "It is Cloudflare's primary platform for building applications. Start new projects with Workers." (https://developers.cloudflare.com/pages/)
- The April 8, 2025 blog post says: "you should start with Workers" and "all of our investment, optimizations, and feature work will be dedicated to improving Workers." Pages is still supported. (https://blog.cloudflare.com/full-stack-development-on-cloudflare-workers/)
- Features only Workers has: Cron Triggers, Tail Workers and gradual deployments. Features only Pages has: native Early Hints, custom domains outside Cloudflare zones, and branch-deploy controls. (https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/)

**Workers Static Assets**
- Requests to static assets are free and unlimited: "Requests to static assets are free and unlimited." (https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)
- If you use `run_worker_first`, matching requests run the Worker and count against the request quota. Over the free quota they get a 429 response.
- File limits: 20,000 files per version on free, 100,000 on paid. Each file can be at most 25 MiB. A Worker script can be at most 64 MiB. (https://developers.cloudflare.com/workers/platform/limits/)
- `_redirects`: up to 2,000 static plus 100 dynamic redirects. Redirects to a different domain are not supported. (https://developers.cloudflare.com/workers/static-assets/redirects/)
- `_headers`: up to 100 rules, 2,000 characters per line. These headers apply only to static asset responses. (https://developers.cloudflare.com/workers/static-assets/headers/)
- `html_handling` options are `auto-trailing-slash` (the default), `force-trailing-slash`, `drop-trailing-slash` and `none`. (https://developers.cloudflare.com/workers/static-assets/routing/advanced/html-handling/)

**Pages free tier** (https://developers.cloudflare.com/pages/platform/limits/)
- 500 builds per month, 1 build at a time, 20-minute build timeout.
- 20,000 files per site, 25 MiB per file.
- 100 custom domains, 100 projects.
- Pages Functions requests count against the Workers quota.

**Workers Builds** (Cloudflare's built-in CI) (https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/)
- Free: 3,000 build minutes per month, 1 build at a time, 20-minute timeout, 2 vCPU, 8 GB RAM.
- Paid: 6,000 minutes, then $0.005 per minute.
- Deploying with wrangler from GitHub Actions does not use these minutes.

**Workers free vs paid** (https://developers.cloudflare.com/workers/platform/limits/ and https://developers.cloudflare.com/workers/platform/pricing/)
- Free: 100,000 requests per day, 10 ms CPU per invocation, 50 subrequests, 5 Cron Triggers per account, 100 Workers.
- Paid costs $5/month minimum. It includes 10M requests per month (then $0.30 per million) and 30M CPU-ms per month (then $0.02 per million CPU-ms). It allows 30 s default and 5 min maximum CPU per request, up to 15 minutes of CPU per cron run, 250 cron triggers and 10,000 subrequests.

**Cron Triggers** (https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- They run in UTC and can fire as often as every minute.
- Changes can take up to 15 minutes to propagate.
- On the free plan the 10 ms CPU limit makes them useless for data processing. Run the data pipeline in GitHub Actions instead.

**When you would need Workers Paid ($5):** only if you need more than 20,000 files per deploy, more than 100,000 dynamic Worker requests per day (for example a Worker proxying PMTiles map tiles), or more than 10 ms CPU. A pure static site does not need it.

**R2 storage** (https://developers.cloudflare.com/r2/pricing/)
- Free each month: 10 GB-month of storage, 1M Class A operations (writes), 10M Class B operations (reads). Egress is free.
- Paid rates: $0.015 per GB-month, $4.50 per million Class A, $0.36 per million Class B. Infrequent Access storage is $0.01 per GB-month plus a $0.01/GB retrieval fee.
- The free tier covers Standard storage only.
- The `r2.dev` public URL "is rate-limited and should only be used for development purposes". For production, put the bucket behind a custom domain to get caching and WAF. (https://developers.cloudflare.com/r2/buckets/public-buckets/)

**Web Analytics**
- It is free and cookieless: it "does not use any client-side state, such as cookies or localStorage" and does not fingerprint visitors. (https://www.cloudflare.com/web-analytics/)
- There is a soft limit of 10 sites per account, and 6 months of data are viewable. Raw beacons are kept for 7 days, then aggregated to about 10%. Sampling is applied at query time. (https://developers.cloudflare.com/web-analytics/faq/)

**Redirects on the free plan** (https://developers.cloudflare.com/rules/url-forwarding/)
- 10 Single Redirect rules per zone.
- Bulk Redirects: 15 rules, 5 lists, 10,000 URLs per account.
- Pattern for two domains: a single wildcard rule in the `.org` zone. Match `http*://environmentdashboard.org/*` and send a 301 to `https://environmentdashboard.com/${2}`, keeping the query string. (https://developers.cloudflare.com/rules/url-forwarding/examples/redirect-all-another-domain/)
- The `.org` apex needs a proxied DNS record, or else attach it to the Worker as a Custom Domain and redirect in a rule.
- Both zones must be on the same Cloudflare account to use Worker Custom Domains, and Cloudflare creates the DNS records and certificates. (https://developers.cloudflare.com/workers/configuration/routing/custom-domains/) The docs do not say explicitly that one Worker can hold Custom Domains in several zones.
- Pick one canonical domain. `.org` suits a non-commercial site better, but that is the owner's call.

**Domain costs** if the domains are moved to Cloudflare Registrar, which charges at cost (https://www.cloudflare.com/products/registrar/)
- About $10.46/yr for .com and $11.20/yr to renew .org. These are third-party price listings, not from Cloudflare: https://startupowl.com/reviews/cloudflare-registrar, https://tldes.com/registrars/cloudflare
- That works out to roughly $1.80/month.

**Estimated total cost:** about $2/month on the free tiers, or about $7/month if Workers Paid is ever needed. Both are well under the $20 budget.

## 2. GitHub Actions
- **Included minutes and storage for private repos** (https://docs.github.com/en/billing/concepts/product-billing/github-actions)
  - Free: 2,000 minutes/month and 500 MB artifact storage.
  - Pro: 3,000 minutes/month and 1 GB.
  - Linux runner overage is $0.006/min after the Jan 1, 2026 price cuts of 15–39%.
- **Public repos:** "The use of standard GitHub-hosted runners is free: In public repositories."
- **Self-hosted runner fee:** a $0.002/min fee was announced for March 2026, then postponed indefinitely. (https://github.com/resources/insights/2026-pricing-changes-for-github-actions, https://samexpert.com/github-actions-pricing-backlash-2026/)
- **Job limits:** a job can run up to 6 hours. Free accounts get 20 concurrent jobs, Pro gets 40. Cache is limited to 10 GB per repo. (https://docs.github.com/en/actions/reference/limits)
- **Large files** (https://docs.github.com/en/billing/concepts/product-billing/git-lfs, https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
  - Git LFS: 10 GiB storage and 10 GiB bandwidth free.
  - GitHub warns on files over 50 MiB and blocks files over 100 MiB. Repos should stay under 1 GB, and under 5 GB is "strongly recommended".
  - So raw source snapshots belong in R2 or Zenodo, not in git.
- **Scheduled (cron) workflows** (https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
  - Minimum interval is 5 minutes.
  - Runs can be delayed under load, especially at the top of the hour, and "some queued jobs may be dropped". Schedule at odd minutes such as `17 4 * * *`.
  - They run only on the default branch.
  - IANA timezones are supported.
  - "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." A data-commit bot counts as activity, or add a keep-alive.
- **Making the repo public** makes Actions minutes free. It is also required for Zenodo's GitHub integration (section 3), and it strengthens the "anyone can trace it" goal.

## 3. Provenance tooling

**Frictionless Data Package v2.0**
- Released June 26, 2024. It has four specs: Data Package, Data Resource, Table Dialect and Table Schema. (https://datapackage.org/)
- What v2 changed (https://datapackage.org/overview/changelog/):
  - `$schema` replaces `profile`, and `version` is now official.
  - New: `source.version`; `contributors[].roles`; `fieldsMatch`; `categories`; per-field `missingValues`; `uniqueKeys`; the `list` type.
  - Parquet is now a valid encoding.
- Package fields: `id` (DOI or UUID), `version` (semver), `created` (RFC3339), `licenses`, `contributors` and `resources`. Each `sources` entry has `title` (required), `path`, `email` and `version`. (https://datapackage.org/standard/data-package/)

**W3C PROV**
- Recommendation since 30 April 2013. The model is Entity, Activity and Agent, linked by `wasGeneratedBy`, `used`, `wasDerivedFrom`, `wasAttributedTo` and `wasAssociatedWith`. Formats are PROV-O (RDF), PROV-N and PROV-XML. (https://www.w3.org/TR/prov-overview/)
- PROV-JSON is a 2013 W3C Member Submission. That is from my memory, not checked today.
- Practical use here: describe each build as an Activity that `used` source-file Entities with a sha256, plus a git commit, and `wasAssociatedWith` the pipeline Agent.

**Zenodo**
- Free. "Total files size limit per record is 50GB." Records are kept for "the lifetime of the host laboratory CERN … next 20 years at least". Withdrawn records leave a tombstone page, and the DOI and URL are kept. (https://about.zenodo.org/policies/)
- REST API (https://developers.zenodo.org/):
  - Uses a personal token with `deposit:write` and `deposit:actions` scopes.
  - 50 GB and up to 100 files per record.
  - Rate limits: 100 requests/min and 5,000/hour authenticated; 60/min and 2,000/hour as a guest.
  - A sandbox exists at sandbox.zenodo.org (DOI prefix 10.5072).
- The GitHub integration (DOI minted on each release) works with public repos only. (https://github.com/zenodo/zenodo/issues/407, https://support.zenodo.org/help/en-gb/24-github-integration/127-which-github-permissions-do-you-request-and-why)
- For dataset snapshots, use the API "new version" flow. The `zenodraft/action` GitHub Action reads `ZENODO_ACCESS_TOKEN` and can create a new version under an existing concept DOI. (https://github.com/marketplace/actions/zenodraft)
- Each release gets a version DOI. The concept DOI always points to the latest version.

**Internet Archive Save Page Now (SPN2)**
- How it works (https://gist.github.com/regstuff/82e690db2f1d91ba59f6681c1abad6cf):
  - Send `POST https://web.archive.org/save` with header `Authorization: LOW accesskey:secret`. Keys come from https://archive.org/account/s3.php.
  - Useful options: `if_not_archived_within`, `skip_first_archive`, `capture_all`, `capture_outlinks` and `js_behavior_timeout` (up to 30 s).
  - Check progress with `GET /save/status/{job_id}`.
  - Limits: 12 concurrent captures authenticated (6 anonymous); 100,000 captures/day authenticated (4,000 anonymous); 10,000 per host per day.
- The per-URL daily limit is inconsistent in the docs (10 vs 5). A user observed 1 per day "for that Resource type", and refusals come back as HTTP 200 with no `job_id`. (https://github.com/internetarchive/wayback/issues/305, filed 2026-09-28)
- Use it to archive source landing and methodology pages. Do not rely on it for large data files: store those yourself in R2 with a sha256, and in Zenodo.

**Software Heritage**
- Archives public repositories via Save Code Now. (https://www.softwareheritage.org/save-and-reference-research-software/)
- SWHIDs (`swh:1:rev:`, `swh:1:dir:` and so on) are content-hash identifiers, standardized as ISO/IEC 18670:2025 on 2025-04-23. (https://www.swhid.org/news/2025-04-23-swhid-standardized-as-iso-iec-18670/)
- API limits: 120 requests/hour anonymous, 1,200/hour with a token. (https://docs.softwareheritage.org/_modules/swh/web/api/throttling.html)
- The API pages were behind an Anubis bot-check when I fetched them.

**Checksums**
- Record a sha256 for every raw download, plus size, `date_accessed`, HTTP `ETag` and `Last-Modified`, and the exact `url_download`.
- Publish a `SHA256SUMS` file per release so anyone can check it with `sha256sum -c`.
- Protomaps publishes BLAKE3 hashes for its builds, the same idea. (https://docs.protomaps.com/basemaps/downloads)

**What to borrow from Our World in Data's ETL**
- **Pipeline stages:** snapshot, then meadow, then garden, then grapher. Snapshots are "edge nodes" with no dependencies, tracked with DVC under URIs like `snapshot://<namespace>/<version>/<file>`. (https://docs.owid.io/projects/etl/architecture/design/phases/)
- **`origin` fields** (https://docs.owid.io/projects/etl/architecture/metadata/reference/):
  - Required: `producer`, `title`, `citation_full`, `url_main`, `date_accessed` (YYYY-MM-DD), `date_published`, `license.name`.
  - Optional: `description`, `title_snapshot`, `description_snapshot`, `attribution`, `attribution_short`, `version_producer`, `url_download` (must be a direct download link), `license.url`.
- **Indicator fields:** `title`, `unit`, `short_unit`, `description_short`, `description_key`, `description_from_producer`, `description_processing`, `processing_level` (minor or major), `presentation` and `origins[]`.
- **Public endpoints:** `/grapher/{slug}.csv`, `.metadata.json` (includes `dateDownloaded` and citations) and `.zip` (CSV, metadata and README). (https://docs.owid.io/projects/etl/api/chart-api/)
- **Very recent changes:**
  - PR #6860, merged 2026-09-30, generates per-table codebook, sources, README and `manifest.json` from metadata, and deliberately avoids claiming a dataset-level license. (https://github.com/owid/etl/pull/6860)
  - PR #6943, merged 2026-10-02, puts provenance (`origins`, `attribution`, `updatePeriodDays`) into each feed's `<slug>.metadata.json`. (https://github.com/owid/etl/pull/6943)
- owid/etl is MIT-licensed.
- **Recommended approach:** copy the Origin schema field for field, adding `sha256`, `bytes`, `wayback_url` and `zenodo_doi`. Store it in a Frictionless `datapackage.json` per dataset, with a short PROV-style list of processing steps (script path, git SHA, inputs → outputs). Every number on the site should link to `/data/{indicator}` showing the value, unit, year, origin, processing description, raw-file hash, archived copies, and download buttons for CSV, JSON and the data package.

## 4. Browser data and visualization stack
This is for Next.js 16 static export (`output:'export'`). Unsupported in that mode: redirects, rewrites, headers, proxy, ISR, cookies, Server Actions, dynamic routes without `generateStaticParams`, and the default image loader. GET Route Handlers with `force-static` do work, which allows build-time JSON. (https://nextjs.org/docs/app/guides/static-exports, docs v16.3.8)

**Latest versions** (npm registry, checked today) and sizes (gzip):

| Library | Version, license | Gzip size | Notes |
|---|---|---|---|
| recharts | 3.10.1 (2026-07-25), MIT | ~151 KB (UMD) | shadcn chart now uses Recharts v3, registry pins 3.8.0 ([docs](https://ui.shadcn.com/docs/components/chart)). Migration: `var(--chart-1)` not `hsl(...)`; give ChartContainer a `min-h-*` or `aspect-*`. `accessibilityLayer` is on by default in v3 ([guide](https://github.com/recharts/recharts/wiki/3.0-migration-guide)). Already used in gigabiome and wadecv. Best for standard line, bar and area charts. |
| @observablehq/plot | 0.6.17 (Feb 2025), ISC | ~67 KB + d3 (~90 KB full) | Best for fast, expressive exploratory charts (small multiples, faceting, stripes). Last release was in Feb 2025. |
| @visx/* | 4.0.0 (2026-06), MIT | tree-shaken | Low-level React plus d3, full design control. |
| echarts | 6.1.0 (2026-05), Apache-2.0 | 359 KB full, 165 KB "simple" | Tree-shakable. Heavy. Does not match shadcn styling well. |
| d3 | 7.9.0, ISC | 90 KB | Import only the needed `d3-*` modules. |
| maplibre-gl | 6.12.0, BSD-3 | ~148 KB + 81 KB CSS | v6.0 (2026-07-22) is ESM-only and requires WebGL2: `import * as maplibregl` ([malagis](https://geo.malagis.com/maplibre-gl-js-v6-mandatory-webgl-and-esm-only.html)). Upgrade to ≥6.11.2 for XSS advisory GHSA-jrc7-96c5-q579. Must load client-only (`dynamic(..., {ssr:false})`). |
| pmtiles | 4.5.0, BSD-3 | 7 KB | |
| @protomaps/basemaps | 5.7.2, BSD-3 | | Styles are BSD-3. Map data is OpenStreetMap under ODbL, so OSM attribution is required. Planet file is ~120 GB. Use `pmtiles extract` to cut it down by zoom level ([docs](https://docs.protomaps.com/basemaps/downloads)). |
| deck.gl | 9.4.0, MIT | 561 KB full | Only worth it for gridded layers (heatmaps of temperature anomalies). |
| @duckdb/duckdb-wasm | 1.33.1-dev57.0, MIT | eh.wasm ~7.7 MB, worker 183 KB | Full SQL in the browser, but very heavy for a "simple" site. Multithreading needs COOP/COEP headers. |
| @uwdata/mosaic + vgplot | 0.32.0, BSD-3 | | DuckDB-backed linked views. |
| arquero | 8.0.3, BSD-3 | 72 KB | |
| apache-arrow | 21.2.0, Apache-2.0 | 50 KB | |
| hyparquet | 1.31.2 (2026-09-27), MIT | 19 KB | Dependency-free. Reads Parquet over HTTP range requests and can select columns. Snappy built in; other codecs via `hyparquet-compressors` ([repo](https://github.com/hyparam/hyparquet)). Best lightweight drill-down option. |
| parquet-wasm | 0.9.0 | 1.6 MB | |
| vega-lite | 6.4.3 | 77 KB (plus vega) | |

Dates in parentheses are npm release dates.

**Map tiles from R2**
- PMTiles can be served straight from an R2 custom-domain bucket using HTTP range requests, with no Worker. Each tile request counts as a Class B read. CORS needs GET and HEAD with `range` and `if-match` headers. (https://docs.protomaps.com/pmtiles/cloud-storage)
- The Protomaps Worker recipe needs a custom domain for caching, and its docs point to Workers Paid for production traffic. (https://docs.protomaps.com/deploy/cloudflare)
- R2 latency is "500ms or higher" on cache misses.
- A choropleth with low zoom can skip a basemap entirely: use country boundaries as TopoJSON or GeoJSON plus d3-geo.

**Scrollytelling**
- scrollama 3.2.0 is about 2 KB but was last released in 2022. react-scrollama is 2.4.2.
- GSAP 3.15 including ScrollTrigger has been free under the "Standard no-charge" license since April 2025, including commercial use. It is not OSI open source. (https://css-tricks.com/gsap-is-now-completely-free-even-for-commercial-use/)
- motion 14.0.0 (MIT, 2026-10-02) has `useScroll`.
- CSS scroll-driven animations (`animation-timeline`) ship in Chrome 115+ and Safari 26, but Firefox has them only in "preview" (Nightly), per MDN browser-compat-data 8.1.4 (2026-10-01, https://www.npmjs.com/package/@mdn/browser-compat-data). Some blogs claim Firefox shipped them in 132; MDN contradicts that.
- View Transitions: Chrome 111, Firefox 144, Safari 18.
- So use CSS scroll animation only as progressive enhancement, inside `@supports` and `prefers-reduced-motion`.

**Chart accessibility**
- Use Chartability (POUR+CAF, 50 heuristics) as the audit checklist. (https://github.com/Chartability/POUR-CAF, https://www.frank.computer/chartability/)
- Keep Recharts' `accessibilityLayer` on.
- Every chart should have a visible "Show data table" toggle (shadcn Table), a written key takeaway, an `aria-describedby` summary, colour-blind-safe palettes, and no meaning carried by colour alone.
- Respect `prefers-reduced-motion`.
- The Observable Plot accessibility page returned HTTP 429, so it is unverified. From memory, Plot supports `ariaLabel`, `ariaDescription` and `ariaHidden`.

**Recommendation**
- Use Recharts through shadcn for 90% of charts, Observable Plot for warming stripes and small multiples, MapLibre v6 plus PMTiles for maps (or d3-geo for simple choropleths), and hyparquet or plain JSON fetched through TanStack Query for drill-down data.
- Avoid DuckDB-WASM and deck.gl unless a specific view needs them, and load them lazily if so.

## 5. Existing climate dashboards: what to learn from
- **OWID** (https://ourworldindata.org/co2-and-greenhouse-gas-emissions)
  - Borrow: explorer dropdowns (gas × metric × per-capita/total/cumulative × production/consumption), chart/map/table tabs, a "Sources & download" block with full citation and BibTeX, CC BY licensing, and the `.csv` / `.metadata.json` / `.zip` endpoint pattern.
  - Avoid: 158+ charts in one grid, which is overwhelming.
- **Climate Pulse (C3S/ECMWF)** (https://pulse.climate.copernicus.eu/, https://climate.copernicus.eu/climate-pulse-tool-take-temperature-our-planet-glance)
  - Two variables only (2 m air temperature and sea surface temperature) from ERA5, about 2 days behind real time, anomalies against 1991–2020, CSV and image downloads. ERA5 is CC BY 4.0.
  - Borrow: tight focus, a stated baseline, and labelling of preliminary data.
- **Climate Reanalyzer** (https://climatereanalyzer.org/clim/t2_daily/)
  - Daily ERA5 from 1940 with a 6-day lag. Every year is overlaid on one chart. Two baselines (1979–2000 and 1991–2020).
  - Public JSON at `/clim/t2_daily/json/era5_world_t2_day.json`, as an array of `{data_source, name: year, data: [...]}`.
  - Borrow its explicit caveat: record values "should be considered with caution and validated against weather station observations."
- **Show Your Stripes** (https://github.com/ed-hawkins/show-your-stripes)
  - CC BY 4.0, "Licensor: Professor Ed Hawkins, University of Reading, UK". The stripes may be reproduced or regenerated with credit and a link to showyourstripes.info.
  - Source datasets include Berkeley Earth, the UK Met Office, NOAA, DWD and others.
  - A strong "one glance" entry point. Pair it with the numbers it encodes.
- **Global Carbon Atlas** (https://globalcarbonatlas.org/)
  - Map plus chart of country fossil and land-use CO₂, from the Global Carbon Budget.
  - Its homepage still cited the 2023 edition. Lesson: show the data vintage prominently and keep it current.
  - Latest data: GCB 2025 (ESSD 18, 3211, 2026). It projects fossil CO₂ at 38.1 GtCO₂ in 2025 (+1.0%), atmospheric CO₂ at 425.7 ppm, and a remaining 1.5 °C budget of 170 GtCO₂, about 4 years at current emissions. (https://essd.copernicus.org/articles/18/3211/2026/, https://globalcarbonbudget.org/fossil-fuel-co2-emissions-hit-record-high-in-2025/)
- **Ember Electricity Data Explorer** (https://ember-energy.org/data/electricity-data-explorer/)
  - 215 geographies, 2025 annual data for 91 countries (93% of global demand), monthly data for 88, updated twice a month. CC BY 4.0, with an API and a methodology PDF.
  - The best model for the "what can be done" side (the power mix).
- **Carbon Brief "Mapped: how every part of the world has warmed"** (https://www.carbonbrief.org/mapped-how-every-part-of-the-world-has-warmed-and-could-continue-to-warm)
  - 1°×1° grid. Click a cell to get its history (annual plus 10-year smoothing) and projections under RCP scenarios, against a 1951–1980 baseline.
  - The best "consequences, near me" pattern.
- **Copernicus climate indicators** (https://climate.copernicus.eu/climate-indicators)
  - 12 indicators: global, European and Arctic temperature; glaciers; Greenland ice sheet; Arctic sea ice; CO₂; CH₄; sea level; sea surface temperature; ocean heat content. Updated at least yearly.
  - A good checklist for the "consequences" section.
- **NASA Vital Signs** (https://climate.nasa.gov/vital-signs/global-temperature/, https://science.nasa.gov/climate-change/evidence/)
  - CO₂, temperature, methane, Arctic sea ice minimum, ice sheets, sea level, ocean warming. A single big number per indicator with a trend line.
  - Content is partly duplicated between climate.nasa.gov and science.nasa.gov. Cite the stable underlying datasets (GISTEMP, NOAA GML and so on), not NASA's summary pages.

**Patterns that create clarity:** one idea per screen; big number → trend → "why" → "what you can do"; a stated baseline; uncertainty shown; a "data as of" date; one click from any number to its source.

**Patterns to avoid:** dashboards packed with dozens of tiles; mixed baselines without labels; stale vintages; charts with no table fallback; maps without OSM or source attribution; citing secondary summary pages instead of primary data.
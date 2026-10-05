# environmentdashboard.org

A public, non-commercial site for exploring climate data: what is causing climate change, what it is doing, and what
can be done. Every number on the site links to where it came from: the producer, the dataset version, the exact file,
when it was fetched, its sha256, what was done to it, and its licence.

| | |
|---|---|
| `pipeline/` | Python (uv): fetch → snapshot (R2 + Wayback) → transform → validate → export to `data/` |
| `data/` | The published numbers and their provenance (generated; each file carries its own licence) |
| `web/` | Next.js 16 static export (Tailwind v4, shadcn/ui, TanStack Query, MDX) on Cloudflare Pages |
| `docs/runbook.md` | Setup, deploy and day-to-day operations |
| `docs/sources.md` | Which sources we use, which we rejected, and why |
| `docs/research/` | The dated research behind the source choices |

## Quick start

```bash
cd pipeline && uv sync && uv run pytest
cd web && npm ci && npm run dev -- --port 3200
```

Tests: `cd pipeline && uv run pytest` · `cd web && npm run typecheck && npm run lint && npm test && npm run build`.

## Licences

- Code: MIT (`LICENSE`).
- Site text: CC BY 4.0 (`LICENSE-CONTENT`). Figures and data carry the licence named under each view and on its
  data page, and in `data/datapackage.json`, which follows each producer's terms.
- Producers and their required credits: `NOTICE` and each page under `/sources`.

## Report a problem with a number

Open an issue with the **Data problem** template, or use the email address on the site. Say which number and page;
the number's link opens its provenance page, which has its id.

# Research snapshot, 2026-10-04

The evidence behind the source choices in `pipeline/sources/` and `docs/sources.md`. It was collected before any code
was written, by parallel research agents that searched the web and fetched each landing page, licence page and
download URL. An independent agent then re-checked each domain's findings.

| File | What it holds |
|---|---|
| `sources-<domain>.json` | `research`: the sources found for one domain. Each entry has publisher, coverage, latest release, download URLs, licence with quoted terms, recommended citation and DOI, status (including US federal funding risk) and what the fetch returned. `verification`: the second agent's verdict per source (`confirmed` / `corrected` / `refuted`), with corrected licence class and priority, plus checks of the headline numbers and sources the first pass missed. |
| `platform.md` | Cloudflare, GitHub Actions, Zenodo, Internet Archive and visualisation-library facts and limits, with URLs. |
| `plan-critique-2026-10-04.txt` | The adversarial review of the build plan (licensing, architecture, operations, UX, completeness) whose fixes the plan adopted. |

This is a dated snapshot, not the source of truth. A source's licence class is decided in
`pipeline/sources/<id>.yaml`, which must quote the terms it relies on (`licence_quote`) and link them (`terms_url`).
Where a verdict here says `corrected`, the corrected value is the one to start from.

## Known corrections

The JSON files are kept exactly as collected on 2026-10-04; corrections found later are listed here instead of
editing them.

- `sources-impacts.json`, Lancet Countdown indicator 1.1.5 (heat-related deaths): the note accepts the report's
  "up 63.2%", but that figure does not follow from the workbook it cites. The 2012–2021 mean of column AN, 545,478,
  against the 1990–1999 mean, 334,690, is a ratio of 1.6298, i.e. +62.98% (+63.0% to one decimal). Found by the
  wave-1 audit; quote the report's 63.2% only as the report's own statement, never as derived from the workbook.

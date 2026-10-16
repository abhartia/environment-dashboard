# Research snapshot, 2026-10-04

The evidence behind the source choices in `pipeline/sources/` and `docs/sources.md`. It was collected before any code
was written, by parallel research agents that searched the web and fetched each landing page, licence page and
download URL. An independent agent then re-checked each domain's findings.

| File | What it holds |
|---|---|
| `sources-<domain>.json` | `research`: the sources found for one domain. Each entry has publisher, coverage, latest release, download URLs, licence with quoted terms, recommended citation and DOI, status (including US federal funding risk) and what the fetch returned. `verification`: the second agent's verdict per source (`confirmed` / `corrected` / `refuted`), with corrected licence class and priority, plus checks of the headline numbers and sources the first pass missed. |
| `platform.md` | Cloudflare, GitHub Actions, Zenodo, Internet Archive and visualisation-library facts and limits, with URLs. |
| `sources-ghg-food-personal-2026-10-05.json` | 2026-10-05 follow-up to the owner's feedback ("food is 31.7% but not in where emissions come from"; "per food"; "per person" meaning a personal footprint). `research`: one pass each for all greenhouse gases by sector, emissions by food stage and product, and personal footprints. `verification`: an independent skeptic's verdict per candidate (`adopt` / `adopt-with-changes` / `reject`) with what it re-derived from the raw files. |
| `sources-zero-*-2026-10-08.json` | 2026-10-08, for the owner's request to represent the frameworks of Bill Gates's *How to Avoid a Climate Disaster* (2021). `sectors`: all greenhouse gases split finely enough to group into his five activities, and how Rhodium Group built his shares. `green-premium`: clean and fossil costs on one basis, by activity. `space-and-power`: land per unit of electricity, and the scale from a home to the world. `levers-and-adaptation`: net-zero targets, electrification, carbon capture, research budgets, policy databases, adaptation finance and smallholder farms. Each candidate quotes its licence from the producer with the date it was read; `open_questions` lists what needs the owner or a producer. `green-premium-papers` holds the helper agents' findings on transport, heating, food and ammonia papers and on IPCC WGIII data. |
| `sources-consequences-2026-10-11.json` | 2026-10-11, for the owner's "so what" request: the site showed CO2, temperature, sea level and ice without saying what they mean for people. `research`: one pass per domain (coasts, disasters and displacement, heat and health, warming-level futures, food and water, fossil-fuel air pollution), each candidate with its producer's licence quoted verbatim, real values read from the files and a plain-words phrase. `verification`: an adversarial re-read of each strong candidate's terms and data (`confirmed` / `corrected` / `refuted`). `critic`: what was still missing or wrongly accepted. |
| `sources-extremes-2026-10-12.json` | 2026-10-12, for the owner's request to highlight extreme weather and disasters becoming more frequent because of climate change. Four angles (frequency per degree of warming, observed long series, the toll of disasters on people, attribution), adversarial verification with `honest_wording` (what the site may and may not say with each dataset), and a critic on what must never be claimed (recorded disaster counts track reporting; no trend in storm numbers or global floods). |
| `future-mode-2026-10-16.json` | 2026-10-16, for the owner's request for a "future" mode: a world map where each country, and each state or province where there is data, shows what the climate models project for an average resident. Projection sources (World Bank CCKP's CMIP6 values by country and region; IIASA's Climate Solutions Explorer as the population-weighted follow-up), boundary files and how CCKP's region codes join them (World Bank GAD V1 by code and name; v3, Natural Earth, geoBoundaries and GADM do not), the decisions taken, the corrections below and the questions left open. |
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
- `sources-country-and-local.json`, lines 9 and 25: CCKP's region values do not "line up exactly" with the World
  Bank's Official Boundaries as published now (version 3): its admin-1 codes do not rebuild CCKP's, and only 2,210 of
  CCKP's 3,500 named regions match by name. It is the earlier GAD V1 (2025-05-07, on CCKP's own bucket) that CCKP's
  codes rebuild, by two code rules and then by name, not exactly (`future-mode-2026-10-16.json`, `corrections`).

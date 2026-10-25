# Depth backlog

Ranked candidates for the weekly run's one layer of depth (`docs/dashboard.md`, AGENTS.md). Each says the question it
answers, the source and its licence class, the node it hangs off, and its status. Seeded on 2026-10-11 from the dead
ends in `web/src/lib/dash/*-tree.ts`, the research files in `docs/research/` and `data/v1/status.json`.

Status: `todo`, `blocked (<why>)`, `done <date>`, `owner` (needs the owner: a new chapter, a licence email, a download).

## Gaps the site already admits

| # | Question | Source (class) | Node | Status |
|---|---|---|---|---|
| G1 | How much international public money reaches adaptation (the fourth AGR indicator) | unep-agr-2025 online annexes PDF (noncommercial) | zero adaptation nodes | owner: download `AGR2025_Online_Annexes.pdf` by hand (runbook step 4) |
| G3 | Wildlife populations to 2022 (Living Planet Report 2026) | living-planet-index (share-alike; terms re-read 2026-10-11) | `/food` species nodes | owner: download the nine trend CSVs, then adopt and update the citation |
| G4 | Keep electric car shares fetchable | iea-gevo-2026 evs-historical (open) | `/energy?v=ev` and below | done 2026-10-18: the IEA moved the route to `api.iea.org/electric-vehicles` (same bytes) |
| G2 | Heat-related deaths after 2021 | Lancet Countdown 2026 report, when released (noncommercial) | `/people` heat deaths | todo: not out on 2026-10-25 (explore-our-data lists only the 2025 workbooks; a UCL event in October marks the 10th report); check again |
| G5 | Food and all-sector emissions to 2024 (FAOSTAT October 2026 release) | faostat (open), faostat-all-sectors (noncommercial) | `/emissions`, `/food` | todo: on 2026-10-25 FAO's catalogue disagreed with the GT zip (2,415,025 vs 2,500,090 rows), so GT failed; adopt when both are the new release |

## Dead ends answerable from data already published

| # | Question | Source (class) | Node | Status |
|---|---|---|---|---|
| D1 | Where are electric cars the largest share of new cars, and how has each of those countries moved? | `ev.iea.sales-share` (open) | `/energy?v=ev` | done 2026-10-11 |
| D2 | What does each of the largest energy users run on? (bars → country by fuel) | `energy.eia.primary-by-fuel` (open) | `/energy?v=all-energy-countries` | done 2026-10-18 (`ae-<ISO>`) |
| D3 | Which animals the livestock methane comes from (cross-drill to food's methane by animal) | `food.faostat.livestock-ch4-by-animal` (open) | `/air?v=methane-livestock` | done 2026-10-25 (card into `food:animals`) |
| D4 | Each country with the least electricity access, over time (bars → country line vs world) | `access.wb-wdi.electricity` (open) | `/energy?v=access-countries` | done 2026-10-18 (`access-<ISO>`) |
| D5 | Primary forest loss and driver bars → the existing `tl-<iso>` country nodes | `forest.gfw.*` (open) | `/food?v=primary-loss-countries`, `driver-<id>` | done 2026-10-25 (tl- nodes for all three rankings, 50 countries) |
| D6 | A country's forest area over time below `tl-<iso>` | `forest.fao-fra-2025.area` (open) | `/food?v=tl-<iso>` | todo |
| D7 | Each country's electrification over time (bars → country line) | `electricity.eurostat.share-of-final-energy` (open) | `/zero?v=electrify-countries` | todo |
| D8 | Net zero emitters' bars → the existing `action:ndc-<iso>` nodes | `ndc.climate-watch.2025-ndc` (noncommercial) | `/zero?v=net-zero-emitters` | todo |
| D9 | A country's net zero target below its NDC | `net-zero.nzt-2025.target-by-country` (noncommercial) | `/action?v=ndc-<iso>` | todo |
| D10 | Ocean pH beside surface carbon dioxide (sibling drill) | `ph.hot-aloha.surface-insitu` (open) | `/oceans?v=pco2` | todo |

## New sources (licence first)

| # | Question | Source (class per research) | Fits under | Status |
|---|---|---|---|---|
| N1 | Methane by source: fossil, farming, wetlands | Global Methane Budget, GCP-CH4 (open per research) | `/air?v=methane` | todo: read the producer's terms first |
| N2 | What people eat per person, by country | FAOSTAT Food Balances (FBS), artifact of `faostat` (CC BY 4.0) | `/food` diets | todo |
| N3 | EU countries' emissions by sector and gas | Eurostat env_air_gge (open, EU/EFTA/candidates only) | `/emissions` countries | todo: check EDGAR/IEA inputs as with env_ac_ghgfp |
| N4 | US states' CO2 by fuel and sector | EIA SEDS (public domain) | `/emissions` | todo |
| N5 | UK local authority emissions by sector | DESNZ local authority GHG 2005–2024 (OGL v3) | `/emissions` | todo |
| N6 | Burned area and fire carbon by country | State of Wildfires 2025-26 (open per research) | `/people?v=fires-europe` | todo |
| N7 | Where drought is worsening | SPEIbase v2.11 (open per research) | `/heat` or `/people` | todo |
| N8 | Official national inventories by IPCC category | Tidy GHG Inventories v2.1 (open per research) | `/emissions` | todo |
| N9 | A per-person denominator for energy | UN WPP 2024 or WDI population (open) | `/energy` | todo: needed before any "per person" energy view |

## Notes

- EIA's United States rows by fuel do not add up to its US total (EIA's US series count solar and geothermal
  differently, as the indicator's basis says), so a country-by-fuel view never says its bands add up to the total.

- The action chapter's root has 10 choice cards (6 static, 3 domains, 1 cross-drill), one more than the 9 the weekly
  task names as the limit. No new card may go there; replace one or go a level lower.
- Natural leaves (single-study or single-figure values) are not listed: most `/zero` leaves, `co2-800k-max`, `forcing`,
  `coral`, `human-year`.

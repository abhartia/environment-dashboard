# Weekly worklog

One entry per Sunday run of the data steward routine (newest first): what was refreshed, what failed and why, what
was fixed, what depth was added, dead ends, and what the next run should do first.

## 2026-10-25

**Refresh.** `envdash refresh`: every automatic licence quote unchanged except imbie-2026's (below). New vintages:
Ember yearly and monthly (file of 2026-10-19; world clean share 2025 revised 42.314 → 42.313 %, monthly to August
2026), Climate Watch NDC tracker (156 submitted, from 151: Albania, Guinea-Bissau, Grenada, Niger, Chad), Systems
Change Lab export (193 outcome indicators, from 179; on track 0.56 → 0.52 %), EIA international bulk (Oct 2026,
values unchanged), EFFIS 2026 burned area 700,797 ha (from 698,450), GWIS, HadCRUT5 monthly to September (annual
unchanged), C3S Climate Pulse to 23 October, FAO FRA, NSIDC and OSI SAF. Ember's revision gives Denmark −0.001 TWh of
other renewables in 2025, so that country-year is withheld by the existing negative-generation rule (11 withheld,
from 10). Every move checked against HEAD: new periods, producer revisions under 1 % on yearly values, or the
monthly series' preliminary months. No errata.

**Failed, not fixable this run.**
- `faostat`, `faostat-all-sectors`: FAO's `datasets_E.json` now gives GT `FileRows` 2,415,025 (it gave 2,500,090 on
  4, 5 and 11 October) while the GT zip is byte-identical (20,501,708 bytes, Last-Modified 2025-12-06) with 2,500,090
  rows, and DateUpdate is still 2025-10-28. The transform's guard refuses to take DateUpdate as the vintage of a
  file the catalogue does not describe, as designed; the GT indicators keep their last export. Probably FAO staging
  the October 2026 emissions release (due by 31 October). The `current.json` pointer moved to the new catalogue, so
  the FAOSTAT snapshot tests (3 failed, 10 errors, one cause) fail until FAO's zip and catalogue agree again.
- `imbie-2026`: data.bas.ac.uk answers 200 with "This website is undergoing maintenance", so the licence quote is not
  found and the source is frozen (its values did not change). Host maintenance, not a licence change; re-check next
  run.
- `unep-agr-2025`: still the owner's annex PDF.

`report-issues` opened issues for faostat, faostat-all-sectors and imbie-2026 and updated #3.

**Snapshot tests.** Facts pinned to last week's vintages re-derived from the new raw files (Climate Watch 158 / 157 /
144, period 2026-10-25; SCL 475 rows, 193 outcome indicators; Ember 116 countries without 2025 Total generation,
42.313, 11 withheld, 64 countries in July 2026, vintage 2026-10-19; EIA Oct 2026). Still failing: the FAOSTAT ones
above, the four UNEP-annex tests, and the golden rebuild (stops on those). Not re-run without those assertions this
week.

**Releases due.** Lancet Countdown 2026 global report: explore-our-data still lists only the 2025 workbooks; a UCL
event in October marks the 10th report, so it is probably days away. LPR 2026: no owner CSVs recorded yet.

**Depth shipped.** Backlog D3 and D5, both small dead ends. `/food?v=primary-loss-countries` and every
`/food?v=driver-<id>` ranking now open each bar's `/food?v=tl-<ISO>` (tree cover loss by driver; `forest.gfw.*`,
CC BY 4.0, open); the tl- nodes are built for the union of the three rankings' top 15 (50 countries, from 15), each
passing the driver-bands-add-up check. A tl- node keeps its trail under "Tree cover loss › By country" when reached
from primary forest; its sentence says "tree cover", so it never claims to be primary-forest-only.
`/air?v=methane-livestock` gets one card into `/food?v=animals` (`food.faostat.livestock-ch4-by-animal`, open). No
card added to a node that had any; no new indicator.

**Visual check not possible.** The preview server start was declined (no one at the keyboard to approve it), so the
nodes were checked from their built JSON only: kickers, headlines, chart series, drill targets and trails. Next run:
look at `/food?v=tl-BOL` and `/air?v=methane-livestock` at desktop and 375×812.

**Gates.** ruff, ruff format, `pytest -q` (1,119 passed), `pytest -m snapshot` (failures as above), `envdash
validate` (0 problems), gen:api clean, typecheck, lint, `npm test` (235), build with check-build (5,403 files, 215
indicators). Archive: R2 before the push; Wayback after it: 683 targets, 140 captured, 18 pending, 525 refused (almost all Save Page Now 429 "limit of active sessions"; pacing the data captures is still worth trying). CI and deploy of 31173f7 green; `tl-BOL` and the methane card served live.

**Owner actions.**
1. Download the Living Planet Report 2026 trend CSVs (see 2026-10-11, action 1).
2. Download `AGR2025_Online_Annexes.pdf` (runbook step 4).
3. IDMC API key still not issued (`idmc-client-id` absent).
4. Earthdata token expires 2026-12-05 (41 days left; renew after 2026-11-21).

**Next run first.** FAOSTAT: if FAO has published the October 2026 emissions release (GT, GLE with data to 2024),
adopt it (licence re-check: PRIMAP-hist v2.8 is CC BY-NC-SA, see `faostat-all-sectors.yaml`), re-pin the FAOSTAT
snapshot facts and check every food and emissions kicker; if the catalogue still disagrees with the zip, it stays
failed. Re-check imbie-2026's terms page. Lancet Countdown 2026 (G2). Then D7 (electrification bars → country line).

## 2026-10-18

**Refresh.** `envdash refresh`: every automatic licence quote unchanged. New vintages: C3S Climate Bulletin September
2026 (1.634 °C above 1850–1900; C3S's page says 1.63), NOAAGlobalTemp 6.1.0.202609 (2025 revised by the producer
from 1.291 to 1.282 °C), C3S Climate Pulse to 16 October, EFFIS 2026 burned area 698,450 ha (from 695,936), OSI SAF and
NSIDC sea ice, HadSST4 monthly, OISST, NASA SSH. Re-downloads with unchanged values: FAO FRA, Climate Watch (151
submitted), Systems Change Lab, Eurostat candidate list, EIA bulk manifest and FAQ 207, Naturvårdsverket, WDI
population. Every headline move checked against the previous catalogue: new periods or under 1%. No errata.

**Failed, fixed at the root.**
- `c3s-era5-bulletin`: the September bulletin renamed its files; no Fig1b link any more. The global all-months data
  is now three byte-identical files (Fig2, FigSupp1a, FigSupp2a); the discover rule takes the ref1850-1900 one with
  the figure number left open, the transform reads the month from either name, and a test checks the rule matches
  exactly one of the page's three links. The C3S publisher check is pinned to vintage 2026-08, so it reports
  not-applicable for 2026-09, like the other monthly sources' pinned checks.
- `iea-gevo-2026`: the IEA moved the explorer's API from `api.iea.org/evs` to `api.iea.org/electric-vehicles` (read
  from the explorer's own script, updated 9 October). Same query, same bytes as our snapshot, so no new vintage. The
  processing step now names the route each snapshot came from. No manual download needed after all.
- `rajalehto-helo-2025`: host back up; unchanged.

**Still failing.** `unep-agr-2025` (online annexes PDF, owner). Snapshot tests: the same four UNEP-annex tests as last
week; the Climate Watch test's pinned access date updated to 2026-10-18. A full forced rebuild without the UNEP
assertion reproduces `data/` except Wayback links that arrived while it ran (and the two files holding hashes), and
`data-private/` exactly.

**Archive.** 284 snapshots (mostly CCKP's projection files from 2026-10-16) had never been uploaded to R2; they are
now, and the data carries their mirror URLs. Wayback captures are slow (683 targets at up to a minute each, over three
hours this run); the push went out once R2 was complete, and captures that landed later went in a follow-up commit.
The Wayback record now holds 695 pages: 294 captured, 62 pending, 339 refused, most of the refusals Save Page Now's
429 "limit of active sessions" late in the run. Next run: if SPN still throttles, consider pacing the data captures.

**Releases due.** Lancet Countdown 2026: not out (explore-our-data still lists the 2025 workbooks; nothing 2026 in the
media library). Living Planet Report 2026: still waiting for the owner's CSVs.

**Depth shipped.** Backlog D2 and D4, both small and complete, both dead ends whose next question published data
answers. `/energy?v=all-energy-countries` bars now open `/energy?v=ae-<ISO>`: that country's energy by fuel since 1980
(`energy.eia.primary-by-fuel`, public domain, open), kicker naming the largest fuel derived from the data (coal in
China, India, Indonesia; gas in Russia, Iran, Canada; nuclear in France; oil elsewhere). `/energy?v=access-countries`
bars open `/energy?v=access-<ISO>`: the country's share with electricity against the world (`access.wb-wdi.electricity`,
CC BY 4.0, open). 30 nodes, no card added anywhere. The by-fuel view never claims its bands add up (EIA's US fuels sum
to 95.997 against a US total of 94.556 quad Btu). Checked at desktop and 375×812 in the built-in browser: one screen,
no scroll, chart draws, number links to its data page, bar → country → back works, no console errors. "Select a
country." was dropped from the access ranking's sentence because it truncated at 375 px.

**Gates.** ruff, ruff format, `pytest -q` (1,119 passed), `pytest -m snapshot` (all but the four UNEP-annex tests),
`envdash validate` (0 problems), gen:api clean, typecheck, lint, `npm test` (235), build with check-build (5,368
files, 215 indicators).

**Owner actions.**
1. Download the Living Planet Report 2026 trend CSVs (see 2026-10-11, action 1).
2. Download `AGR2025_Online_Annexes.pdf` (runbook step 4).
3. IDMC API key still not issued (`idmc-client-id` absent).
4. Earthdata token expires 2026-12-05 (48 days left; renew after 2026-11-21).

**Next run first.** Check for the Lancet Countdown 2026 workbooks (G2; usually late October); adopt LPR 2026 if the
owner recorded the CSVs; then backlog D3 (livestock methane → food's methane by animal) or D5 (forest loss bars →
the existing `tl-<iso>` nodes), both small.

## 2026-10-11

First run under this routine; WORKLOG.md and BACKLOG.md created (backlog seeded from the dead-end nodes, the research
files and status.json).

**Refresh.** `envdash refresh`: 79 sources checked, every automatic licence quote unchanged. New vintages built:
Ember yearly and monthly (2026-10-06; monthly now to August 2026), NOAA GML CO2/CH4/N2O (Mauna Loa September 2026,
426.07 ppm), GISTEMP v4 (2026-09; 2025 revised from 1.4205 to 1.4045 °C, a producer revision), World Bank WDI
electricity access (vintage 2026-10-08, values unchanged), EFFIS 2026 burned area (695,936 ha, from 689,324), OSI SAF
and Rutgers snow (September), C3S Climate Pulse daily, FAO FRA 2025 bulk re-download (unchanged values), Climate
Watch NDC tracker (151 submitted, unchanged), EIA FAQ 207, Eurostat candidate list. Every headline move checked:
monthly and daily series moved to a new period, the rest by under 1% or not at all. No errata needed.

**Failed (kept their last validated vintage; issues filed by `report-issues`):**
- `iea-gevo-2026` (evs-historical): `api.iea.org/evs` answers 404 "Cannot GET /evs" to every query, with or without
  parameters. The Wayback CDX shows the endpoint answering 200 on 2026-06-13 and 404 from 2026-10-10, so the IEA has
  retired or moved the API. www.iea.org refuses scripts (403), so the explorer's new data route cannot be read
  (rule 7). The 2026 vintage (data to 2025) stays published and is still the latest GEVO. Next run: probe again; if
  still gone, make the artifact `acquisition: manual` and ask the owner to download the explorer's CSV.
- `rajalehto-helo-2025` (article-pdf): osuva.uwasa.fi does not answer at all (connection times out, home page too).
  Host outage; retry next run.
- `unep-agr-2025`: the online annexes PDF has never been recorded (owner action below), so
  `adaptation-finance.unep-agr-2025.international-public-flows` is still unpublished.

**Releases due.** Living Planet Report 2026 is out (the LPI site's results page says "Data: Living Planet Report 2026,
WWF/ZSL"). LPI is manual (Shiny per-session downloads), so the nine trend CSVs need the owner. Its terms PDF moved:
`documents/data_agreement.pdf` is 404 and the home page links `LPI_Data_Use_Policy_2026.pdf`, whose clause 3 still
puts the published trends under CC BY-SA 4.0 (wording now "published LPI trends"); the new "for financial gain"
sentence covers the database records, which we never ingest. Registry quote, URL and checked_on updated; not a
licence change against us. The other "release due" issues (C3S, GISTEMP, NASA SSH, NOAA GML, NOAAGlobalTemp, OISST)
are monthly sources the refresh fetched.

**Snapshot tests.** Updated the facts pinned to last week's vintages, each re-derived from the new raw files: Ember
yearly 2025 has 114 (was 116) countries without Total generation, clean share 42.314; ten (was eleven) country-years
withheld for negative generation, Costa Rica's other fossil now -1.134 TWh; Ember monthly 62 countries in July 2026,
47 preliminary months to 2026-08; WDI vintage 2026-10-08; Climate Watch access date 2026-10-11. Still failing, as on
main since 2026-10-08: the three `test_action_unep_agr.py` tests that read the annex PDF and the golden rebuild, which
stops on the same missing annex. The same full rebuild run without that one assertion
is byte-identical to the committed `data/` and `data-private/`.

**Depth shipped.** Electric cars by country (backlog D1, chosen over D2–D10 because it needs no new source, the
question is the obvious next one, and the IEA file already carries 60 countries): `/energy?v=ev` now opens
`/energy?v=ev-countries` (the 15 highest electric shares of new car sales in 2025, Norway first, derived from the
ranking) and each bar opens `/energy?v=ev-<ISO>` (that country against the world, 2010–2025). `ev.iea.sales-share`,
CC BY 4.0 under the IEA Notice (open). Checked at desktop and 375×812: one screen, no horizontal scroll, chart draws,
number links to `/data/ev/iea/sales-share`, no console errors.

**Gates.** ruff, ruff format, `pytest -q` (963 passed), `pytest -m snapshot` (all but the four UNEP-annex tests),
`envdash validate` (0 problems), gen:api clean, typecheck, lint, `npm test` (196), build with check-build (3,939
files, 185 indicators).

**Owner actions.**
1. Download the Living Planet Report 2026 trend CSVs (Global, Terrestrial, Freshwater, Marine and the five IPBES
   regions) from https://www.livingplanetindex.org/latest_results and record each with
   `uv run envdash snapshot add --source living-planet-index --artifact trend-<id> --file <path> --note "downloaded by
   <who> from the latest_results page"`; the next run then updates the citation to "ZSL/WWF 2026".
2. Download `AGR2025_Online_Annexes.pdf` (runbook step 4) so the fourth adaptation indicator publishes and the UNEP
   snapshot tests pass.
3. If the IEA EV API is still 404 next week: download the Global EV Data Explorer CSV by hand.
4. IDMC API key still not issued (`idmc-client-id` absent).
5. Earthdata token expires 2026-12-05 (55 days left; renew after 2026-11-21).

**Next run first.** Re-probe `api.iea.org/evs` and osuva.uwasa.fi; adopt LPR 2026 if the owner has recorded the CSVs;
check whether the Lancet Countdown 2026 workbook is out (backlog G2); then backlog D2.

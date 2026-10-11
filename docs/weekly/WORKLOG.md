# Weekly worklog

One entry per Sunday run of the data steward routine (newest first): what was refreshed, what failed and why, what
was fixed, what depth was added, dead ends, and what the next run should do first.

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

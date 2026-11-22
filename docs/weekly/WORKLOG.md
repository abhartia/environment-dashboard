# Weekly worklog

One entry per Sunday run of the data steward routine (newest first): what was refreshed, what failed and why, what
was fixed, what depth was added, dead ends, and what the next run should do first.

## 2026-11-22

Third run on the Windows machine. Still no run secrets in `%USERPROFILE%\.secrets` (only two unrelated keys), so GFW,
NASA SSH, R2 and the Internet Archive were unavailable again. The `.claude/worktrees/weekly-depth` worktree (at
origin/main) held uncommitted work from an earlier, unrecorded session of 2026-11-21: a Naturvårdsverket fix, backlog
D8, and a fetch that had recorded Ember's file of 17 November. I reviewed it and kept it rather than discarding it,
re-ran the refresh over it, and shipped it after the gates.

**Refresh.** `envdash refresh` (about 25 minutes). Every reachable licence quote was unchanged. New vintages: NOAA GML
2026-11 (Mauna Loa October 426.69 ppm; global methane 2025 1936.03 → 1935.95 ppb), C3S Climate Pulse to 20 November,
AVISO to September 2026, NSIDC, OSI SAF, Systems Change Lab, FAO FRA re-download (values unchanged), EIA bulk manifest,
WDI population, and Ember yearly and monthly files of 17 November. Ember revised world solar up about 2 % in every year
(2025 share 8.791 → 8.986 %), so the world clean share 2025 is 42.309 → 42.483 %. That is a producer revision,
consistent across the series. No errata.

**Fixed (56e5b44).** Naturvårdsverket's page now prints `lastReviewed` as local midnight with an offset and holds the
GWP tab's HTML only as `textAsModel.fragments`. The transform reads the date part (any other time is refused) and joins
the fragments' raw HTML. Snapshot tests are pinned to the November page. Values unchanged.

**Held, not fixable here: ember-yearly by country.** Ember's 17 November file fails the by-country share check in 67
area-years across 19 small territories (Cook Islands 2021–2024, Montserrat 2019–2024 with 104.286 % in 2023, Kiribati,
Nauru, Falklands, Guinea-Bissau, French Guiana, Guadeloupe, Réunion and others; off by 0.003 to 4.3 points). In each,
Ember's own `Total generation` share prints the same off-100 figure. For Cook Islands 2021, generation of 0.008 and 0.02
TWh gives 28.714 % and 71.784 %, a denominator about 0.5 % below the total. The 3 November file passed in all 5,312
area-years. That is a producer inconsistency, not our parsing. Declaring 67 exceptions would amount to loosening the
check, so `electricity.ember.mix-by-country`, `clean-share-by-country` and `lifecycle-intensity-by-country` keep the 3
November vintage, and issue `source:ember-yearly` is open. The World indicators passed every check and use the 17
November file. The scan script is not committed: it runs `check_area_year` over `area_years(read_table(...))` and
collects every failure.

**Other failures (host side or missing keys).** `gfw-tree-cover-loss` and `nasa-ssh-gmsl` (no keys), `grant-2025`
(Europe PMC HTTP 500), `ipcc-ar6-wg1-spm1` (CEDA HTTP 503 on panel a's 1–2000 reconstruction; the other three panels
were not modified), `rajalehto-helo-2025` (osuva.uwasa.fi timed out), and `unep-agr-2025` (manual). Recovered and
closed: wb-cckp (#20), furch-2022 (#15) and rosenow-2025 (#19). Terms unverifiable as before: ourairports.com (expired
certificate), and Europe PMC for rosenow and scarborough (HTTP 500).

**Release due: Lancet Countdown 2026 (G2), checked, not adopted.** The terms page (lancetcountdown.org/use-our-data/)
still carries our quote word for word (CC BY-NC-SA 4.0), so the class stays noncommercial. The site's general Terms
& Conditions speak of "personal, non-commercial use" without redistribution. They are unchanged since we adopted the
2025 data, and the specific data licence governs, as before. The 2026 files are XLSX at
`data.lancetcountdown.org/downloads/2026/<indicator>/<hash>/lancet-countdown-2026-<indicator>-<name>.xlsx`. 1.1.5
heat deaths runs to 2023 (the 2025 report ran to 2021). 1.1.1 and 1.1.3 run to 2025, and 3.2.1 to 2023. Labour is
1.1.3 and 1.1.4 is now sleep loss. Not adopted this run (too large to finish alongside the rest).

**Depth shipped.** Backlog D8 (f77b808): each bar on `/zero?v=net-zero-emitters` now opens `/action?v=ndc-<ISO>`.
All 13 emitters have one, and a country without a coded plan would be named in the caption. `resolvedNode` now checks
chart drills as it already checked cards. No new indicator, card or screen. I chose D8 because it was finished and
its gates passed, and G2 does not fit in one run.

**Visual check: not possible.** Starting the static preview server was declined (no one present to approve it). Instead
I read the node file: 13 bars, each with `drill: action:ndc-<ISO>`. `crossHref` and `drill-canvas` route a bar's
cross-chapter drill with `router.push`.

**Gates.** ruff, ruff format, `pytest -q` (1,120 passed), `envdash validate` (0 problems), gen:api clean, typecheck,
lint, `npm test` (235), build with check-build (5,468 files, 215 indicators). Snapshot tests: the full run gave 457 passed and 14 failed. Ten of the failures were facts pinned to the old vintages (Ember 3 → 17 November, AVISO 7 → 21 November, EIA's count of country-years checked 11,140 → 11,563); they were re-pinned to the new files, and the Ember by-country tests now read the snapshot the published indicators were built from. A new test pins the refusal of the 17 November file, and the rerun of those files passes (19). The four remaining failures are the expected ones: three UNEP-annex tests, and the golden rebuild (WinError 1314).

**Not archived.** No R2 or Internet Archive keys. Three weeks of snapshots now have no `r2_key`. Their bytes were copied
into the main checkout's `pipeline/.snapshots` before the worktree was removed. No private export changed.

**Issues.** Opened ember-yearly, ipcc-ar6-wg1-spm1 and rajalehto-helo-2025. Closed furch-2022, rosenow-2025 and
wb-cckp. Updated #3, #16, #17 and #18. New release-due issue: iucn-red-list-gbif.

**Owner actions.**
1. **Renew the Earthdata token at urs.earthdata.nasa.gov › Generate Token.** It expires on 2026-12-05, in 13 days.
   Store it as `earthdata-envdash` in `%USERPROFILE%\.secrets`.
2. Put the run's secrets on this machine as DPAPI files in `%USERPROFILE%\.secrets`: `r2-envdash-access-key-id`,
   `r2-envdash-secret-access-key`, `gfw-api-key`, `archive-org-s3-access`, `archive-org-s3-secret` and `eia-api-key`.
   Three weeks of snapshots are waiting to be archived.
3. Optional: tell Ember (hello@ember-energy.org) that its 17 November yearly file has small-territory shares that do not
   add up to 100 (Cook Islands 2021: 100.498 %; Montserrat 2023: 104.286 %).
4. Download the Living Planet Report 2026 trend CSVs and `AGR2025_Online_Annexes.pdf` (as before). The IDMC key has
   still not been issued.

**Next run first.** Re-fetch Ember. If its file adds up again, the three by-country indicators rebuild by themselves.
If it does not, hold again; never declare 67 exceptions. Then adopt Lancet Countdown 2026 (G2), starting with 1.1.5
and 1.1.1. Run `envdash archive` if the R2 keys exist.

## 2026-11-15

Second run on the Windows machine; it started on Sunday 15 November and finished early on the 16th. Still no run
secrets in `%USERPROFILE%\.secrets` (only two unrelated keys), so GFW, NASA SSH, R2 and the Internet Archive were
unavailable again (owner actions below). The leftover `.claude/worktrees/weekly-depth` folder held only an empty
`web/` directory and was not a registered worktree; it was removed and the worktree re-created from origin/main.

**Refresh.** `envdash refresh` took about 90 minutes, most of it fetching. Every reachable licence quote was unchanged.
New vintages: GISTEMP v4 2026-10 (2025 revised 1.4045 → 1.4145 °C, a producer revision), NOAAGlobalTemp
6.1.0.202610 (2025 1.282 → 1.290 °C), C3S Climate Pulse to 12 November, EFFIS 704,227 ha (from 703,775), HadSST4
monthly, EIA international bulk Nov 2026 (values unchanged), WDI electricity access 2026-11-11 (values unchanged), FAO
FRA re-download (values unchanged), Systems Change Lab (unchanged share), Eurostat candidate list, EIA FAQ 207. No
errata.

**Failed, not fixable here (host side).**
- `wb-cckp`: cckpapi.worldbank.org answered HTTP 500 to every artifact after three attempts. Values unchanged.
- `furch-2022`, `grant-2025`, `rosenow-2025`: Europe PMC's fullTextXML service answered HTTP 500 for all three.
- `gfw-tree-cover-loss`, `nasa-ssh-gmsl`: `GFW_API_KEY` and `EARTHDATA_TOKEN` not on this machine.
- `unep-agr-2025`: still the owner's annex PDF.
- Terms unverifiable, as last week: ipcc.ch/copyright answers 403; ourairports.com's TLS certificate has expired.

**FAOSTAT 2026 adopted (backlog G5, fixed at the root).** The refresh again built 13 FAOSTAT indicators on the release
of 6 November 2026 and failed 7, so it would have published half a release. Fixed instead:
1. *PRIMAP-hist version.* Twenty CO2 values (DEU, CHN, IND energy; USA IPPU; BRA waste; 2021–2024) equal PRIMAP-hist
   v2.8 HISTTP exactly, and 12 of them differ from v2.7 (Germany energy 2023: 537,000 kt in GT and v2.8, 550,000 in
   v2.7). v2.8's Zenodo record (22876287) says "Since v2.8 PRIMAP-hist is published under a non-commercial license
   (CC BY-NC-SA)", so the class stays noncommercial; registry quote, terms_url, citation and attribution now name
   v2.8 (Gütschow and Pflüger, 2026). Not a licence change against us.
2. *Bunkers.* `International bunkers` (6820) is a seventh, World-only part of `ghg.faostat.by-sector` and
   `ghg.faostat.ch4-share-by-sector` ("International aviation and shipping"). The identities still hold everywhere
   (World with seven parts in all 35 years, 9,320 other area-years with six), and a bunkers row without a total
   stops the build. Scope is `bunkers: included` for the six all-sector indicators, and every description says the
   world's total counts them and no country's does. Agrifood indicators keep `excluded` (their items never include
   bunkers).
3. *Flag L.* An empty Value flagged L ("Missing value; data exist but were not collected", checked against each
   file's codebook) is left out and named in a step (Nicaragua 2023–2024 in EM, 2024 in GLE). Any other empty Value
   still stops. Shared helpers `faostat_bulk.not_collected` and `not_collected_step`.
4. *Tuvalu 2000 methane shares add up to 100.0433.* FAO divided 0.2311 kt of sector methane by a total it prints as
   0.2310 kt. Declared in `CH4_SHARES_OVER_100`, which stops the build if the sum changes. The check was not
   loosened.
5. Every count in the descriptions was re-derived from the new files: 27 territories without energy rows (was 28),
   8 zero-total territories (was 10), 61 without F-gases (was 67), 201 negative per-person values (was 94), 74/71
   negative EI meat values (was 75/72).

Headline moves, all FAO revisions, checked for consistency rather than taken on trust. World total 2023 is 52.106 →
52.931 Gt (v2.8 plus 1.330 Gt of bunkers); 2024 is 53.362. Agrifood 2023 is 16.535 → 18.648 Gt. FAO's agrifood share
2023 is 31.73 → 35.23 % (2024: 34.61 %), and 2001 is 38.37 → 44.74 %. In every year checked, FAO's printed share equals
its agrifood total over its all-sector total. World net land use 2023 is +0.467 → −0.711 Gt (a larger forest sink).
FAO has published no analytical brief for this release yet, so the publisher checks (Brief 115, release of 2025)
report not-applicable. Tests were re-pinned to the new files: test_ghg_faostat_all_sectors, test_faostat_emissions
(the World total now includes bunkers, so the identity test asserts seven parts), test_food_faostat and
test_food_faostat_breakdowns. New snapshot tests cover the bunkers part, flag L and the declared Tuvalu sum.

**Depth shipped.** Backlog D6: each `/food?v=tl-<ISO>` (tree cover lost by driver, previously `drills: []`) gets one
card into `/food?v=fa-<ISO>`. That view is the country's forest area in FAO's forest assessment since 1990
(`forest.fao-fra-2025.area`, CC BY 4.0, open), and its sentence says forest area also counts regrowth and planting,
unlike tree cover lost. It adds 50 nodes (every tl- country has FRA data) and no new indicator. I chose D6 because
the FAOSTAT fix filled most of the run, and D6 was small and complete.

**Visual check (built-in browser, static export on :3201).** The pane was hidden, so animations stalled in
screenshots. A full-resolution capture and DOM measurements stood in:
- `/emissions` draws seven World bands, with the blue aviation and shipping band on top.
- `tl-BRA` shows the "Brazil: forest area" card, and selecting it opens `fa-BRA`, whose chart draws.
- At 375×812, `tl-IDN`, `fa-IDN` and `/emissions` have no page scroll either way (812 × 375), and the card is inside
  the viewport.
- No console errors, apart from the local `serve`'s 404s on Next RSC prefetch files. Those 404s are not from this
  change.

**Gates.** ruff, ruff format, `pytest -q` (1,119 passed), `envdash validate` (0 problems), gen:api clean, typecheck,
lint, `npm test` (235), build with check-build (5,468 files, 215 indicators). `pytest -m snapshot`: 466 passed; the
expected failures are the three UNEP-annex tests and the golden rebuild (WinError 1314, symlinks need Developer
Mode).

**Not archived.** No R2 or Internet Archive keys. This week's and last week's new snapshots (including FAOSTAT's
b048ba37…, f49d3fde… and the GLE/EI/catalogue files) have no `r2_key`; their bytes are in the main checkout's
`pipeline/.snapshots` cache, copied there before the worktree was removed. No private export changed, so the
deploy's `private pull` is unaffected.

**Issues.** `envdash report-issues` failed twice on Windows, both times on wb-cckp's 119,030-character failure
reason. First the body was passed on the command line, past Windows' 32,767-character limit. Then GitHub refused it
(the limit is 65,536). Fixed in `issues.py`: bodies now go to `gh` on stdin (`--body-file -`), and the quoted reason
is cut between artifacts at 4,000 characters, with a pointer to status.json (unit test added). Result: closed
faostat, faostat-all-sectors and imbie-2026; opened furch-2022 (#15), gfw-tree-cover-loss (#16), grant-2025 (#17),
nasa-ssh-gmsl (#18), rosenow-2025 (#19) and wb-cckp (#20); updated unep-agr-2025 (#3). New release-due issues:
climate-trace, lancet-countdown-2025 and net-zero-tracker-2025. Check those producers next run.

**Owner actions.**
1. Put the run's secrets on this machine as DPAPI files in `%USERPROFILE%\.secrets`: `r2-envdash-access-key-id`,
   `r2-envdash-secret-access-key`, `gfw-api-key`, `earthdata-envdash`, `archive-org-s3-access`,
   `archive-org-s3-secret`, `eia-api-key`. Two weeks of snapshots are waiting to be archived.
2. Renew the NASA Earthdata token: it expires 2026-12-05 (19 days left). Renew it at urs.earthdata.nasa.gov ›
   Generate Token after 2026-11-21, and store it as above.
3. Download the Living Planet Report 2026 trend CSVs (see 2026-10-11, action 1).
4. Download `AGR2025_Online_Annexes.pdf` (runbook step 4).
5. IDMC API key still not issued.
6. Optional: ask FAO (faostat@fao.org) which PRIMAP-hist version its GT notes should name. The values are v2.8, but
   FAO's documentation still says v2.4.

**Next run first.** `envdash archive` if the R2 keys exist. Then the Lancet Countdown 2026 (G2, new portal), then
look for an FAO brief on the 2026 emissions release to add as a publisher check. Re-probe cckpapi and Europe PMC.

## 2026-11-08

First run on the owner's Windows machine (the Mac is out of service until about December). No run on 2026-11-01.
None of the run's secrets exist here yet: `%USERPROFILE%\.secrets` holds only an unrelated key, so R2, GFW, Earthdata,
Internet Archive and EIA keys were all absent (owner actions below).

**Setup.** The main checkout's snapshot cache lacked 40 snapshots from the last two Mac runs. 39 were in the public R2
bucket and came down over HTTPS from files.environmentdashboard.org, each checked against its manifest's sha256 with
`snapshot_pull.decode`. The 40th, `systems-change-lab/scl-data-all`, is private-bucket only; the refresh fetched a new one.
The 11 private exports in the main checkout matched the catalogue's hashes, and none changed this run, so the deploy's
`private pull` has nothing new to find.

**Windows fixes (c568ae9).** `%-d` in EIA's and IRENA's step text is a glibc/BSD-only strftime code. Windows raised
"Invalid format string", so the four EIA energy indicators failed. 72 test reads and 8 writes (plus one in archive.py)
used the platform's default encoding, cp1252 here. check-build's page paths kept "\", so every data page missed the
TECHNICAL_PAGES exemption. Each is fixed at the root, with output byte-identical to the Mac's.

**Refresh.** `envdash refresh`: every reachable licence quote unchanged. New vintages and moves are in the refresh
commit (5d1991b): Ember to 3 November (world clean share 2025 42.313 → 42.309 %; Iceland's clean share printed
100.002, accepted within nine shares' rounding, 702642e), C3S October 1.754 °C, AVISO to August 2026, EFFIS 703,775 ha.
Naturvårdsverket added 2024 and revised the whole Swedish series (2023 7.62 → 7.17 t). OECD GBARD turned provisional
years final (France 2023 2,659 → 1,583, back in line with 2019–2022). Each move was checked against HEAD: new periods,
producer revisions, or (OECD, Naturvårdsverket) provisional-to-final and series revisions that are consistent across
the series, not parsing errors. Terms "unverifiable": ipcc.ch/copyright answered 403 to this machine (new this week),
and ourairports.com's TLS certificate has expired. Neither is a licence change; recheck next run. imbie-2026 recovered.

**FAOSTAT held (G5).** FAO published its release of 6 November 2026 (data to 2024). I traced three changes in the raw
files, then held both sources at their last vintage instead of publishing half of it. Before the hold, 13 FAOSTAT
indicators built on the new files and 8 failed. Status records the hold through `update_status(extra_failures=…)`,
with the vintage put back to the published one.
1. The World's "All sectors with LULUCF" (6825) now includes International bunkers (6820), in GT and in EM's shares.
   All 35 World years add up with seven parts, and all 9,320 other area-years still add up with six. Our scopes say
   `bunkers: excluded`.
2. Agrifood systems emissions are revised up over the whole series. World 2023 goes 16.535 → 18.648 Gt; land-use
   change +32 % and pre- and post-production +23 %; FAO's own share 31.73 → 35.23 %. The stage parts still add up to
   FAO's total.
3. Nicaragua 2023–2024 is printed empty with flag L ("Missing value; data exist but were not collected"). This
   affects EM, EI and livestock, and the transforms stop on any empty Value.
The PRIMAP-hist version behind energy, IPPU, waste and other is unverified (the registry header expects v2.8), so the
attribution would be wrong. The fixes for 1 and 3 were written and then backed out, so no untested code was
committed; the backlog G5 row lists what they need. Snapshot tests for FAOSTAT fail the same way as last week.

**Lancet Countdown 2026 is out (G2).** It is on a new portal, data.lancetcountdown.org/data-explorer, with CSV and
XLSX per indicator (1.1.5 "last updated in September 2026"). Not adopted this run: it is every Lancet indicator on a
new file layout.

**Depth shipped.** Backlog D7: `/zero?v=electrify-countries` bars now open `/zero?v=electrify-<ISO>`, which shows the
country's share of final energy used as electricity since 1990, against the EU in grey
(`electricity.eurostat.share-of-final-energy`, open). It adds 15 nodes, no card, and no new indicator. I chose D7
over G2 and G5 because both releases need more than one run's careful work, and D7 was complete and small. **Visual
check not possible**: the browser pane refused localhost with nobody to approve it. The node files were checked
instead (kicker, headline, sentence, NOR + EU27 lines with 35 points each, every bar's drill target built).

**Gates.** ruff, ruff format, `pytest -q` (1,119 passed), `envdash validate` (0 problems), gen:api clean, typecheck,
lint, `npm test` (235), build with check-build (5,418 files, 215 indicators). `pytest -m snapshot`: 20 facts
re-pinned and passing. Expected failures: the four UNEP-annex tests and FAOSTAT on its held vintage. The golden rebuild
cannot run here because `symlink_to` needs a Windows privilege (WinError 1314); it needs Developer Mode or the Mac.

**Not archived.** With no R2 or Internet Archive keys, `envdash archive` could not run. This week's new snapshot
manifests have no `r2_key`, so a fresh checkout's `snapshots pull` will name them until they are archived. Their bytes
are kept in the main checkout's `pipeline/.snapshots` cache, copied there before the worktree was removed. The deploy
does not need them: it pulls only the unchanged private exports.

**Owner actions.**
1. Put the secrets on this machine as DPAPI files in `%USERPROFILE%\.secrets` (`r2-envdash-access-key-id`,
   `r2-envdash-secret-access-key`, `gfw-api-key`, `earthdata-envdash`, `archive-org-s3-access`, `archive-org-s3-secret`,
   `eia-api-key`). Then next week's run can archive this week's snapshots and fetch GFW and NASA SSH.
2. The Earthdata token expires 2026-12-05 (27 days left; renew after 2026-11-21). Its expiry could not be read here.
3. Download the Living Planet Report 2026 trend CSVs (see 2026-10-11, action 1).
4. Download `AGR2025_Online_Annexes.pdf` (runbook step 4).
5. IDMC API key still not issued.

**Next run first.** `envdash archive` once the R2 keys exist (this run's snapshots). Then FAOSTAT 2026 (G5, steps in
the backlog), then the Lancet Countdown 2026 (G2).

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

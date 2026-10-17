# Sources: how we choose them, and what we turned down

The registry itself is `pipeline/sources/<id>.yaml`, one file per source. Each file quotes its producer's terms
(`evidence.licence_quote`, from `evidence.terms_url`, checked on `evidence.checked_on`), and every web page under
`/sources` is generated from it. This document holds the rules and the decisions that are not visible in the registry,
above all what was rejected and why. The research behind the first registry is dated and kept in `docs/research/`.

## Rules for adding a source (adapted from simmerlist's SOURCES.md)

1. **Licence first.** Read the producer's own terms before writing any code. If they forbid what we need (showing
   the values, or redistributing them where we want a download), record the source under *Rejected* below with the
   clause and the URL, and stop. Never take the licence from an aggregator's metadata (Our World in Data, HDX, the UN
   SDG database). Aggregators have repeatedly been wrong about the producer's terms: OWID labels the Living Planet
   Index CC BY when the producer says CC BY-SA, and HDX labels IDMC data CC BY-IGO when IDMC says CC BY-NC-SA.
2. **The producer, not a copy.** Fetch from the organisation that made the data. Use a mirror only when it is the
   producer's own stable copy (a Zenodo deposit, a pinned ICOS object), and say so.
3. **Pin what can be pinned.** Prefer DOI-versioned files and pinned object ids over "latest" links. Where a
   producer renames files on a schedule, the artifact's `discover` rule picks the newest by an explicit key; it never
   guesses.
4. **Decide what the source may assert.** One series comes from one source. A second source measuring the same thing
   is a `twin`, shown beside the first, never blended into it.
5. **No scraping workarounds.** If a host blocks scripts (Cloudflare challenges, captchas), the source is
   `acquisition: manual`. A person downloads the file and records it with `envdash snapshot add`, and the data page
   says so.
6. **Record the obligations.** These are the credit line (and its "modified" form), notices, rounding rules, whether
   the raw file may be re-hosted, logo and endorsement limits, and the credit owed wherever a derived motif appears.
   check-build verifies they are rendered.

## Licence classes

| Class | Meaning | What the site does |
|---|---|---|
| `open` | Public domain, CC0, CC BY, OGL, or attribution-only terms | Chart, download, public raw mirror (unless `mirror_raw: false`) |
| `share-alike` | CC BY-SA | As open; downloads carry CC BY-SA |
| `noncommercial` | CC BY-NC(-SA) or custom non-commercial terms | Chart and download, carrying those terms |
| `no-derivatives` | CC BY-NC-ND and similar | The producer's published values verbatim; nothing recalculated; no download |
| `display-only` | No licence, all rights reserved, no re-hosting | Shown with citation; no download, no mirror |
| `excluded` | Terms forbid what we need | Not ingested; listed under Rejected |

## Decision on FAOSTAT all-sector emissions (2026-10-05)

Evidence: docs/research/sources-ghg-food-personal-2026-10-05.json (research[0] candidate 1 and verification[1]).

- **FAOSTAT all-sector emissions are a separate, noncommercial source (`faostat-all-sectors`).** FAO labels FAOSTAT
  CC BY 4.0 ("Unless specified otherwise in their metadata or webpage, all datasets disseminated through FAO corporate
  statistical databases (see examples in Annex 1) are licensed under the Creative Commons Attribution-4.0
  International licence (CC BY 4.0)", https://www.fao.org/contact-us/terms/db-terms-of-use/en/), but its section 2
  'Third party exceptions' says "It is your responsibility to act in compliance with the terms and conditions of the
  third-party data providers." The Emissions totals (GT) items Energy, IPPU, Waste and Other are PRIMAP-hist
  third-party-priority (HISTTP) data. FAO's GT note and Analytical Brief 115 name PRIMAP-hist v2.4 (CC BY), but the
  values in the October 2025 release are v2.7: Germany energy CO2 2023 is 550,000 kt in GT and in v2.7 HISTTP against
  558,000 in v2.6.1; USA IPPU CO2 2022 is 139,000 against 136,000; India energy CO2 2022 is 2,670,000 against
  2,680,000. PRIMAP-hist v2.7 (https://zenodo.org/records/17090760) says "Since v2.7 PRIMAP-hist is published under a
  non-commercial license (CC BY-NC-SA). This means that commercial users can not use it freely and have to obtain a
  commercial license.", and its commercial licence does not cover the TP series. As with
  jones-2025-national-contributions, a downstream CC BY label cannot lift upstream NC-SA terms, so FAOSTAT's non-farm
  sectors, the all-sector totals and every Emissions indicators (EM) share or per-capita value whose denominator
  includes them are published under CC BY-NC-SA 4.0 with PRIMAP-hist credited. The open `faostat` entry keeps the
  agrifood and livestock items; the agrifood share (food.faostat.agrifood-emissions-world.share) moved to the new
  entry and is now FAO's own published value.
- **Open questions, not yet asked.** Nothing has been sent to FAO. The owner is to ask FAO (faostat@fao.org; see
  docs/runbook.md) which PRIMAP-hist version and terms apply to GT's non-farm items, and whether the IEA activity data
  behind the pre- and post-production estimates carries restrictions. Re-check at FAO's October 2026 release, which
  will probably use PRIMAP-hist v2.8 (also CC BY-NC-SA; its record warns "Do not use the TP scenario data without
  proper checks.").

## Decisions on FAOSTAT food breakdowns (2026-10-05)

Evidence: docs/research/sources-ghg-food-personal-2026-10-05.json (need B and its verification).

- **FAOSTAT Emissions intensities (EI)** is registered as artifact `emissions-intensities` of `faostat`
  (https://bulks-faostat.fao.org/production/Environment_Emissions_intensities_E_All_Data_(Normalized).zip). Its
  methodological note (https://files-faostat.fao.org/production/EI/EI_e.pdf, release October 2025) gives "Owner FAO
  Provider FAO Source FAO" and no licence of its own, so the FAO Statistical Database Terms of Use (CC BY 4.0) apply
  and the class is open. EI counts only farm-gate emissions: enteric CH4, manure management CH4 and N2O, N2O from
  manure left on pasture and applied to soils, and, for rice and cereals, N2O from crop residues and synthetic
  fertiliser, N2O and CH4 from burning crop residues, plus rice paddy CH4. It leaves out on-farm energy, drained
  organic soils, savanna fires, land-use change and all pre- and post-production, and FAO says its values "should not
  be compared" with life-cycle assessments. Its intensities are per kilogram of FAOSTAT production: carcass weight for
  meat, raw whole milk, eggs in shell. Its 14 products leave out soy, palm oil, fruit, vegetables, sugar, pulses and
  fish and add up to no FAO total, so they are shown as ranked bars, never as a stack, and no share of food's emissions
  is computed from them (it would divide an EI value by a GT value of another vintage).
- **Why the agrifood items of GT stay open while its non-farm items are noncommercial.** GT's energy, IPPU, waste and
  other items are PRIMAP-hist values used directly, an adaptation of NC-SA data, so they follow PRIMAP-hist's terms
  (see the all-sector decision above). FAO's pre- and post-production estimates are FAO's own calculations from
  several inputs (UNSD, IEA, and emission information from PRIMAP-hist), so they keep FAO's CC BY label. Whether that
  holds is the open question for FAO, together with the next point.
- **Open question: third-party inputs in FAOSTAT Emissions totals (GT).** FAO's GPP note says pre- and
  post-production energy emissions use IEA data (China and Russia) and IEA grid electricity emission factors, and that
  cold-chain F-gases come from EDGAR v7; the GN note says on-farm energy use applies IEA grid electricity and heat
  factors and IEA fisheries energy data. FAO's metadata states no restriction on them, so `faostat` stays open under
  FAO's own clause. Because this registry treats EDGAR's IEA-derived CO2 as restricted, permission to redistribute
  these GT items is to be confirmed with FAO (faostat@fao.org) by the owner. Not yet asked.
- **GT and GPP are not mixed.** FAOSTAT GPP (DateUpdate 2026-05-22) has newer pre- and post-production values than GT
  (2025-10-28): World 2023 pre- and post-production is 5,303,012 kt in GPP against 5,247,971 kt in GT. Stacking GPP
  parts under GT's agrifood total would break its equality with FAO's published total, so only GT is used until the
  vintages align.
- **FAOSTAT Emissions from crops (GCE)** is not used: synthetic-fertiliser N2O is not split by crop, so its per-crop
  values do not add to its total, and EI already publishes CO2-equivalent per cereal and rice.
- **GLEAM 3 dashboard** (life-cycle livestock emissions, 2015) is not registered yet: its own terms say CC BY 4.0, but
  the data can only be downloaded by hand from a Shiny app and its structure and additivity are unverified.
- **FAOSTAT GLE catalogue row count.** datasets_E.json gives GLE FileRows 6,941,916 while the CSV has 6,650,421 data
  rows, so the GLE transform ties the catalogue's DateUpdate to the zip by FileLocation and FileSize (kilobytes
  rounded up) instead, and says so in a processing step.

## Decisions on personal footprints (2026-10-05)

The owner read "per person" as one person's footprint, not a country's territorial average. No openly licensed
producer publishes a world-average footprint split by consumption category, or tonnes per person by global income
group (docs/research/sources-ghg-food-personal-2026-10-05.json). The site therefore shows only what producers publish
themselves, and never divides a total by population or multiplies an income share by a total.

- **Naturvårdsverket per-person footprint (Sweden)** (`naturvardsverket-consumption-footprint`): open on two quotes,
  Naturvårdsverket's "Öppna data får användas fritt" and SCB's CC0 for the official statistics behind it. The quote
  spans two pages, so the terms are re-read by hand each quarter (`terms_check: manual`). The series exists only as
  the chart payload inside the statistics page, so the whole page is snapshotted and parsed strictly. The page is not
  re-hosted (`mirror_raw: false`): the open terms cover the statistics, and the page names its photographs and
  illustrations as copyright-protected. Its test fixture is therefore only the bytes of the data payload. Public
  consumption and investment (2.92 of 7.62 t in 2023) are shown apart from the household parts because they are not
  personal choices; investment includes new homes. The parts are rounded by the producer and may differ from the
  total by 0.01 t. The page shows the IPCC AR4 global warming potentials (methane 25, nitrous oxide 298) in a general
  conversion table without saying they apply to this series, so no GWP is recorded and the scope says why. The page
  does not say whether meals eaten out are under food. Naturvårdsverket's 'Övrigt' cannot be rebuilt from SCB's
  COICOP tables, so SCB tonnes are never used to recompute it.
- **Defra UK carbon footprint** (`defra-uk-carbon-footprint`): OGL v3, stated on the dataset's own cover sheet, which
  the transform re-reads on every build. The registry declares the OpenDocument files as `zip`, which is what they
  are as packages, because the artifact formats have no `ods`. The release's Summary of Methods PDF is registered as
  artifact `methods` and read by every Defra indicator, which cites its AR5 sentence for the global warming
  potentials. Per-person values exist only for the total, which is an average per resident. Categories are in
  kilotonnes and are shown in million tonnes, never per person. 'Food and beverages' excludes 'Hotels and restaurants'
  and 'Alcohol and tobacco', and flights have no figure of their own: households' flights are inside transport, and
  business and government travel sit in the supply chains of other rows.
- **SEI income-group shares end at 2022** (`co2-share.sei-inequality.income-groups-global`): not a licence issue. The
  API's 2023 national values are territorial while 1990-2022 are consumption-based (historicalDataByCountry, registered
  as artifacts national-history-che, -usa and -gbr and snapshotted on 2026-10-05: Switzerland 121,979,300 t in 2022
  and 32,737,300 t in 2023; United States 5,642,856,100 t and 4,911,391,000 t; United Kingdom 488,532,000 t and
  305,146,300 t). The world top-10% share falls from 48.99% to 47.08% at that change of basis, so 2023 is not
  published. The indicator is labelled as shares of world emissions, not tonnes per person.

## Decisions for the "Getting to zero" chapter (2026-10-08)

The owner asked for the frameworks of Bill Gates's *How to Avoid a Climate Disaster* (2021) to be well represented.
Evidence: docs/research/sources-zero-*-2026-10-08.json. Gates's own figures cannot be used: his five shares are
Rhodium Group's (all rights reserved, built on IEA data) and his Green Premiums are Breakthrough Energy's, whose terms
allow only unmodified, non-commercial copying. Each concept is therefore shown from primary producers, and nothing from
the book is typed into the site.

- **UNEP's notice is noncommercial for every UNEP report** (owner, 2026-10-08). "This publication may be reproduced in
  whole or in part and in any form for educational or non-profit services ... No use of this publication may be made
  for resale or any other commercial purpose" covers charting and downloading on this non-commercial site. unep-egr-2025
  moved from display-only (it had no indicators, so no published file moved); unep-food-waste-index-2024 and
  unep-agr-2025 already match. The PDFs are not re-hosted.
- **UNEP Adaptation Gap Report 2025** (`unep-agr-2025`): two manual PDFs (UNEP's repository refuses scripts), read
  from fixed pages. The 2019–2023 flows are Figure 4.4's printed data labels, never measured from bars, and UNEP took
  them from the OECD DAC Climate-Related Development Finance data set (online annex 4.B), whose own terms could not be
  read (oecd.org refuses scripts). Its "developing countries" are entity `UNEP_AGR_DEV`, with no membership list
  because UNEP publishes none. The four indicators publish once a person records the files.
- **FAO World Census of Agriculture** (artifact `world-census-agriculture` of `faostat`, CC BY 4.0): holdings and their
  area by FAO's land-size classes, per country and census. Censuses fall in different years and countries define a
  holding differently, so there is no world or regional sum and classes are never added. FAO files China's census
  under area 351 ("China" including Hong Kong, Macao and Taiwan), so it is left out until FAO says whether those rows
  cover the mainland only. The WCAD metadata endpoint returned HTTP 521 on 2026-10-08, so its "unless specified
  otherwise in their metadata" check is still to be done. The world figures most often quoted (608 million farms,
  about 35% of food from farms under 2 ha: Lowder et al. 2021; Ricciardi et al. 2018) are CC BY-NC-ND articles and are
  not ingested.
- **Net Zero Tracker 2025** (`net-zero-tracker-2025`, Zenodo record 17143240): the deposit is tagged CC BY 4.0, but
  zerotracker.net/data-terms-of-use says the Tracker's datasets are CC BY-NC 4.0 since 3 December 2024. The stricter
  class, noncommercial, applies until the Tracker says otherwise (owner, 2026-10-08). Only national target status and
  year are published: the file's emissions columns come from Climate Watch CAIT, which cites OECD/IEA, and the
  Stocktake report's coverage shares (all rights reserved) are not reproducible from the file, so no share of world
  emissions is shown. The report's "198 incl. EU and Taiwan" does not match the file, which has no Taiwan row and
  counts Bermuda, the Cayman Islands and Niue.
- **Eurostat** (`eurostat`, open under Decision 2011/833/EU): electricity's share of final energy as Eurostat
  publishes it (nrg_ind_fecf, E7000, FC_E), and government R&D budgets for energy (gba_nabsfin07, NABS05). Eurostat's
  notice bars commercial reuse of data for countries outside the EU, EFTA and the candidate countries, so only those
  are requested, and the candidate list is re-read at every build. NABS05 counts all energy research, fossil and
  nuclear included.
- **OECD government R&D budgets for energy** (`oecd-gbard`, open under the Data section of the OECD terms, read from
  an Internet Archive capture because www.oecd.org refuses scripts, so re-checked by hand): constant 2020 PPP dollars,
  with the OECD's status flags. The dataflow is annotated "NonProductionDataflow: true", which the OECD does not
  explain. Japan rises from 5,268 (2022) to 13,682 (2023) under a "definition differs" flag. The IEA RD&D Budgets
  product ("Terms of Use for Non-CC Material") is not used, although its explorer page says CC BY 4.0 (owner,
  2026-10-08).
- **IEA CCUS Projects Database** (`iea-ccus-projects`, CC BY 4.0 on the product and explorer pages, read from
  Internet Archive captures because iea.org refuses scripts): the explorer's own data file, counted with the explorer's
  own rule (ccus.js: capacity above zero, not suspended, transport and storage projects left out). These are
  announced capacities of projects, not carbon dioxide captured. The IEA Notice obligations apply.
- **The State of Carbon Dioxide Removal, 3rd edition** (`state-of-cdr-3`, CC BY 4.0): chapter 7's novel removals by
  method and conventional forest removals. Open: the site's CC BY statement names the reports, not the data files; and
  for projects not on registries the novel values come from CDR.fyi, whose terms forbid republishing. Chapter 3
  (investment, from the commercial Net Zero Insights database) is not used.
- **Land per unit of electricity: Lovering et al. 2022** (`lovering-2022`, CC BY 4.0, PLOS ONE): Table 1 only, as
  printed and checked against the PDF. Its spread is the width between the quartiles, not the two quartiles. Coal,
  gas, nuclear and dedicated biomass include the land that supplies the fuel; rooftop solar is zero by the authors'
  assumption. The site-level file is not ingested: its 951 dam rows come from the subscription ICOLD World Register.
  **Nøland et al. 2022** (`noland-2022`, CC BY 4.0, Scientific Reports) is its twin in watts per square metre, shown
  beside it and never combined, from Table 16 without its gas row (IEA World Energy Outlook inputs) and biomass row (van
  Zalk & Behrens' value, whose licence is unconfirmed).
- **How much power: average power is a recorded unit conversion.** A year's energy (EIA RECS 2020 for the average US
  home, public domain; DESNZ subnational electricity 2024 for Great Britain's average home and London, OGL v3; Ember
  world electricity demand; EIA world primary energy) is divided by the hours in its own span counted from dates, and
  the processing step says so. Vogtle's 4.53 GW is a net summer capacity (EIA FAQ, public domain), labelled as a
  capacity, not an output.
- **Green Premiums: one producer, one basis.** A clean and a fossil cost are shown side by side only when one producer
  publishes both on one basis (EIA AEO2026 new-plant costs; DESNZ Generation Costs 2025, a twin; CEMCAP's reference
  cement plant; one CC BY study each for ammonia, heating, cars, trucks and meat). Premiums a producer states are
  published as printed, ranges as low and high ends. Nothing is computed across sources. IEA statements come only from
  report PDFs the IEA serves to scripts, each sentence found on its page at every build; figures credited to
  BloombergNEF, Argus or S&P are left out, and chart data embedded in iea.org pages is not read through the Internet
  Archive (rule 7). Costs exclude subsidies and carbon prices except where marked: ETP's urea figure includes carbon
  pricing, the IEA's ammonia premium is given both ways, and DESNZ totals carry the UK carbon price as their own row.
  A value a paper takes from someone else is left out: Sacchi et al.'s fossil jet fuel cost is an IEA chart value
  for 2019 by way of Becattini et al. 2021 (CC BY-NC-ND), so that side says there is no fossil comparator. No open
  same-basis source was found for plastics or cultivated meat. gardarsdottir-2019 and siegrist-2024 are manual
  snapshots because ETH's repository stamps a new cover page on every download.
- **UNSD and the IEA** (open question, 2026-10-08). UNSD's metadata says its data for OECD and EU countries are
  obtained through the IEA and that historical data may come from the IEA World Energy Statistics Database. The
  existing `unsd-energy` views stay as they are until UNSD answers (owner, 2026-10-08); no new view uses UNSD.

## Decisions on the Lancet Countdown 2025 additions (2026-10-12)

Evidence: docs/research/sources-consequences-2026-10-11.json and docs/research/sources-extremes-2026-10-12.json (the
Lancet 1.2.1, 1.2.2, 1.2.3 and 3.2.1 entries). Workbooks 3.2.1, 1.2.1 (mortality), 1.2.2 and 1.2.3 became artifacts of
`lancet-countdown-2025` (CC BY-NC-SA 4.0, noncommercial), and the 1.1.1 vulnerable-populations workbook, registered on
2026-10-04, got its transform. Only the Global sheets are read (the 1.1.1 and 1.1.3 country sheets were added later
the same day; see "what the changes mean where you live").

- **3.2.1 is used although IEA World Energy Balances are among its inputs.** Those balances are rejected below for
  redistribution. Here they are one input to IIASA's GAINS model: the workbook publishes the authors' modelled deaths,
  death rates and PM2.5 concentrations and no IEA values, and only the deaths are used. Its third-party clause ("subject
  to the license terms from the original third-party authors") is recorded in the registry. The owner is to confirm
  this reading.
- **One sum, inside one file.** `air-pollution.lancet-2025.fossil-deaths` adds the coal and the liquids-and-gas deaths
  over the seven sectors of the 3.2.1 Global sheet, as the report's own key finding does, and is checked against it
  (2.68 million in 2010 and 2.52 million in 2022; the sums are 2,677,081 and 2,522,076). It is kind `derived`, credited
  "Calculated by Environment Dashboard from …". Nothing is added across workbooks or sources.
- **What each may say.** Wildfire-smoke deaths count all fire smoke and are not attributed to climate change. Deaths
  from fossil-fuel air pollution are a harm of the burning itself, not of the warming. The drought share is a
  meteorological index (SPEI-6, against 1986–2005) that warmer air itself pushes towards drought; it is not drought
  caused by climate change, nor water or crop shortage. Extreme-rainfall days come from the ERA5-Land reanalysis, which
  does not directly assimilate rain-gauge data, and are not floods. Heatwave days of over-65s and infants are heat of any cause.
- **Left out, as published gaps.** The 12-month drought share (NA in 15 of its 74 years); 1.2.3's land-share sheet
  (irregular nine- or ten-year windows, fractions under a "%" heading); and the over-75 columns of 1.1.1 vulnerable
  (not described by the guidance sheet, and 0 in every year before 2000). 1.2.3 has no values for 1991–1994, and that
  gap stays a gap.
- **Upstream credits.** 1.2.2 names SPEI without a version (SPEIbase is ODbL), so the notice credits SPEI. The Copernicus
  notice now names only the indicators computed from ERA5 or ERA5-Land (1.1.1, 1.1.3, 1.1.5 and 1.2.3).

## Decision on a second estimate of deaths from fossil-fuel air pollution: Lelieveld et al. 2023 (2026-10-12)

Evidence: docs/research/sources-consequences-2026-10-11.json (research[5] candidate 1 and verification[5] verdict 1).
The Lancet Countdown's 3.2.1 gives 2.52 million deaths in 2022; Lelieveld et al. (BMJ 383: e077784) give about 5.13
million in 2019. Respected sources that disagree are shown side by side (docs/style.md), so Lelieveld is registered as
a twin of `lancet-countdown-2025`.

- **The data deposit, not the article** (`lelieveld-2023`, CC0 1.0, open). The authors deposited the model output in
  Edmond, the Max Planck Society's repository (doi:10.17617/3.T7XAXH, version 2, 23 November 2023); the licence is read
  from the repository's Dataverse API record, which also serves the files. The BMJ article is CC BY-NC 4.0 and is not
  fetched or re-hosted: only its abstract sentence with the printed figure and its 95% confidence interval is quoted,
  with its citation, as the publisher check and on the observation. The repository's community norm asks for a
  citation, so the credit names the deposit and the article.
- **One subtraction inside one source.** `air-pollution.lelieveld-2023.fossil-deaths` is the WORLD row of the
  all-cause, fine-particle-plus-ozone column ('NCD+LRI+LRI5-+CPO3') in the reference run (mortality_region_2019_ref)
  less the same cell in the run without fossil fuels (mortality_region_2019_noFF), which is how the paper defines
  fossil-fuel deaths: 5,126,627, checked against the abstract's 5.13 million. It is kind `derived`, credited
  "Calculated by Environment Dashboard from …". The reference total and its confidence limits must round to the
  abstract's 8.34 million (5.63 to 11.19), which confirms the column read. Confidence limits cannot be subtracted, so no
  range is calculated; the note quotes the paper's own interval (3.63 to 6.32 million).
- **Why they differ, as the producers describe their methods.** Lelieveld counts ozone as well as fine particles and
  removes every fossil-fuel emission at once in a second run of the EMAC model (2019, with NASA satellite-based fine
  particles); the authors attribute their higher estimate to the new FUSION relative-risk model, counting deaths from
  all causes as well as from specific diseases, and the large fall in exposure when fossil fuels are removed entirely.
  The Lancet Countdown counts fine particles alone and shares deaths out by sector and fuel with IIASA's GAINS model
  (meteorology fixed at 2015). The years differ too. The two are never added, averaged or drawn as one series.
- **Not used yet.** The country files (names with trailing tabs, which need a crosswalk to ISO codes), the half and
  quarter phase-out and no-anthropogenic runs, the cause-specific columns, and the 1.27 GB model code. In the country
  files the model leaves almost no deaths in some high-income countries without fossil fuels (Germany 0), a property of
  the model that a country view would have to explain.

## Decisions on what the measurements mean for people (2026-10-12)

Evidence: docs/research/sources-consequences-2026-10-11.json (coasts, and the critic's section 4).

- **People on land below high tide and below the yearly flood level: Kulp & Strauss 2019** (`kulp-strauss-2019`,
  CC BY 4.0, Nature Communications 10: 4844). Open on the article's own licence paragraph (publisher's PDF, page
  12); its Supplementary Data carry no licence of their own and the data availability statement puts the national
  exposure tables "within this article and its supplementary information files". The CoastalDEM elevation grid
  itself is a separate Climate Central product "available at no cost ... for non-commercial research use"; it is
  not fetched or re-hosted, so the article's files may be mirrored. Only the World rows and the CoastalDEM columns
  of Supplementary Data 1 are published, as printed (millions of people; median with the 5th to 95th percentiles as
  a 90% interval). The SRTM, JAXA and MERIT columns are not used (the paper's finding is that they understate
  exposure). The country rows are published separately, in people (see "what the changes mean where you live").
  - **Which projections.** The abstract's lead figure (190 million below high tide by 2100 under low emissions,
    150–250 million) is K14 (Kopp et al. 2014), the set the paper calls probabilistic and closely aligned with IPCC
    findings; its high end ("up to 630 M" below the annual flood level by 2100) is the 95th percentile of K17 (Kopp
    et al. 2017, unstable Antarctic ice, not probabilistic). Both sets are therefore published as values of a
    `projection` dimension, never mixed; the build checks that the abstract's figures are those cells. Both predate
    the IPCC's AR6, and the indicators say so.
  - **Time.** Every row counts the people of LandScan 2010, so the present day is dated 2010 (its sea level is that
    of 2000, the projections' zero) and 2050 and 2100 are projections with the population held as it was in 2010:
    they show where today's people live relative to future seas, not future populations.
  - **Exposure, not flooding.** It is a bathtub model: sea walls and levees are not counted (the paper says levee
    locations are not available globally), so protected coasts such as the Netherlands are included.
  - **Author Correction** (doi:10.1038/s41467-019-13552-0, 12 December 2019). A code error fixed in peer review had
    left superseded numbers in the text: 230 M (not 250 M) below 1 m, 94 M (not 95 M), and one cell of Table 1
    (K17, RCP8.5, annual flood, 2100: 480 (380–630), not 500 (390–640)). The Supplementary Data were not affected.
    The registered PDF is the corrected one; the transform checks all 24 CoastalDEM totals of its Table 1 against
    the file, so a PDF still printing the superseded cell stops the build, and the publisher cross-checks quote only
    the corrected text.
  - Lancet Countdown indicator 2.3.3 uses the same CoastalDEM method with 2024 population (people below 1 m of
    future rise, noncommercial); it is not combined with these values.

## Decisions on what the changes mean where you live (2026-10-12)

The owner had deferred per-country "so what" views; this round adds them from files already registered and
downloaded, so no new source and no new licence. Evidence: docs/research/sources-consequences-2026-10-11.json.

- **Lancet Countdown 1.1.1 and 1.1.3 country sheets** (`lancet-countdown-2025`, CC BY-NC-SA 4.0). The attributable
  heatwave workbook's country sheet gives 220 countries and territories, 2020–2024, by ISO3 code; it is published with
  the World row as `heat.lancet-2025.heatwave-days-countries` (each row checked: observed = counterfactual +
  attributable; every country has every year of the Global sheet). Two rows have a negative attributable value
  (Pakistan 2021 and 2023: fewer heatwave days than the modelled world without the warming); they are published as
  they are. The work-hours workbook's country sheet gives 219; only hours lost per worker (`TotalSunWHLpp`, checked to
  equal total hours over the people employed) is published, with the World, as
  `heat.lancet-2025.labour-hours-per-worker`, since a country's total hours mostly measure its size. Its 204
  `#DIV/0!` cells (no one employed in the four sectors in the producer's sheet: every year of Andorra, French Guiana,
  Liechtenstein, Monaco, San Marino and the Seychelles) and one blank (Zimbabwe 2022) are published as missing with
  that reason, never filled. Every ISO3 code is in the entity crosswalk.
- **Kulp & Strauss country rows** (`kulp-strauss-2019`, CC BY 4.0). The 134 country and territory rows of
  Supplementary Data 1 are published with the World rows as `coastal.kulp-strauss-2019.below-high-tide-by-country`
  and `…annual-flood-by-country`, in people (the printed millions times one million, exact; two significant figures
  as printed), because country values down to 0.01 million cannot be read in whole millions. Place names map to
  entities through an explicit alias table (`envdash/geo.py`, ten names such as "Côte d'Ivoire" and "United
  States"); the authors' SIDS group is left out by name. The file leaves out places whose largest exposure is under
  0.01 million, so a country missing from it has no value (the view says "No data for … in Kulp and Strauss's
  coastal estimates"), never zero.
- **On the dashboard.** Each heat country view opens with a "caused by the warming" card for that country's heatwave
  days (the producer attributes them); without Lancet values the view says "No data for … in the Lancet Countdown's
  heatwave days". The work hours are heat of any cause and say so.
- **CCKP's heat-index days and hot nights** (`wb-cckp`, open) are on the home page's future map, with hot days, the
  hottest day, the longest dry spell and warming, for every country and every state or province (below). The wettest
  day is registered but withheld: CCKP's national values lie below the area-weighted mean of their own regions in
  6,086 of 6,630 values, which the method CCKP documents cannot give
  (`pipeline/src/envdash/transforms/future/cckp_projections.py`, "Withheld"). The owner agreed on 2026-10-17 to keep
  it withheld until CCKP's gridded rx1day climatology is compared with its area values, or CCKP explains them.

## Decisions on extreme weather: IPCC figure data and land TXx (2026-10-12)

The owner asked to show extremes becoming more frequent because of climate change. Evidence:
docs/research/sources-extremes-2026-10-12.json, with its verifiers' `honest_wording` (what each dataset may and may
not be used to say).

- **IPCC AR6 WGI Figure SPM.6 data** (`ipcc-ar6-wg1-spm6`, CEDA, CC BY 4.0 on the catalogue record and in the
  directory's License.txt and metadata.yaml): how many times as often a once-in-10 (or once-in-50) year hot day,
  wettest day or drought of 1850–1900 occurs at 1, 1.5, 2, 3 and 4 °C of global warming. Open because the data files
  carry their own CC BY grant; the IPCC's figure artwork and SPM text stay display-only under `ipcc-ar6-wg1-spm`, so
  the figure is redrawn from the CSVs and its printed labels are used only as cross-checks. These are CMIP6 model
  results at a warming level, not observed counts and not years: they are dated 2021 (the assessment) and never
  placed on a time axis or interpolated, and the 1 °C level is not "today". Drought covers the 16 drying regions the
  figure computes (17 listed, the Caribbean left out), not the world. The 3 °C level is in the data but not in the
  figure, and its label says so (the build checks the caption's list of levels). The intensity files are registered
  but not published this round.
- **IPCC AR6 WGI Figure SPM.3 data** (`ipcc-ar6-wg1-spm3`, CEDA, CC BY 4.0): the IPCC's assessed type of observed
  change since the 1950s in hot extremes, heavy precipitation and agricultural and ecological drought for each of the
  45 inhabited AR6 regions, with its confidence in a human contribution. Only world counts of regions per category
  are published (kind `derived`, checked against the tallies printed on the figure); regions are not countries, so
  no regional map or value is shown. "Limited data" and "low agreement" mean missing or mixed evidence, not no
  change, and a confidence level is not the size of the human contribution.
- **IGCC 2025 land TXx** (artifact `txx-timeseries` of `igcc-2025`, CC BY 4.0): the hottest day of the year averaged
  over land excluding Antarctica, ERA5 column only, relative to 1961–1990 as the file gives it (IGCC's single 0.51 °C
  offset to 1850–1900 is not applied). The file's Berkeley column is left out because Berkeley Earth's own terms are
  CC BY-NC 4.0, which IGCC's CC BY grant cannot lift; the HadEX3 column (Crown Copyright, OGL v2, ending in 2018) is
  left out too, as one series comes from one dataset and the three are not coverage-matched. TXx is intensity, not
  frequency, and the file attributes nothing; attribution comes only from SPM.3 and SPM.6. ERA5 on the C3S Climate
  Data Store is CC BY 4.0, and the CDS asks for a Copernicus attribution and the EC/ECMWF disclaimer besides, so
  `igcc-2025` now carries them as a notice naming the TXx series, as `lancet-countdown-2025` does for its
  ERA5-derived indicators. A notice is per source, so it also shows on the other IGCC indicators.

## Decisions for the "so what" pairings (2026-10-12)

The owner asked for each climate measurement to be paired with what it means for people. Evidence:
docs/research/sources-consequences-2026-10-11.json and docs/research/sources-extremes-2026-10-12.json.

- **Children born today: Grant et al. 2025** (`grant-2025`, CC BY 4.0, Nature 641:374-379, read from the publisher's
  JATS XML on Europe PMC). Only the world shares the article's text states are published: of people born in 1960,
  about 16% face unprecedented lifetime exposure to heatwaves "regardless of the scenario"; of people born in 2020, 52%
  on the 1.5 °C pathway and 92% on the 3.5 °C pathway (the Results text, with the abstract as a cross-check). The text
  gives no world share for the 2020 cohort on the 2.5 °C pathway, so that cell is published as missing; nothing is read
  from Fig. 2 and nothing is computed. "Unprecedented" is the authors' statistical threshold (more heatwaves in a
  lifetime than the 99.99th percentile of lifetimes simulated in a pre-industrial climate); it is modelled from
  ISIMIP2b, not a count of deaths, and it assumes country-average life expectancy, no migration and no adaptation. The
  2.7 °C current-policies pathway has no world heatwave share in the text (only shares of the most and least deprived
  fifths), so it is not shown. The Supplementary Information's per-country tables are not used in this round (no
  per-country views; some small states print "0 (0)" for 2010 and 2020 after non-zero shares, which needs the authors'
  reading). The analysis code on GitHub has no licence file and is not used.

## Decisions on IDMC disaster displacement (2026-10-12)

Evidence: docs/research/sources-consequences-2026-10-11.json (verification[1]) and
docs/research/sources-extremes-2026-10-12.json (verification[2]).

- **The GIDD event export is downloaded by hand from the GIDD page** (`idmc-gidd`, artifact `gidd-disaster-events`,
  noncommercial). The registry used to say the GIDD page had no button for it; it has one: with Cause set to Disaster,
  "Excel" under "Annual displacement data" downloads the event file. The API still answers 403 without our own
  client_id, so the source stays manual until IDMC issues the key. The owner downloaded the file on 2026-10-12
  (2,968,931 bytes, sha256 25c78f15…d0d2d3). Its README says "LAST UPDATE: August 31, 2026", "DATE EXTRACTED: October
  05, 2026" and "USE LICENSE: This content is licensed under CC BY-NC", which is looser than the API documentation's
  CC BY-NC-SA 3.0 IGO, so the share-alike terms, the credit, and the website's no-logo and no-endorsement clauses
  still apply. The README's coverage text ("running through 2024") lags its own 2025 rows.
- **Weather-related displacement by hazard is a sum inside this one file**
  (`displacement.idmc-gidd.weather-by-hazard`, kind derived, credited as calculated from IDMC event data). It keeps
  IDMC's own Hazard Category "Weather related", which leaves out geophysical events (earthquakes, volcanic activity,
  dry mass movement) and IDMC's "Mixed disasters" without a judgement of ours, and adds up the raw figures by year
  and IDMC's Hazard Type. Events with no reported figure are left out, never counted as zero, and the description
  says how many. For 2008 and 2010-2016, IDMC files China's displacement as one "Mixed disasters" row a year, not
  split by hazard (26,822,000 in 2008), so China is not in those years' weather-related sums, nothing is estimated in
  its place, and the description says those years are not comparable with later ones. IDMC's Global Report on Internal Displacement prints weather-related and per-hazard totals built
  another way, so there is no publisher check against it and its figures are never mixed in. What it can say: how
  many times people had to move because of weather-related disasters in the events IDMC recorded. What it cannot
  say: that disasters or displacement are becoming more frequent (IDMC records many more events than it did), that
  climate change caused them, or a number of people (one person can be displaced more than once).

## Decisions on the future map's shapes (2026-10-16)

The future map colours each country, and each state or province, by CCKP's projections (`wb-cckp`). Its shapes are
the World Bank's own boundaries, registered as `wb-gad-v1`. `envdash geo shapes` (`envdash/geo_shapes.py`) simplifies
them into `data/v1/geo/` and matches CCKP's region codes to them; `envdash build` runs it when its inputs change.
Evidence: the research of 2026-10-15/16 for the future map, re-checked on 2026-10-16.

- **Which boundaries: World Bank Official Boundaries, GAD V1 of 7 May 2025** (`wb-gad-v1`, open). It is the release
  CCKP aggregates its regions on. CCKP's region code can be rebuilt from its admin-1 attributes: as
  `{ISO_A3}.{GAUL_0}{GAUL_1}` for 2,315 regions, and as `{ISO_A3}.{GAUL_0}{int(ADM1CD_t[3:])}` for 470 more, the names
  agreeing. India matches 35 of 35 this way (IND010 Delhi is CCKP's IND.11510). The key is ISO_A3, not WB_A3: CCKP's
  country codes are ISO_A3 codes (Kosovo is KSV), and WB_A3 is blank for Iraq and Haiti and puts Taiwan and France's
  overseas regions under another country's code.
- **Licence.** CC BY 4.0 with the World Bank Dataset Terms. The dataset's catalogue page reads "This dataset is
  licensed under Creative Commons Attribution 4.0". The zip carries no licence of its own. The AWS registry's label
  for the bucket is inconsistent and is not relied on. **An assumption the owner accepted on 2026-10-17:** the catalogue
  now offers only later versions (its version history starts on 2026-05-14), so V1 is taken to be under the same CC BY
  4.0, as an earlier release of the same World Bank dataset that the World Bank itself hosts in CCKP's open bucket.
- **Fetching.** The zip is 264,700,182 bytes. Only 11 of its members are read, by range requests: the .shp, .shx and
  .dbf of ADM0, ADM1 and NDLSA, plus one .prj and one .cpg, since those two are the same bytes in every layer. A
  fetch whose zip has the same size, ETag and Last-Modified keeps every snapshot after a one-byte request.
- **Matching.** A code match counts only when the names agree. 152 pairs are declared in
  `pipeline/geo/cckp-adm1-declared.csv`, each with its reason: 80 accepted and 72 rejected.
  - Rejected: Kenya (45), Iraq (15), Djibouti (5) and South Sudan (3), whose units CCKP numbers in an order of its
    own, and four records that share a neighbour's GAUL code (Bogotá; Bekaa and North in Lebanon; North West in
    Sierra Leone).
  - Accepted: Morocco's and Nepal's regions named by number; Hong Kong, Macao and Taiwan, which CCKP names by their
    codes; and, in countries with as many CCKP regions as shapes, names differing in spelling, language or encoding.
    These are Canada's bilingual names, Mexico's garbled accents ("Nuevo Le¢n"), Mongolian transliterations,
    Cyprus's Greek names, and the Philippines' numbered regions and Bangsamoro (below).
  - The name rule applies only where a country has as many CCKP regions as shapes. It is withheld in 29 countries,
    such as Indonesia, whose 33 CCKP provinces predate the splits of 2012 and 2022 (38 shapes). A shared name there
    can name a different shape.
  - The regions are those of `pipeline/geo/entities.csv`: CCKP's 3,530 region codes less its 32 DIS.* units and the
    three units it lists under China for Hong Kong, Macao and Taiwan, which are places with regions of their own. The
    build stops if the entity table was built from another names file or lacks one of these regions.
  - Result: 3,176 of these 3,495 regions are on a shape, and 217 of 246 countries are fully matched. The other 319
    regions are listed, never drawn on a guessed shape.
  - **The Philippines, kept as drawn by the owner's decision of 2026-10-17.** CCKP's 17 regions are matched to V1's 17 records by declaration,
    Bangsamoro (PHL.1961) included. V1's NAM_1 calls that record ARMM, but its P_NAME_1, from the P-code list of
    2023-11-06, calls it "Bangsamoro Autonomous Region In Muslim Mindanao (BARMM)": CCKP's name with the abbreviation,
    as for the Cordillera (CAR) and the capital region (NCR). V1's Philippine shapes are UN SALB's of 2013, from before
    the 2019 plebiscite: Cotabato City and the barangays of North Cotabato that then joined Bangsamoro lie in Region
    XII's shape (CCKP's Region 12, PHL.1969), not in ARMM's. Both regions are drawn on these shapes. If CCKP averages
    over V1's shapes, as its codes elsewhere suggest, both are right; if it uses the borders of 2019, both shapes are
    off by that area. The alternative, not taken, was to remove both declarations, which would leave both regions
    listed without a shape and their two shapes grey.
  - The table by country, `pipeline/tests/expected/cckp-join-by-country.csv`, makes any change show as a diff.
- **A country's value against its regions (a diagnostic, not a check).** The check that stops the build is in
  `cckp_projections.py`: each national value lies within its regions' range. A national value can pass it and still
  be weighted wrongly, so `pipeline/tests/test_geo_area_weighted.py` compares it with the mean of its regions'
  values weighted by their areas (V1's shapes measured on the WGS 84 ellipsoid). It reads the 2040–2059 SSP2-4.5
  medians of the 172 countries with two or more regions, all on shapes.
  - The gap is within half the site's last printed digit in 167 countries for hot days, 154 for hot nights, 169 for
    heat-index days, 166 for the hottest day, 135 for the longest dry spell and 167 for warming.
  - Pakistan's gap is the largest for every heat and dry measure: its national value has 11.45 fewer hot days than
    the weighted mean of its regions. Guinea-Bissau's and India's are next, at 5.83 and 3.17 fewer. V1's shapes of
    Pakistan and India leave out Jammu and Kashmir, a disputed area. CCKP does not publish the national areas it
    averages over, so whether its national values include that area is not known.
  - For the wettest day, the gap is within 0.5 mm in only 29 countries, and the national value is the lower one in 162.
    The largest gap is the Philippines', at 17.68 mm. CCKP's national figure for this measure is not an area mean of
    its regions' figures; the national check found it below every region in 859 country values.
  - The result by country is `pipeline/tests/expected/cckp-area-weighted.csv`. Nothing on the site combines regions
    into a country.
- **Simplifying.** The shapes are simplified as one topology per file, so shared borders stay shared.
  - `world.topo.json` is 210,843 bytes (limit 250,000). Its epsilon is 0.25°, polygons under 0.05 square degrees are
    left out, and 192 of 245 countries are drawn; the rest are points.
  - 224 country files total 3,961,701 bytes. The largest is Guinea-Bissau's at 70,841 bytes (limit 200,000).
  - Every feature keeps a representative point of its full shape, so no place is lost.
- **Names.** Regions take CCKP's names, except seven Mexican states whose accented letters CCKP garbles (written in
  code page 437 and read as Windows-1252: "Ciudad de M‚xico", "Yucat n"); they take the name of the World Bank shape
  each is declared to match ("Ciudad de México", "Yucatán"), and a change to CCKP's garbled name stops the build
  (`envdash/geo.py` GARBLED_NAMES).
- **Disputed areas.** The World Bank's 24 non-determined legal status areas are drawn grey with its own names and
  never coloured. CCKP's 32 DIS.* units are left out.
- **When CCKP changes boundaries.** CCKP's portal says it will move to the World Bank's newer boundaries. When it
  does, its region codes change and the build stops: code matches no declaration explains, and declarations no
  longer needed (a rejection no code rule makes, or an acceptance that the code or name rules already make). The
  region maps keep their last version until someone re-matches them.

## Rejected

Recorded on 2026-10-04 while building the first registry. Each entry gives the clause or the reason, so it can be
re-checked if the terms change.

- **Oxfam/SEI 'Climate Equality: A planet for the 99%' datasets (alternative carbon-inequality numbers)** (https://policy-practice.oxfam.org/copyright-permissions/): Oxfam copyright page (fetched 2026-10-04): 'If you wish to make commercial use of any of our material, or if you wish to make any alterations or modifications (including translations), you must contact us for permission.' Re-hosting or deriving from the datasets is not covered by the personal-use or short-extract waivers. The SEI Emissions Inequality Dashboard API (CC BY 4.0) is used for the numbers instead.
- **Global Carbon Budget 2025 xlsx downloads on globalcarbonbudget.org (download/2341, 2345, 2348)** (https://globalcarbonbudget.org/download/2341/?tmstv=1762815901): Not rejected on licence. These are the 10 Nov 2025 pre-release files, equivalent to the deprecated ICOS v0.1: the national file is 739,007 bytes against 755,198 for v1.0. The links still answer 206, but the pinned ICOS v1.0 object PIDs are used instead.
- **IEA Global EV Outlook 2026 data product (XLSX 'EV data by country', IEA account required)** (https://www.iea.org/data-and-statistics/data-product/global-ev-outlook-2026): Product page licence: 'Terms of Use for Non-CC Material' (Internet Archive copy 2026-10-01), not CC BY. Only the report and the Global EV Data Explorer / api.iea.org/evs are CC BY 4.0.
- **Energy Institute Statistical Review 2026 data files (EI-Stats-Review-ALL-data.xlsx, narrow and panel CSVs)** (https://www.energyinst.org/statistical-review/resources-and-data-downloads): EI terms: 'Any use or reproduction of such documents for any other purpose whatsoever is expressly forbidden without the written permission of the EI. No licence or right, other than the right to view on the Sites, is granted'. The report adds 'The redistribution or reproduction of data whose source is S&P Global Energy or S&P Global Inc, is strictly prohibited without its prior authorisation.' Only quoted statements are used (energy-institute-review-2026).
- **IRENASTAT PxWeb tables (Country/Region_ELECSTAT_2026_H2_PX.px) — deferred, not registered** (https://pxweb.irena.org/pxweb/en/IRENASTAT/IRENASTAT__Power%20Capacity%20and%20Generation/Country_ELECSTAT_2026_H2_PX.px/): The site footer reads '© IRENA - International Renewable Energy Agency. All Rights Reserved.' while the table metadata reads 'Copyright: No', so the terms conflict and need written confirmation from IRENA. Data is also served only to POST queries, which Artifact.access (GET-only) cannot express. The 2026 capacity PDF is used instead.
- **IRENA RPGC 2025 data file sheets 'Fig. 9.5' and 'Fig. 9.7' (energy storage costs)** (https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Jul/IRENA_TEC_RPGC_in_2025_data_file_2026.xlsx): Sheets are labelled 'Based on BNEF data'. The publication says 'Material in this publication that is attributed to third parties may be subject to separate terms of use and restrictions, and appropriate permissions from these third parties may need to be secured before any use of such material.'
- **IEA Global EV Data Explorer car price rows (price_*_2025USD, sales-historical-price-data)** (https://api.iea.org/evs?category=Historical&year=2025&csv=true): The report credits them as 'IEA analysis based on data from S&P Global Mobility'. The IEA Notice says the OECD/IEA 'does not license … any component within the CC-licensed Content that is attributed to a third-party'. Not used; the raw API file is therefore not mirrored.
- **Scarborough et al. 2023 ORA dataset (Results_21Mar2022.csv, doi:10.5287/ora-5zebayaog)** (https://ora.ox.ac.uk/objects/uuid:ca441840-db5a-48c8-9b82-1ec1d77c2e9c): DataCite rightsList on 2026-10-04 is http://www.rioxx.net/licenses/all-rights-reserved. ORA terms allow one copy for private non-commercial study only. Use the CC BY article tables and source data instead.
- **Scarborough et al. 2023 analysis code (PeteScarbs/environment-impact-of-diets)** (https://github.com/PeteScarbs/environment-impact-of-diets): The repository has no licence (research verifier); not reusable.
- **UN SDG Global Database API as the route for UNEP food waste (AG_FOOD_WST, AG_FOOD_WST_PC)** (https://www.un.org/en/about-us/terms-of-use): The unstats.un.org SDG site footer links to the UN Terms of Use: 'download and copy the information ... for the User's personal, non-commercial use, without any right to resell or redistribute them or to compile or create derivative works therefrom'. The values are taken from UNEP's own report PDF under UNEP's notice instead.
- **IUCN Red List website, API v4 and summary statistics** (https://www.iucnredlist.org/terms/terms-of-use): IUCN Red List Terms and Conditions of Use v3.1 (June 2024), section 4 'No Reposting and/or Redistribution': all forms of reposting, sub-licensing or redistribution of IUCN Red List Data need IUCN's written permission. The site returns 403 to scripts; read via the Internet Archive. Use the CC BY GBIF checklist instead.
- **Living Planet Database population records (underlying LPI data)** (https://www.livingplanetindex.org/documents/data_agreement.pdf): LPI Data Use Policy clause 4: 'The recipient will not pass the original datasets on to third parties'. Clause 5: 'will not publish the data in their original format, either whole or in part, on a website'. Only the published trends (clause 3, CC BY-SA 4.0) are used.
- **Climate Reanalyzer daily SST JSON (University of Maine), as an OISST shortcut** (https://climatereanalyzer.org/clim/sst_daily/json_2clim/oisst2.1_world2_sst_day.json): Returns HTTP 403 to non-browser clients, and neither its sst_daily nor its about pages state a licence (verifier, sources-ocean-and-ice.json). It is a derivative, not the producer. oisst-v2 computes the global mean from NCEI's own NetCDF files instead.
- **NOAA Climate at a Glance global CSV, as the NOAAGlobalTemp input** (https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series/globe/land_ocean/12/12/1850-2026/data.csv): Not a licence problem (it is public domain). Rejected for method: it uses a 'Base Period: 1901-2000' and two decimals, while the v6.1 .asc files use 1991-2020 at six decimals. The plan rebases NOAAGlobalTemp to its own 1850-1900 mean, and the two baselines must never be mixed.
- **GISTEMP GMSTA predictions CSV, as GISS's '1850-1900-referenced series'** (https://data.giss.nasa.gov/gistemp/gmsta/data/Annual_GISTEMP_GMSTA_Predictions_202609.csv): This is the only GISS file on a 1850-1900 basis, but it holds forecasts for 2026 and 2027 (NMME, ENSO and year-to-date regressions), not observations. Its 1850-1900 offset is borrowed from five other datasets.
- **Rutgers Global Snow Lab monthly snow cover tables (moncov.nhland.txt and siblings)** (https://climate.rutgers.edu/snowcover/files/moncov.nhland.txt): No licence is stated. These are Rutgers derivatives; the NOAA CDR 'no restrictions' policy covers only the NCEI CDR. The verifier found the same, and the task said not to use them. The NCEI NetCDF CDR is used instead (rutgers-snow-cdr).
- **AWS Open Data copy of the NH snow cover extent CDR (noaa-cdr-snow-cover-ext-north-pds)** (https://noaa-cdr-snow-cover-ext-north-pds.s3.amazonaws.com/index.html): Stale as an artifact location. The bucket listing on 2026-10-04 holds only nhsce_v01r01_19661004_20210405.nc (data to April 2021) plus documentation.
- **NCEI legacy 3-month ocean heat file 3month/h22-w0-2000m.dat** (https://www.ncei.noaa.gov/data/oceans/woa/DATA_ANALYSIS/3M_HEAT_CONTENT/DATA/basin/3month/h22-w0-2000m.dat): Stale. Last-Modified 9 Oct 2020 and it ends at 2010.5. Current quarterly values are in h22-w0-2000m1-3.dat and the other quarter files; the yearly and pentadal files were registered instead.
- **OSI SAF sea-ice index THREDDS link given in the research (osisaf_420siiv3p0.html)** (https://thredds.met.no/thredds/osisaf/osisaf_420siiv3p0.html): The link returns 404, per the verifier. The working catalogue is https://thredds.met.no/thredds/catalog/osisaf/osisaf_seaiceindex.html (HTTP 200 on 2026-10-04). The plain HTTPS text files were used instead.
- **Our World in Data mirror of GWIS burned area (annual-area-burnt-by-wildfires-gwis)** (https://ourworldindata.org/grapher/annual-area-burnt-by-wildfires-gwis): Aggregator copy. AGENTS.md rule 5 requires the licence class to come from the producer, never an aggregator, and provenance must point at the primary file. The OWID series is a minor-processing copy of the GWIS API: WORLD lc_tot for 2025 is 332,928,197.5 ha in both. gwis-burned-area uses the GWIS API directly.
- **HDX copy of IDMC disaster displacement data (licence metadata CC BY-IGO)** (https://data.humdata.org/dataset/idmc-internal-displacements-new-displacements-associated-with-disasters): HDX metadata says license_id cc-by-igo. IDMC's own API documentation says 'Data is available under the Creative Commons Attribution-Non-Commercial-Share Alike 3.0 IGO license', so the producer's terms apply. The HDX CSV is also older than the GIDD export (README dated 31 Aug 2026). Not used as a licence source or as the data channel.
- **GWIS Country Profile bulk downloads (MCD64A1/GlobFire/GFED/FAO/GFAS full-dataset ZIPs)** (https://effis-gwis-cms.s3.eu-west-1.amazonaws.com/apps/country.profile/MCD64A1_burned_area_full_dataset_2002_2024.zip): The app's Data downloads page lists these files, but on 2026-10-04 every one returned HTTP 404 from S3: the 2002_2024 names, the 2002_2025 variants and user_guide_2023.pdf. They cannot be registered until JRC restores them.
- **wri/wri-scl-data-prod-public GitHub repository (Systems Change Lab raw data)** (https://github.com/wri/wri-scl-data-prod-public): It could be pinned to a commit, but it has no licence file (GitHub reports no licence) and no metadata or source attribution per indicator. Without the provider list, IEA-sourced indicators cannot be excluded, so the official /scl-download/all export is used instead.
- **NASA/IPCC AR6 Sea Level Projection Tool** (https://sealevel.nasa.gov/ipcc-ar6-sea-level-projection-tool): The URL named in the Zenodo record returns HTTP 404 (2026-10-04); the NASA material now sits under earth.gov/sealevel. The Zenodo record (doi:10.5281/zenodo.6382554) is the primary source instead.
- **Global Climate Change Survey microdata (IZA Data Service Center, doi:10.15185/gccs.1: Country_data.zip, Replication.zip)** (https://dataverse.iza.org/dataset.xhtml?persistentId=doi:10.15185/gccs.1): Licence IIL-1.0, registration required: 'Users are prohibited from using data acquired from the IDSC in the pursuit of any commercial or private ventures. The data will be used only for scholarly, research, educational purposes or replications.' Only the paper and its CC BY Supplementary Information are used (andre-2024).
- **World Bank Carbon Pricing Dashboard data downloads** (https://carbonpricingdashboard.worldbank.org/): Every page returns HTTP 403 with 'cf-mitigated: challenge' (Cloudflare) to scripts, so the data licence could not be read. Not registered; only the CC BY 3.0 IGO report is used (wb-carbon-pricing-2026).
- **Drawdown Explorer website CSV export** (https://drawdown.org/explorer-solutions-table-export.csv): Carries no licence of its own. drawdown.org's generic Terms of Use say users 'won't use, copy, reproduce, modify ... any Content not owned by you, (i) without the prior consent of the owner'. The CC BY 4.0 Zenodo deposits are used instead (drawdown-explorer).
- **WDI EG.CFT.ACCS.ZS (access to clean fuels and technologies for cooking)** (https://api.worldbank.org/v2/sources/2/series/EG.CFT.ACCS.ZS/metadata?format=json): License_Type says CC BY-4.0, but the indicator's source note reads 'License: Creative Commons Attribution—NonCommercial 3.0 IGO (CC BY-NC 3.0 IGO)'. Under the World Bank's 'Exceptions for Some Third-Party Data' clause that note governs, so it is kept out of the open wb-wdi entry. It would need its own noncommercial entry.
- **Climate Watch NDC overview query (all categories)** (https://www.climatewatchdata.org/api/v1/ndcs?category=overview): Mixes in indicators from other organisations under their own terms: Net Zero Tracker, LSE CCLW, World Bank, UNICEF (whose metadata says licence 'None'), NDC Explorer, Pledges and LTS. Only the Climate Watch-sourced 2025 NDC Tracker indicators are registered.
- **Stechemesser et al. 2024 Science article text and figures** (https://doi.org/10.1126/science.adl6547): The article carries no open licence (Crossref lists none) and science.org returns HTTP 403 to scripts. Only the CC BY 4.0 Zenodo replication deposit is used.
- **Zenodo files-archive zip of Stechemesser record 12773811** (https://zenodo.org/api/records/12773811/files-archive): Not a licence problem. The zip is generated on each request: two downloads 3 seconds apart had different sha256 values, so every weekly run would record a new 'vintage'. The individual CSV files are registered instead.
- **EM-DAT (CRED) portal exports**: the terms forbid distributing "a substantial part" of the database, sharing any
  portion via the Internet, and building derivative databases. The FAIR archive (doi:10.14428/DVN/I0LTPH) is
  CC BY-NC-ND and may be used later as `no-derivatives` aggregate charts.
- **Berkeley Earth**: the licence (CC BY-NC 4.0) would be acceptable on this non-commercial site, but the current
  high-resolution product is labelled preliminary and not yet peer-reviewed, and the country series need a request
  form. Revisit when it is published.
- **IEA World Energy Balances and other paid IEA datasets**: not CC licensed; no redistribution.
- **Carbon Majors database**: its terms forbid republishing and derivatives.
- **GADM boundaries**: "Redistribution or commercial use is not allowed without prior permission." Climate TRACE's
  admin ids are crosswalked to Natural Earth instead.

Recorded on 2026-10-05 while researching personal footprints (docs/research/sources-ghg-food-personal-2026-10-05.json):

- **WID.world per-capita emissions by income group (wid_all_data.zip, lpfghg* variables)** (https://wid.world/): on 2026-10-05 every wid.world path returned a 114-byte page redirecting to /lander (a parked domain), so the data licence cannot be read from the producer. The world-inequality-database GitHub repositories carry no data licence. Revisit when wid.world is restored.
- **Hot or Cool Institute (2021), 1.5-Degree Lifestyles; Sitra/IGES/Aalto (2019), 1.5-Degree Lifestyles**: the only rights statements are 'Copyright Hot or Cool Institute, Berlin. October 2021.' and '© Sitra 2019', with no licence (display-only). iges.or.jp returns HTTP 403 to scripts.
- **OECD Greenhouse Gas Footprints 2025 (DSD_ICIO_GHG_MAIN_2025, demand-based GHG per person) — deferred, not registered** (https://www.oecd.org/en/about/terms-conditions.html): www.oecd.org returns 403 to scripts, so the dataset terms could not be read. The methodology paper is CC BY 4.0 'except third-party material', and the model uses IEA 'Greenhouse Gas Emissions from Energy'. A person must read the OECD terms in a browser first.
- **Eurostat env_ac_ghgfp (GHG footprints, FIGARO)**: the metadata says the non-European footprints use EDGAR, which uses IEA data 'licensed under CC BY-NC-ND 4.0', and those emissions feed every EU footprint. It is also split by emitting industry, not by consumption purpose.
- **JRC Consumption Footprint, breakdown by area of consumption — deferred** (https://eplca.jrc.ec.europa.eu/ConsumptionFootprintPlatform.html): licence COM_REUSE (open), but the breakdown sits behind a JSF dashboard form (manual acquisition), runs only to 2021, and is a life-cycle model of household products that is not comparable with input-output footprints.
- **NTNU Environmental Footprint Explorer (environmentalfootprints.org)**: the terms say its materials are 'protected by applicable copyright', with no open licence.
- **Chancel (2022), Global carbon inequality over 1990-2019, Nature Sustainability; Bruckner et al. (2022); Ivanova et al. (2016), Journal of Industrial Ecology**: Crossref gives only publisher TDM or Wiley terms licences, not open.

Recorded on 2026-10-16 while choosing the future map's shapes (see "Decisions on the future map's shapes"):

- **World Bank Official Boundaries, current version (catalogue dataset 0038272, version 3)** (https://datacatalog.worldbank.org/search/dataset/0038272/world-bank-official-boundaries): not a licence problem (CC BY 4.0). Its admin-1 codes (ADM1CD_c, such as IND003) do not rebuild CCKP's region codes. Its units are newer than CCKP's: version 2 merged India's Dadra and Nagar Haveli with Daman and Diu. By name, only 2,210 of CCKP's 3,500 named regions match within their country. GAD V1 is used instead (`wb-gad-v1`).
- **Natural Earth admin-1 (1:10m, public domain)** (https://www.naturalearthdata.com/downloads/10m-cultural-vectors/): not a licence problem. Its "admin-1" is not always the first level: it has 232 counties and unitary authorities for the United Kingdom, 101 departments for France, and Kenya's 8 former provinces instead of its 47 counties. Its codes (adm1_code, iso_3166_2) do not join CCKP's, and by name only 27 countries match one to one.
- **geoBoundaries admin-1** (https://www.geoboundaries.org/): each country's boundary carries its producer's licence. Of 199 admin-1 records, 84 are ODbL and 14 are CC BY-SA, so the class would differ by country and many would be share-alike. Its codes are opaque shape ids, and China's admin-1 includes Taiwan.

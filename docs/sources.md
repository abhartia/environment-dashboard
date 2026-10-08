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

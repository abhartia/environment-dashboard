"""FAOSTAT Emissions totals (GT): agrifood-systems greenhouse gas emissions by country, for the European Union and for
the world, in million tonnes of CO₂-equivalent (IPCC AR5 100-year global warming potentials).

Input. Emissions_Totals_E_All_Data_(Normalized).csv in the GT bulk zip (UTF-8, CRLF, every field quoted; columns Area
Code, Area Code (M49), Area, Item Code, Item, Element Code, Element, Year Code, Year, Source Code, Source, Unit, Value,
Flag, Note) and its flag codebook Emissions_Totals_E_Flags.csv. The rows used are item 6518 "Agrifood systems",
element 723113 "Emissions (CO2eq) (AR5)", unit "kt", Source "FAO TIER 1" (FAO's own estimates); rows from FAO's
"UNFCCC" source (country inventory submissions) are never mixed in. The names next to the codes must be the ones
above, or the transform stops. Values are divided by 1,000 (kilotonnes to million tonnes, exact decimal arithmetic).

Scope. In every World, region and country row of the release of 28 October 2025, item 6518 equals the sum of its
three parts, "Farm gate" (6996), "Land-use change" (6516) and "Pre- and post-production" (6517), to within 0.0001 kt
(tests/test_food_faostat_country_emissions.py, snapshot test). So it contains FAO's land-use change emissions (net
forest conversion, fires in humid tropical forests and in organic soils) but not the forest sink ("Forestland"), and it
does not contain "International bunkers" (6820), which is a separate item outside the agrifood total.

Areas are mapped by faostat_bulk.AREAS. FAO's former states (USSR to 1991, Sudan (former) to 2011, ...), territories
without an entity and FAO's regional groups (including "China", the sum of mainland China, Hong Kong, Macao and
Taiwan) are left out and named in a processing step.

Projections. Rows flagged F ("Forecast value") are not published and must come after the last estimated year of
their series. Every other flag must be in the codebook. A non-empty Note is copied to the observation.

Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
"""

from __future__ import annotations

import functools
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.food.faostat_bulk import (
    CATALOGUE,
    SOURCE,
    FaostatBulkError,
    Table,
    area_entity,
    flag_step,
    flag_words,
    not_published_step,
    read_flags,
    read_member,
    vintage_of,
    year_of,
)

TOTALS = Input(SOURCE, "emissions-totals")
DATASET_CODE = "GT"
DATA_MEMBER = "Emissions_Totals_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "Emissions_Totals_E_Flags.csv"
COLUMNS = [
    "Area Code",
    "Area Code (M49)",
    "Area",
    "Item Code",
    "Item",
    "Element Code",
    "Element",
    "Year Code",
    "Year",
    "Source Code",
    "Source",
    "Unit",
    "Value",
    "Flag",
    "Note",
]
AGRIFOOD = ("6518", "Agrifood systems")
CO2EQ_AR5 = ("723113", "Emissions (CO2eq) (AR5)")
TIER1 = "FAO TIER 1"
UNIT_KT = "kt"
FORECAST = "F"
MARKER = b'"6518","Agrifood systems","723113"'


def read(lines) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Item Code"] == AGRIFOOD[0] and r["Element Code"] == CO2EQ_AR5[0] and r["Source"] == TIER1

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, MARKER)


def observations(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    if flags.get(FORECAST) != "Forecast value":
        raise FaostatBulkError(f"{FLAGS_MEMBER}: flag {FORECAST} is {flags.get(FORECAST)!r}, not 'Forecast value'")
    estimates: dict[str, list[tuple[int, Decimal, dict[str, str]]]] = defaultdict(list)
    forecast: dict[str, list[int]] = defaultdict(list)
    left_out: set[str] = set()
    for r in table.rows:
        what = f"area {r['Area Code']} {r['Year']}"
        if (r["Item"], r["Element"]) != (AGRIFOOD[1], CO2EQ_AR5[1]):
            raise FaostatBulkError(
                f"item {AGRIFOOD[0]} / element {CO2EQ_AR5[0]} are named {r['Item']!r} / {r['Element']!r}, expected "
                f"{AGRIFOOD[1]!r} / {CO2EQ_AR5[1]!r}"
            )
        if r["Unit"] != UNIT_KT:
            raise FaostatBulkError(f"{what}: unit {r['Unit']!r}, expected {UNIT_KT!r}")
        entity = area_entity(r["Area Code"], r["Area Code (M49)"])
        if entity is None:
            left_out.add(r["Area Code"])
            continue
        year = year_of(r, what)
        if r["Value"] == "":
            raise FaostatBulkError(f"{what}: empty Value; re-read the file before trusting it")
        if r["Flag"] == FORECAST:
            forecast[entity].append(year)
        else:
            estimates[entity].append((year, Decimal(r["Value"]), r))
    if "WLD" not in estimates:
        raise FaostatBulkError(f"no World {TIER1} rows of {AGRIFOOD[1]} / {CO2EQ_AR5[1]}")
    for entity, pts in estimates.items():
        years = [y for y, _, _ in pts]
        if len(set(years)) != len(years):
            raise FaostatBulkError(f"{entity}: more than one {TIER1} value for a year")
        if forecast[entity] and min(forecast[entity]) <= max(years):
            raise FaostatBulkError(f"{entity}: forecast years {forecast[entity]} are not all after {max(years)}")
    counts = Counter(r["Flag"] for pts in estimates.values() for _, _, r in pts)
    words = flag_words(flags, counts, FLAGS_MEMBER)
    thousand = Decimal(1000)
    obs: list[Observation] = []
    for entity in sorted(estimates):
        for year, value, r in sorted(estimates[entity], key=lambda p: p[0]):
            notes = [f"FAO note: {r['Note']}"] if r["Note"] else []
            if len(words) > 1:
                notes.append(f"FAO flag {r['Flag']}: {words[r['Flag']]}.")
            obs.append(
                Observation(
                    entity=entity, period=f"{year:04d}", value=float(value / thousand), note=" ".join(notes) or None
                )
            )
    all_years = sorted({y for pts in estimates.values() for y, _, _ in pts})
    forecast_years = sorted({y for ys in forecast.values() for y in ys})
    steps = [
        f'Kept the "{TIER1}" rows of item "{AGRIFOOD[1]}" (code {AGRIFOOD[0]}), element "{CO2EQ_AR5[1]}" (code '
        f"{CO2EQ_AR5[0]}), {all_years[0]}–{all_years[-1]}, in kilotonnes of CO₂-equivalent (IPCC AR5 100-year global "
        'warming potentials), for every area FAO reports. Rows from FAO\'s "UNFCCC" source are not used.',
        not_published_step(left_out),
        "Converted kilotonnes to million tonnes by dividing by 1,000 (exact decimal arithmetic on the printed values).",
        flag_step(words, counts),
    ]
    if forecast_years:
        shown = " and ".join(str(y) for y in forecast_years)
        steps.append(f'Left out FAO\'s projections for {shown}, which the file flags F ("Forecast value").')
    return obs, steps


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _run(files: dict[str, InputFile]) -> Result:
    table, flags = _read_zip(files[TOTALS.key].path)
    updated, vintage_step = vintage_of(files, TOTALS, DATASET_CODE, table.data_rows, DATA_MEMBER)
    obs, steps = observations(table, flags)
    return Result(
        observations=obs,
        vintage=updated.isoformat(),
        year=str(updated.year),
        date_published=updated.isoformat(),
        steps=[vintage_step, *steps],
        changes="converted from kilotonnes to million tonnes of CO₂-equivalent.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-by-country",
                title="Greenhouse gas emissions from agrifood systems, by country",
                description="Greenhouse gas emissions from each country's food and farming system each year since "
                "1990, in carbon dioxide equivalent: on farms, from clearing land for agriculture, and from making, "
                "moving, selling, cooking and throwing away food, as estimated by FAO with the same method for "
                "every country.",
                kind="series",
                unit=Unit(code="MtCO2e", label="million tonnes of carbon dioxide equivalent", short="Mt CO₂e"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Countries and territories, the European Union (27) and the world",
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis='FAOSTAT item "Agrifood systems" = farm gate (crops and livestock) + land-use change + '
                    "pre- and post-production (fertilizer manufacturing, processing, packaging, transport, retail, "
                    "household consumption and waste disposal). Land-use change counts only what FAO attributes to "
                    "agriculture: net forest conversion (deforestation) plus fires in humid tropical forests and in "
                    "organic soils (peat); the carbon taken up by forests is not subtracted. International aviation "
                    "and shipping bunkers are a separate FAOSTAT item and are not included. FAO Tier 1 estimates "
                    "for every country, not country inventory submissions, so they can differ from a country's "
                    "own inventory.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=6_000, value_range=(0.0, 25_000.0)),
        )
    ]

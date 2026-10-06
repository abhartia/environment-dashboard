"""FAOSTAT Emissions totals (GT): where food's greenhouse gas emissions come from, by FAO's three stages (farm gate,
land-use change, pre- and post-production) and by the 22 processes within them, for the world and each country,
1990-2023.

Input. Emissions_Totals_E_All_Data_(Normalized).csv in the GT bulk zip (columns Area Code, Area Code (M49), Area, Item
Code, Item, Element Code, Element, Year Code, Year, Source Code, Source, Unit, Value, Flag, Note) and its flag codebook
Emissions_Totals_E_Flags.csv. Rows used: element 723113 "Emissions (CO2eq) (AR5)", unit "kt", Source "FAO TIER 1"
(FAO's own estimates; the "UNFCCC" rows, country inventory submissions, are never mixed in), and the items in STAGES
and PROCESSES below, matched by code with FAO's names checked. Nothing is added up or subtracted: each published value
is one row of the file, converted from kilotonnes to million tonnes (both indicators; billion tonnes with two decimals
would show most countries' stages as 0.00).

The parts are FAO's own. In every area and year from 1990, item 6518 "Agrifood systems" equals the sum of the three
stage items, and each stage item equals the sum of its process items present, to within 0.01 kilotonnes (FAO prints
four decimals); `faostat_parts.check_parts` checks this on the whole file at every build and stops otherwise. Where FAO
prints no row for a process (for example no fertilizers manufacturing, food processing or food packaging rows for
Ethiopia), the process is absent, never zero, and the stage still equals the sum of the rows present. Overlapping
FAOSTAT items (Emissions from livestock, Emissions from crops, Emissions on agricultural land, IPCC Agriculture,
Agricultural Soils, AFOLU, LULUCF, Forest fires, and the N2O and CO2 parts of Drained organic soils) are not used.
"Forestland" (6751), the carbon taken up by forests, is not part of "Agrifood systems" and is not published here.

Years. FAO publishes the stage items and the agrifood total from 1990. Some farm items (enteric fermentation, manure,
rice, synthetic fertilizers, crop residues and their burning) go back to 1961 with no stage total to check them
against; those earlier rows are left out of both indicators, so every published year's parts can be checked against
FAO's total. FAO's projections for 2030 and 2050 (flag F) are left out.

Values as printed. Seven process values are negative in the file (synthetic fertilizers, Somalia 2004-2012 and
Timor-Leste 2008 and 2014, at most 0.7 kilotonnes); they are published as printed, and FAO's stage totals include them.

Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
"""

from __future__ import annotations

import functools
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.food.faostat_bulk import (
    CATALOGUE,
    SOURCE,
    FaostatBulkError,
    Table,
    flag_step,
    flag_words,
    read_flags,
    read_member,
    vintage_of,
)
from envdash.transforms.food.faostat_parts import (
    Gathered,
    areas_step,
    check_parts,
    entity_of,
    gather,
    labels_step,
    plain_labels,
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
TIER1 = "FAO TIER 1"
CO2EQ_AR5 = "723113"
ELEMENTS = {CO2EQ_AR5: ("Emissions (CO2eq) (AR5)", "kt")}
AGRIFOOD = ("6518", "Agrifood systems")
FIRST_YEAR = 1990
TOLERANCE_KT = Decimal("0.01")

# FAO item code -> (our stage id, FAO's item name)
STAGES: dict[str, tuple[str, str]] = {
    "6996": ("farm-gate", "Farm gate"),
    "6516": ("land-use-change", "Land-use change"),
    "6517": ("pre-post-production", "Pre- and post-production"),
}
# FAO item code -> (stage item code, our process id, FAO's item name), in FAO's order within each stage.
PROCESSES: dict[str, tuple[str, str, str]] = {
    "5058": ("6996", "enteric-fermentation", "Enteric Fermentation"),
    "5059": ("6996", "manure-management", "Manure Management"),
    "5063": ("6996", "manure-left-on-pasture", "Manure left on Pasture"),
    "5062": ("6996", "manure-applied-to-soils", "Manure applied to Soils"),
    "5061": ("6996", "synthetic-fertilizers", "Synthetic Fertilizers"),
    "5060": ("6996", "rice-cultivation", "Rice Cultivation"),
    "5064": ("6996", "crop-residues", "Crop Residues"),
    "5066": ("6996", "burning-crop-residues", "Burning - Crop residues"),
    "6729": ("6996", "drained-organic-soils", "Drained organic soils"),
    "6994": ("6996", "on-farm-energy-use", "On-farm energy use"),
    "6795": ("6996", "savanna-fires", "Savanna fires"),
    "6750": ("6516", "net-forest-conversion", "Net Forest conversion"),
    "69921": ("6516", "fires-in-humid-tropical-forests", "Fires in humid tropical forests"),
    "6993": ("6516", "fires-in-organic-soils", "Fires in organic soils"),
    "6504": ("6517", "fertilizers-manufacturing", "Fertilizers Manufacturing"),
    "6997": ("6517", "pesticides-manufacturing", "Pesticides Manufacturing"),
    "6507": ("6517", "food-processing", "Food Processing"),
    "6506": ("6517", "food-packaging", "Food Packaging"),
    "6815": ("6517", "food-transport", "Food Transport"),
    "6508": ("6517", "food-retail", "Food Retail"),
    "6505": ("6517", "food-household-consumption", "Food Household Consumption"),
    "6991": ("6517", "agrifood-systems-waste-disposal", "Agrifood Systems Waste Disposal"),
}
# Our id -> the label shown. FAO's item names are terms of art; these say the same thing in plain words.
STAGE_LABELS = {
    "farm-gate": "On the farm",
    "land-use-change": "Clearing land for farming",
    "pre-post-production": "Before and after the farm",
}
PROCESS_LABELS = {
    "enteric-fermentation": "Farm animals' digestion (burps)",
    "manure-management": "Storing and handling manure",
    "manure-left-on-pasture": "Manure left on grazing land",
    "manure-applied-to-soils": "Manure spread on fields",
    "synthetic-fertilizers": "Synthetic fertiliser on fields",
    "rice-cultivation": "Flooded rice fields",
    "crop-residues": "Crop leftovers rotting on fields",
    "burning-crop-residues": "Burning crop leftovers",
    "drained-organic-soils": "Drained peat soils",
    "on-farm-energy-use": "Fuel and electricity used on farms",
    "savanna-fires": "Grassland (savanna) fires",
    "net-forest-conversion": "Cutting down forests",
    "fires-in-humid-tropical-forests": "Tropical forest fires",
    "fires-in-organic-soils": "Peat fires",
    "fertilizers-manufacturing": "Making fertiliser",
    "pesticides-manufacturing": "Making pesticides",
    "food-processing": "Processing food",
    "food-packaging": "Packaging",
    "food-transport": "Transport",
    "food-retail": "Shops",
    "food-household-consumption": "Cooking and storing food at home",
    "agrifood-systems-waste-disposal": "Disposing of food waste",
}
STAGE_LABELLED = plain_labels({i: n for i, n in STAGES.values()}, STAGE_LABELS)
PROCESS_LABELLED = plain_labels({pid: n for _, pid, n in PROCESSES.values()}, PROCESS_LABELS)
ITEMS = (
    {AGRIFOOD[0]: AGRIFOOD[1]} | {c: n for c, (_, n) in STAGES.items()} | {c: n for c, (_, _, n) in PROCESSES.items()}
)
MARKER = f'"{CO2EQ_AR5}"'.encode()


def read(lines) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Element Code"] == CO2EQ_AR5 and r["Item Code"] in ITEMS and r["Source"] == TIER1

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, MARKER)


def gathered(table: Table) -> tuple[Gathered, list[str]]:
    """The rows used, checked: names, units, projections, and every part against FAO's total. Plus the steps."""
    g = gather(table.rows, items=ITEMS, elements=ELEMENTS, source=TIER1, what=DATA_MEMBER)
    early = {
        (area, year)
        for (area, _, item), series in g.values.items()
        for year in series
        if year < FIRST_YEAR and item in PROCESSES
    }
    for (area, _, item), series in g.values.items():
        if item not in PROCESSES and min(series) < FIRST_YEAR:
            raise FaostatBulkError(f"area {area}: item {ITEMS[item]} starts in {min(series)}, before {FIRST_YEAR}")
    years = range(FIRST_YEAR, 10_000)
    checked = check_parts(g, CO2EQ_AR5, AGRIFOOD[0], STAGES, TOLERANCE_KT, years)
    for stage in STAGES:
        check_parts(g, CO2EQ_AR5, stage, [p for p, (s, _, _) in PROCESSES.items() if s == stage], TOLERANCE_KT, years)
    forecast = g.forecast_years()
    steps = [
        f'Kept the "{TIER1}" rows of element "{ELEMENTS[CO2EQ_AR5][0]}" (code {CO2EQ_AR5}), in kilotonnes of '
        "CO₂-equivalent (IPCC AR5 100-year global warming potentials), for item "
        f'"{AGRIFOOD[1]}" ({AGRIFOOD[0]}), its three stage items and their 22 process items. Rows from FAO\'s '
        '"UNFCCC" source are not used.',
        f"Checked, in all {checked:,} areas and years from {FIRST_YEAR} where FAO prints them (FAO's regions "
        f'included), that "{AGRIFOOD[1]}" equals the sum of the three stages and each stage equals the sum of its '
        f"processes present, to within {TOLERANCE_KT} kilotonnes. Nothing is computed from this check; it shows "
        "that the parts published are FAO's whole total, with no remainder.",
        f"Left out {len(early):,} area-years before {FIRST_YEAR} that carry farm process rows only: FAO publishes "
        f"no stage total or agrifood total before {FIRST_YEAR}, so those rows could not be checked against one.",
    ]
    if forecast:
        shown = " and ".join(str(y) for y in forecast)
        steps.append(f'Left out FAO\'s projections for {shown}, which the file flags F ("Forecast value").')
    return g, steps


THOUSAND = Decimal(1000)


def observations(table: Table, flags: dict[str, str], level: str) -> tuple[list[Observation], list[str]]:
    """level "stage" or "process", both in million tonnes."""
    g, steps = gathered(table)
    wanted = list(STAGES) if level == "stage" else list(PROCESSES)
    left_out: set[str] = set()
    rows: list[tuple[str, int, int, dict[str, str], Decimal, str, str]] = []
    for (area, _, item), series in g.values.items():
        if item not in wanted:
            continue
        entity = entity_of(area, g, left_out)
        if entity is None:
            continue
        if level == "stage":
            dims = {"stage": STAGES[item][0]}
        else:
            stage, pid, _ = PROCESSES[item]
            dims = {"stage": STAGES[stage][0], "process": pid}
        for year, cell in series.items():
            if year >= FIRST_YEAR:
                rows.append((entity, wanted.index(item), year, dims, cell.value / THOUSAND, cell.flag, cell.note))
    if not any(r[0] == "WLD" for r in rows):
        raise FaostatBulkError("no World rows")
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    counts = Counter(r[5] for r in rows)
    words = flag_words(flags, counts, FLAGS_MEMBER)
    obs = []
    for entity, _, year, dims, value, flag, note in rows:
        notes = [f"FAO note: {note}"] if note else []
        if len(words) > 1:
            notes.append(f"FAO flag {flag}: {words[flag]}.")
        obs.append(
            Observation(
                entity=entity, period=f"{year:04d}", value=float(value), dims=dims, note=" ".join(notes) or None
            )
        )
    all_years = sorted({r[2] for r in rows})
    steps += [
        f"Published the {'three stage' if level == 'stage' else '22 process'} items, {all_years[0]}–{all_years[-1]}, "
        "each value exactly as one row of the file.",
        areas_step(left_out),
        "Converted kilotonnes to million tonnes by dividing by 1,000 (exact decimal arithmetic on the printed values).",
        flag_step(words, counts),
        labels_step(STAGE_LABELLED if level == "stage" else STAGE_LABELLED + PROCESS_LABELLED),
    ]
    return obs, steps


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    # Snapshot paths are content-addressed, so caching by path is caching by content: both indicators read the
    # 364 MB member once.
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _runner(level: str):
    def run(files: dict[str, InputFile]) -> Result:
        table, flags = _read_zip(files[TOTALS.key].path)
        updated, vintage_step = vintage_of(files, TOTALS, DATASET_CODE, table.data_rows, DATA_MEMBER)
        obs, steps = observations(table, flags, level)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[vintage_step, *steps],
            changes="converted from kilotonnes to million tonnes of CO₂-equivalent.",
        )

    return run


STAGE_DIM = Dimension(
    id="stage", label="Stage", values=[DimensionValue(id=i, label=label) for i, _, label in STAGE_LABELLED]
)
PROCESS_DIM = Dimension(
    id="process", label="Process", values=[DimensionValue(id=i, label=label) for i, _, label in PROCESS_LABELLED]
)

_COMMON_BASIS = (
    "FAO TIER 1 estimates for every country with the same method, not country inventory submissions, so they can "
    "differ from a country's own inventory. Farm gate is FAO's grouping: it includes on-farm energy use, drained "
    "organic soils and savanna fires as well as livestock and crop emissions. Land-use change counts only what FAO "
    "attributes to agriculture: net forest conversion (deforestation) plus fires in humid tropical forests and in "
    'organic soils (peat). The carbon taken up by standing forests (FAOSTAT item "Forestland", a net removal) is '
    "outside FAO's agrifood total: it is not subtracted and not shown. Net forest conversion uses FAO Forest "
    "Resources Assessment period averages, so it is constant within each assessment period and steps between "
    "periods, including a method break between 2000 and 2001; year-to-year changes in land-use change are partly "
    "an artefact of that method. Pre- and post-production covers fertilizer and pesticide manufacturing, food "
    "processing, packaging, transport, retail, household consumption (cooking, storing) and agrifood waste "
    "disposal. International aviation and shipping bunkers are a separate FAOSTAT item and are not included. "
    "Stage totals start in 1990."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-by-stage",
                title="Greenhouse gas emissions from agrifood systems, by stage: within the farm gate (including "
                "savanna fires and drained peat soils), land-use change, and before and after the farm",
                description="Greenhouse gas emissions from food and farming each year since 1990, for the world "
                "and each country, in carbon dioxide equivalent, split into FAO's three stages: within the farm "
                "gate (animals, manure, fertilisers, rice fields, crop residues, drained peat soils, savanna fires "
                "and energy used on farms), land-use change (clearing forests for farming, fires in humid tropical "
                "forests and fires in peat soils), and pre- and post-production (making fertilisers and pesticides, "
                "processing, packaging, transport, retail, household food consumption and waste disposal). The "
                "three stages add up exactly to FAO's agrifood systems total. The forest carbon sink is not part of "
                "that total and is not shown.",
                kind="series",
                unit=Unit(code="MtCO2e", label="million tonnes of carbon dioxide equivalent", short="Mt CO₂e"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Countries and territories, and the world",
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis='FAOSTAT items "Farm gate" (6996), "Land-use change" (6516) and "Pre- and '
                    'post-production" (6517), which add up to item "Agrifood systems" (6518). ' + _COMMON_BASIS,
                ),
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(STAGE_DIM,),
                headline_dims=(("stage", "farm-gate"),),
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_runner("stage"),
            module_file=here,
            validation=Validation(min_rows=20_000, value_range=(-1_000.0, 30_000.0)),
        ),
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-by-process",
                title="Greenhouse gas emissions from agrifood systems, by process",
                description="Greenhouse gas emissions from food and farming each year since 1990, for the world "
                "and each country, in carbon dioxide equivalent, split into the 22 processes FAO estimates, within "
                "its three stages. Farm gate (11): enteric fermentation, manure management, manure left on pasture, "
                "manure applied to soils, synthetic fertilizers, rice cultivation, crop residues, burning crop "
                "residues, drained organic soils, on-farm energy use and savanna fires. Land-use change (3): net "
                "forest conversion, fires in humid tropical forests and fires in organic soils. Pre- and "
                "post-production (8): fertilizers manufacturing, pesticides manufacturing, food processing, food "
                "packaging, food transport, food retail, food household consumption and agrifood systems waste "
                "disposal. Within each stage the processes add up exactly to FAO's stage total. Where FAO gives no "
                "value for a process in a country and year, it is absent, not zero.",
                kind="series",
                unit=Unit(code="MtCO2e", label="million tonnes of carbon dioxide equivalent", short="Mt CO₂e"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Countries and territories, and the world",
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis='The 22 FAOSTAT process items of item "Agrifood systems" (6518), with FAO\'s names, each '
                    "under its stage; overlapping FAOSTAT items (Emissions from livestock, Emissions from crops, "
                    "Emissions on agricultural land, IPCC Agriculture, AFOLU, LULUCF) are not included, so nothing "
                    "is counted twice. A few synthetic-fertilizer values are negative as published (Somalia and "
                    "Timor-Leste, some years). " + _COMMON_BASIS,
                ),
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(STAGE_DIM, PROCESS_DIM),
                headline_dims=(("stage", "farm-gate"), ("process", "enteric-fermentation")),
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_runner("process"),
            module_file=here,
            validation=Validation(min_rows=100_000, value_range=(-10.0, 10_000.0)),
        ),
    ]

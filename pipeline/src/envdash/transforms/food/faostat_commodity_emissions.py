"""FAOSTAT Emissions intensities (EI): farm-gate emissions of 14 farm products, and those emissions per kilogram of
product, for the world and each country, 1961-2023.

Input. Environment_Emissions_intensities_E_All_Data_(Normalized).csv in the EI bulk zip (header unquoted, data fields
quoted; columns Area Code, Area Code (M49), Area, Item Code, Item Code (CPC), Item, Element Code, Element, Year Code,
Year, Unit, Value, Flag; there is no Source column) and its flag codebook Environment_Emissions_intensities_E_Flags.csv.
Items are matched by Item Code: the data file writes the names with commas ("Meat of cattle with the bone, fresh or
chilled") where the ItemCodes file writes semicolons, so the data file's names are the ones checked. Elements used:

- 723113 "Emissions (CO2eq) (AR5)", unit "kt": converted to million tonnes (kt / 1,000, exact decimal arithmetic);
- 71761 "Emissions intensity", unit "kg CO2eq/kg": published as printed.

What FAO counts (methodological note EI_e.pdf, release October 2025, linked from the source entry): only emissions
"generated within the farm gate". For meat, milk and eggs: CH4 from enteric fermentation, CH4 and N2O from manure
management, and N2O from manure applied to soils and left on pasture, from the animals FAO assigns to each product
(non-dairy cattle to cattle meat, dairy cattle to cattle milk, all swine to pig meat, broilers to chicken meat,
layers to eggs; sheep, goats, buffalo and camels split between meat and milk by the share of milk animals). For rice
and cereals: N2O from crop residues and synthetic fertiliser (fertiliser shared out by FAO's 1995-2000 crop shares),
N2O and CH4 from burning crop residues, plus CH4 from rice paddies for rice. (The note lists burning under nitrous
oxide, but the values include its methane: in all 1,121 area-years of the February 2026 release whose synthetic
fertiliser N2O is 0 and whose residue burning emits methane, EI's rice and cereal emissions equal FAOSTAT Emissions
from crops' residue N2O, burning N2O and CH4, and paddy CH4 at AR5 weights; checked on 2026-10-05 against the GCE bulk
file of 28 October 2025.) Not counted: on-farm energy use, drained organic soils, savanna fires, land-use change and
every stage before and after the farm. FAO says these values "should not be compared" with life-cycle assessments. The
14 products are not a partition of any FAO total: other animals (horses, asses, mules, llamas, ducks, turkeys; camel
meat) and all other crops have no row.

The denominator of the intensities is FAOSTAT production (Production/Crops and Livestock): meat in carcass weight (the
items are meat "with the bone"), raw whole milk not corrected for fat and protein, hen eggs in shell, and harvested
cereals. So the intensities cannot be compared with figures per kilogram of boneless retail meat.

Values as printed. The split of sheep, goat, buffalo and camel emissions by the share of milk animals gives negative
meat values (in the February 2026 release 75 emission values and 72 intensities, all goat, buffalo or sheep meat,
mostly Mali and Bhutan, down to -6.3 million tonnes for goat meat in Mali in 2011 and -854 kg per kg in 2010); they are
published as printed, as are very large intensities where production is small. Emission rows without an intensity row
(no production figure) have absent intensities, never filled; the processing steps count both, for the published
areas only.

Areas are mapped by faostat_bulk.AREAS through faostat_parts (world and countries; the European Union and FAO's groups,
including "China", are left out). Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
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
from envdash.transforms.food.faostat_parts import areas_step, entity_of, gather

INTENSITIES = Input(SOURCE, "emissions-intensities")
DATASET_CODE = "EI"
DATA_MEMBER = "Environment_Emissions_intensities_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "Environment_Emissions_intensities_E_Flags.csv"
COLUMNS = [
    "Area Code",
    "Area Code (M49)",
    "Area",
    "Item Code",
    "Item Code (CPC)",
    "Item",
    "Element Code",
    "Element",
    "Year Code",
    "Year",
    "Unit",
    "Value",
    "Flag",
]
EMISSIONS = "723113"
INTENSITY = "71761"
ELEMENTS = {
    EMISSIONS: ("Emissions (CO2eq) (AR5)", "kt"),
    INTENSITY: ("Emissions intensity", "kg CO2eq/kg"),
}
# FAO Item Code -> (our commodity id, FAO's name as written in the data file), in FAO's order of 2023 world emissions.
COMMODITIES: dict[str, tuple[str, str]] = {
    "867": ("cattle-meat", "Meat of cattle with the bone, fresh or chilled"),
    "27": ("rice", "Rice"),
    "882": ("cattle-milk", "Raw milk of cattle"),
    "1718": ("cereals-excluding-rice", "Cereals excluding rice"),
    "947": ("buffalo-meat", "Meat of buffalo, fresh or chilled"),
    "977": ("sheep-meat", "Meat of sheep, fresh or chilled"),
    "1017": ("goat-meat", "Meat of goat, fresh or chilled"),
    "1035": ("pig-meat", "Meat of pig with the bone, fresh or chilled"),
    "951": ("buffalo-milk", "Raw milk of buffalo"),
    "1058": ("chicken-meat", "Meat of chickens, fresh or chilled"),
    "982": ("sheep-milk", "Raw milk of sheep"),
    "1020": ("goat-milk", "Raw milk of goats"),
    "1062": ("hen-eggs", "Hen eggs in shell, fresh"),
    "1130": ("camel-milk", "Raw milk of camel"),
}
ITEMS = {code: name for code, (_, name) in COMMODITIES.items()}


def read(lines) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Element Code"] in ELEMENTS and r["Item Code"] in ITEMS

    # Every data line holds a quote, so every line is parsed (the file is 58 MB); keep() decides.
    return read_member(lines, DATA_MEMBER, COLUMNS, keep, marker=b'"')


def observations(table: Table, flags: dict[str, str], element: str) -> tuple[list[Observation], list[str]]:
    g = gather(table.rows, items=ITEMS, elements=ELEMENTS, source=None, what=DATA_MEMBER)
    if g.forecast:
        raise FaostatBulkError(f"{DATA_MEMBER}: unexpected rows flagged F (forecast): {sorted(g.forecast)[:5]}")
    order = list(COMMODITIES)
    left_out: set[str] = set()
    rows = []
    published: set[str] = set()
    """FAO area codes of the rows published (of either element), for counting gaps in published areas only."""
    for (area, el, item), series in g.values.items():
        entity = entity_of(area, g, left_out)
        if entity is None:
            continue
        published.add(area)
        if el != element:
            continue
        for year, cell in series.items():
            value = cell.value / Decimal(1000) if element == EMISSIONS else cell.value
            rows.append((entity, order.index(item), year, {"commodity": COMMODITIES[item][0]}, value, cell.flag))
    if not any(r[0] == "WLD" for r in rows):
        raise FaostatBulkError("no World rows")
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    counts = Counter(r[5] for r in rows)
    words = flag_words(flags, counts, FLAGS_MEMBER)
    obs = [
        Observation(
            entity=entity,
            period=f"{year:04d}",
            value=float(value),
            dims=dims,
            note=f"FAO flag {flag}: {words[flag]}." if len(words) > 1 else None,
        )
        for entity, _, year, dims, value, flag in rows
    ]
    years = sorted({r[2] for r in rows})
    name, unit = ELEMENTS[element]
    steps = [
        f'Kept the rows of element "{name}" (code {element}, unit "{unit}") for the 14 items of the file, matched by '
        f"Item Code, {years[0]}–{years[-1]}.",
        areas_step(left_out),
        _negatives_step(rows, unit),
    ]
    if element == EMISSIONS:
        steps.append(
            "Converted kilotonnes to million tonnes by dividing by 1,000 (exact decimal arithmetic on the printed "
            "values)."
        )
    else:
        absent = sum(
            1
            for (area, el, item), series in g.values.items()
            if el == EMISSIONS and area in published
            for year in series
            if year not in g.values.get((area, INTENSITY, item), {})
        )
        steps.append(
            "Published the intensities as printed, in kilograms of CO₂-equivalent per kilogram produced (FAOSTAT "
            "production: carcass weight for meat, raw whole milk, eggs in shell, harvested cereals). "
            f"{absent:,} product-years of the published areas have an emissions row but no intensity row in the file "
            "(no production figure); they are absent here, not filled."
        )
    steps.append(flag_step(words, counts))
    return obs, steps


def _negatives_step(rows: list, unit: str) -> str:
    """Words counting the published values below zero (FAO's split of mixed meat-and-milk herds)."""
    neg = [r for r in rows if r[4] < 0]
    if not neg:
        return "No published value is below zero."
    ids = list(COMMODITIES.values())
    products = sorted({ids[r[1]][0] for r in neg})
    entities = sorted({r[0] for r in neg})
    low = min(neg, key=lambda r: r[4])
    shown = "million tonnes" if unit == "kt" else unit
    return (
        f"{len(neg):,} published values are below zero ({', '.join(products)}; {', '.join(entities)}), from FAO's "
        "split of sheep, goat, buffalo and camel emissions between meat and milk by the share of animals milked; the "
        f"lowest is {low[0]} {ids[low[1]][0]} {low[2]} ({low[4].normalize():f} {shown}). Published as printed."
    )


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _runner(element: str):
    def run(files: dict[str, InputFile]) -> Result:
        table, flags = _read_zip(files[INTENSITIES.key].path)
        updated, vintage_step = vintage_of(files, INTENSITIES, DATASET_CODE, table.data_rows, DATA_MEMBER)
        obs, steps = observations(table, flags, element)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[
                vintage_step
                + " FAO's methodological note for this domain (release October 2025) says its emissions come from "
                "FAOSTAT's Emissions from crops and Emissions from livestock domains and its production from "
                "FAOSTAT Production (QCL).",
                *steps,
            ],
            changes="converted from kilotonnes to million tonnes of CO₂-equivalent." if element == EMISSIONS else None,
        )

    return run


COMMODITY_DIM = Dimension(
    id="commodity",
    label="Farm product",
    values=[DimensionValue(id=i, label=name) for i, name in COMMODITIES.values()],
)

COUNTED = (
    "Counts only emissions on the farm from: methane from animals' digestion (enteric fermentation) and from manure "
    "management; nitrous oxide from manure management, from manure applied to soils and from manure left on pasture; "
    "and, for rice and other cereals, nitrous oxide from crop residues and from synthetic fertiliser, methane and "
    "nitrous oxide from burning crop residues, plus methane from flooded rice paddies. Not counted: energy used on "
    "farms, drained organic (peat) soils, savanna fires, clearing land (land-use change), and everything before and "
    "after the farm (making fertiliser and feed, processing, packaging, transport, retail, cooking and waste)."
)
COVERAGE = (
    "Only 14 products: meat of cattle, buffalo, sheep, goats, pigs and chickens; raw milk of cattle, buffalo, sheep, "
    "goats and camels; hen eggs; rice; and other cereals together. Soy, palm oil, fruit, vegetables, sugar, pulses, "
    "fish and other farm animals are not covered, so the products do not add up to food's emissions."
)
NOT_LCA = (
    "These are farm-gate values, not life-cycle footprints: FAO says they should not be compared with life-cycle "
    "assessment figures."
)
BASIS = (
    "FAOSTAT Emissions intensities (EI). FAO assigns each kind of animal to a product: non-dairy cattle to cattle "
    "meat, dairy cattle to cattle milk, all pigs to pig meat, broilers to chicken meat and laying hens to eggs; sheep, "
    "goat, buffalo and camel emissions are split between meat and milk by the share of animals milked, which gives "
    "some negative meat values, published as printed (the processing steps count them). Synthetic fertiliser is "
    "shared among crops by FAO's 1995-2000 fertiliser use by crop. Milk is raw milk, not corrected for fat and "
    "protein, and products are compared by weight, not by protein or energy. FAO TIER 1 estimates (IPCC 2006 "
    "Guidelines), not country inventory submissions. The products do not add up to any FAO total and overlap FAO's "
    "farm-gate process items (for example rice includes rice's share of fertiliser), so they are never stacked with "
    "them."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    scope = Scope(
        geography="Countries and territories, and the world", gwp="AR5-GWP100", lulucf="excluded", basis=BASIS
    )
    return [
        Transform(
            spec=Spec(
                id="food.faostat.commodity-emissions",
                title="On-farm methane and nitrous oxide from animals, manure, fertiliser and rice fields, by farm "
                "product (14 products)",
                description="Methane and nitrous oxide emitted on farms each year since 1961 in producing each of 14 "
                "farm products, for the world and each country, in carbon dioxide equivalent, as allocated by FAO. "
                + COUNTED
                + " "
                + COVERAGE
                + " "
                + NOT_LCA
                + " FAO's split of sheep, goat, buffalo and camel emissions between meat and milk makes 75 meat "
                "values negative in the February 2026 release, all goat, buffalo or sheep meat and most of them in "
                "Mali and Bhutan, down to about -6.3 million tonnes for goat meat in Mali in 2011. They are published "
                "as printed.",
                kind="series",
                unit=Unit(code="MtCO2e", label="million tonnes of carbon dioxide equivalent", short="Mt CO₂e"),
                display=Display(decimals=1),
                scope=scope,
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(COMMODITY_DIM,),
                headline_dims=(("commodity", "cattle-meat"),),
            ),
            inputs=(INTENSITIES, CATALOGUE),
            run=_runner(EMISSIONS),
            module_file=here,
            validation=Validation(min_rows=100_000, value_range=(-100.0, 5_000.0)),
        ),
        Transform(
            spec=Spec(
                id="food.faostat.commodity-intensity",
                title="On-farm methane and nitrous oxide per kilogram of farm product, from animals, manure, "
                "fertiliser and rice fields (14 products)",
                description="Methane and nitrous oxide emitted on farms per kilogram of each of 14 farm products, "
                "each year since 1961, for the world and each country, in kilograms of carbon dioxide equivalent, "
                "as published by FAO (the product's farm emissions divided by its production). The kilogram is "
                "FAO's production weight: carcass weight for meat (FAO's items are meat 'with the bone'), raw whole "
                "milk, eggs in shell and harvested cereals. It is not a kilogram of boneless meat or of food as "
                "bought, so these values are not comparable with retail or life-cycle figures per kilogram of food. "
                + COUNTED
                + " "
                + COVERAGE
                + " "
                + NOT_LCA
                + " Where a country produces little of a product the value can be very large, and where FAO gives "
                "no production figure there is no value. FAO's split of sheep, goat, buffalo and camel emissions "
                "between meat and milk makes 72 meat values negative in the February 2026 release, most of them in "
                "Mali and Bhutan, down to about -854 kilograms per kilogram for goat meat in Mali in 2010. They are "
                "published as printed.",
                kind="series",
                unit=Unit(
                    code="kgCO2e/kg",
                    label="kilograms of carbon dioxide equivalent per kilogram produced (carcass weight for meat, "
                    "raw whole milk, eggs in shell)",
                    short="kg CO₂e/kg",
                ),
                display=Display(decimals=2),
                scope=scope,
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(COMMODITY_DIM,),
                headline_dims=(("commodity", "cattle-meat"),),
            ),
            inputs=(INTENSITIES, CATALOGUE),
            run=_runner(INTENSITY),
            module_file=here,
            validation=Validation(min_rows=100_000, value_range=(-1_000.0, 100_000.0)),
        ),
    ]

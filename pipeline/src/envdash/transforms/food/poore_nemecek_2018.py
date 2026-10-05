"""Poore & Nemecek (2018): greenhouse gas emissions per kilogram and per 100 grams of protein of about 40 food
products, global means, as published by Our World in Data (OWID) in its grapher CSVs.

Licence: display-only (no data licence; the paper is © the authors, exclusive licensee AAAS). These indicators are
exported to data-private/ only: shown with their citation, never downloaded, mirrored or archived.

Inputs: poore-nemecek-2018/ghg-per-kg (ghg-per-kg-poore.csv) and poore-nemecek-2018/ghg-per-protein
(ghg-per-protein-poore.csv). Each is a CSV with the header "entity,year,<column>", one row per food product, the
year 2010 (OWID's reference year for the study, whose median reference year is 2010), values in kg CO₂e per kg of
product and per 100 g of protein. The header must be exactly the one below and every year must be 2010, or the
transform stops. Values are published as printed, with no conversion.

What OWID says about the values: emissions are in carbon dioxide equivalents, "non-CO₂ gases are weighted by the
amount of warming they cause over a 100-year timescale" (grapher page, read 2026-10-05). Which IPCC report's factors
were used is not stated in these files or on that page, and science.org (the paper and its supplement) refuses
scripts, so the scope names GWP100 without an assessment report. Some per-100 g protein values are OWID's own
conversions with FAO/INFOODS composition factors (registry note); the processing step says so.

Food products are the files' entities, declared in FOODS; each becomes a dimension value whose id is the name in lower
case with every run of characters other than a-z and 0-9 replaced by a hyphen (e.g. "Beef (beef herd)" ->
"beef-beef-herd"). Two names giving one id stop the transform. They are global means across the producers in the
study: impacts vary widely between producers of the same food, and beef from beef herds and from dairy herds are
separate products.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "poore-nemecek-2018"
PER_KG = Input(SOURCE, "ghg-per-kg")
PER_PROTEIN = Input(SOURCE, "ghg-per-protein")
COLUMNS = {
    PER_KG.key: "ghg_emissions_per_kilogram__poore__and__nemecek__2018",
    PER_PROTEIN.key: "ghg_emissions_per_100g_protein__poore__and__nemecek__2018",
}
YEAR = "2010"
# Every food name in the two files (snapshots of 2026-10-04), as OWID prints it. A name not listed stops the transform.
FOODS: tuple[str, ...] = (
    "Apples", "Bananas", "Barley", "Beef (beef herd)", "Beef (dairy herd)", "Beet Sugar", "Berries & Grapes",
    "Brassicas", "Cane Sugar", "Cassava", "Cheese", "Citrus Fruit", "Coffee", "Dark Chocolate", "Eggs",
    "Fish (farmed)", "Grains", "Groundnuts", "Lamb & Mutton", "Maize", "Milk", "Nuts", "Oatmeal", "Onions & Leeks",
    "Other Fruit", "Other Pulses", "Other Vegetables", "Peas", "Pig Meat", "Potatoes", "Poultry Meat",
    "Prawns (farmed)", "Rice", "Root Vegetables", "Soy milk", "Tofu", "Tomatoes", "Wheat & Rye", "Wine",
)  # fmt: skip
VINTAGE = "Science 360, 987–992 (2018); OWID grapher series updated 2019-10-08"
PUBLISHED = "2018-06-01"


class PooreFormatError(ValueError):
    pass


def food_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def read(raw: bytes, column: str) -> list[tuple[str, str]]:
    """(food name, value as printed), in file order."""
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    if rows[0] != ["entity", "year", column]:
        raise PooreFormatError(f"header {rows[0]} is not entity, year, {column}")
    out: list[tuple[str, str]] = []
    ids: dict[str, str] = {}
    for r in rows[1:]:
        if len(r) != 3:
            raise PooreFormatError(f"row {r} does not have 3 fields")
        name, year, value = r
        if year != YEAR:
            raise PooreFormatError(f"{name}: year {year}, expected {YEAR}")
        if value == "":
            raise PooreFormatError(f"{name}: empty value")
        if name not in FOODS:
            raise PooreFormatError(f"{name!r} is not in FOODS; declare it before publishing")
        fid = food_id(name)
        if fid in ids:
            raise PooreFormatError(f"{name!r} and {ids[fid]!r} both give the id {fid!r}")
        ids[fid] = name
        out.append((name, value))
    return out


def _runner(inp: Input, what: str, extra: list[str]):
    def run(files: dict[str, InputFile]) -> Result:
        rows = read(files[inp.key].path.read_bytes(), COLUMNS[inp.key])
        obs = [Observation(entity="WLD", period=YEAR, value=float(v), dims={"food": food_id(name)}) for name, v in rows]
        return Result(
            observations=obs,
            vintage=VINTAGE,
            date_published=PUBLISHED,
            steps=[
                f"Read OWID's grapher CSV of Poore and Nemecek (2018) {what} (column {COLUMNS[inp.key]}): "
                f"{len(rows)} food products, all for the year {YEAR}. Values are published as printed, with no "
                "conversion; the food names are OWID's.",
                *extra,
            ],
        )

    return run


_DIMENSION = Dimension(id="food", label="Food product", values=[DimensionValue(id=food_id(n), label=n) for n in FOODS])


_BASIS = (
    "Global mean of the life-cycle studies in Poore and Nemecek's meta-analysis (about 570 studies, 38,700 farms, "
    "119 countries, median reference year 2010), from land-use change and farm to retail, including packaging and "
    "losses. Greenhouse gases weighted by their warming over 100 years (GWP100); the IPCC report the factors come "
    "from is not stated in the files used. Impacts vary widely between producers of the same food."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="food.poore-nemecek-2018.ghg-per-kg",
                title="Greenhouse gas emissions per kilogram of food",
                description="Greenhouse gas emissions from producing a kilogram of each of about 40 foods, from "
                "land-use change and the farm to the shop, in kilograms of carbon dioxide equivalent: global means "
                "from Poore and Nemecek (2018), as published by Our World in Data.",
                kind="series",
                unit=Unit(
                    code="kgCO2e-per-kg",
                    label="kilograms of carbon dioxide equivalent per kilogram of food",
                    short="kg CO₂e/kg",
                ),
                display=Display(decimals=1),
                scope=Scope(geography="World (global mean of the studies reviewed)", basis=_BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("food", "beef-beef-herd"),),
            ),
            inputs=(PER_KG,),
            run=_runner(PER_KG, "greenhouse gas emissions per kilogram of food product", []),
            module_file=here,
            validation=Validation(min_rows=30, value_range=(0.0, 200.0)),
        ),
        Transform(
            spec=Spec(
                id="food.poore-nemecek-2018.ghg-per-100g-protein",
                title="Greenhouse gas emissions per 100 grams of protein",
                description="Greenhouse gas emissions from producing the amount of each of about 30 foods that "
                "holds 100 grams of protein, from land-use change and the farm to the shop, in kilograms of carbon "
                "dioxide equivalent: global means from Poore and Nemecek (2018), as published by Our World in Data.",
                kind="series",
                unit=Unit(
                    code="kgCO2e-per-100g-protein",
                    label="kilograms of carbon dioxide equivalent per 100 grams of protein",
                    short="kg CO₂e/100 g protein",
                ),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World (global mean of the studies reviewed)",
                    basis=_BASIS + " Some per-protein values are Our World in Data's conversions of the per-kilogram "
                    "values with FAO/INFOODS food composition factors.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("food", "beef-beef-herd"),),
            ),
            inputs=(PER_PROTEIN,),
            run=_runner(
                PER_PROTEIN,
                "greenhouse gas emissions per 100 grams of protein",
                [
                    "Some of these per-protein values are Our World in Data's own conversions of the per-kilogram "
                    "values with FAO/INFOODS food composition factors (registry note), labelled as processed by Our "
                    "World in Data."
                ],
            ),
            module_file=here,
            validation=Validation(min_rows=25, value_range=(0.0, 200.0)),
        ),
    ]

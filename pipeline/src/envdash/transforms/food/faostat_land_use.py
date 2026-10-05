"""FAOSTAT Land Use (RL): agricultural land, cropland, permanent meadows and pastures, and forest land, by country, for
the European Union and for the world: area (thousand hectares) and share of land area (percent).

Input. The RL bulk zip holds Inputs_LandUse_E_All_Data_(Normalized).csv (UTF-8, CRLF, every field quoted; columns
Area Code, Area Code (M49), Area, Item Code, Item, Element Code, Element, Year Code, Year, Unit, Value, Flag, Note) and
its flag codebook Inputs_LandUse_E_Flags.csv. Items and elements are matched by code, and the names next to the codes
must be the ones below, or the transform stops:

- items 6610 Agricultural land, 6620 Cropland, 6655 Permanent meadows and pastures, 6646 Forest land;
- element 5110 Area, unit "1000 ha", published as printed (thousand hectares, no conversion);
- element 7209 Share in Land area, unit "%", FAO's own share of each country's land area, published as printed.

FAO's definitions (FAOSTAT RL metadata): agricultural land is cropland plus permanent meadows and pastures; cropland
is arable land plus land under permanent crops; forest land follows the FRA definition (at least 0.5 ha with trees
over 5 m and canopy cover over 10 percent, not mainly under agricultural or urban use). FAO takes forest land from the
Global Forest Resources Assessment (here FRA 2025), so it covers 1990 onward (to 2025 for area, 2024 for the share);
the FRA series itself is published separately from fao-fra-2025.

Areas are mapped by faostat_bulk.AREAS (countries, territories, EU27, WLD); FAO's former states, territories without
an entity and FAO's regional groups are left out and named in a processing step.

Flags. Every flag must be in the codebook. When the rows of an indicator carry several flags (A official, E estimated,
I imputed, X from an external organisation), each observation names its flag and FAO's words for it in a note. An empty
value is published as null with FAO's flag as the reason (flag L "Missing value; data exist but were not collected",
for example Nicaragua 2023-2024); an empty value without a flag stops the transform. A non-empty Note is copied to the
observation.

Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
"""

from __future__ import annotations

import functools
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
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

LAND_USE = Input(SOURCE, "land-use")
DATASET_CODE = "RL"
DATA_MEMBER = "Inputs_LandUse_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "Inputs_LandUse_E_Flags.csv"
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
    "Unit",
    "Value",
    "Flag",
    "Note",
]

# FAO item code -> (our dimension value id, FAO's item name, our label)
ITEMS: dict[str, tuple[str, str, str]] = {
    "6610": (
        "agricultural-land",
        "Agricultural land",
        "Agricultural land (cropland and permanent meadows and pastures)",
    ),
    "6620": ("cropland", "Cropland", "Cropland (arable land and permanent crops)"),
    "6655": ("permanent-meadows-and-pastures", "Permanent meadows and pastures", "Permanent meadows and pastures"),
    "6646": ("forest-land", "Forest land", "Forest land"),
}


@dataclass(frozen=True)
class Element:
    code: str
    name: str
    unit: str


AREA = Element("5110", "Area", "1000 ha")
SHARE = Element("7209", "Share in Land area", "%")


def read(lines, element: Element) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Element Code"] == element.code and r["Item Code"] in ITEMS

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, f'"{element.code}"'.encode())


def observations(table: Table, element: Element, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    """The published observations of one element, and the processing steps that describe them."""
    kept: list[tuple[str, str, int, dict[str, str]]] = []
    left_out: set[str] = set()
    for r in table.rows:
        item_id, item_name, _ = ITEMS[r["Item Code"]]
        what = f"{r['Area Code']} {item_name} {r['Year']}"
        if (r["Item"], r["Element"]) != (item_name, element.name):
            raise FaostatBulkError(
                f"item {r['Item Code']} / element {element.code} are named {r['Item']!r} / {r['Element']!r}, "
                f"expected {item_name!r} / {element.name!r}"
            )
        if r["Unit"] != element.unit:
            raise FaostatBulkError(f"{what}: unit {r['Unit']!r}, expected {element.unit!r}")
        entity = area_entity(r["Area Code"], r["Area Code (M49)"])
        if entity is None:
            left_out.add(r["Area Code"])
            continue
        kept.append((entity, item_id, year_of(r, what), r))
    if not kept:
        raise FaostatBulkError(f"no rows for element {element.code} {element.name!r}")
    words = flag_words(flags, (r["Flag"] for *_, r in kept if r["Flag"]), FLAGS_MEMBER)
    # The flags of the published values decide whether each value needs its own note; an empty value's flag is its
    # missing_reason.
    counts = Counter(r["Flag"] for *_, r in kept if r["Flag"] and r["Value"] != "")
    value_words = {f: w for f, w in words.items() if f in counts}
    several = len(value_words) > 1
    obs: list[Observation] = []
    nulls = 0
    order = list(ITEMS)
    for entity, item_id, year, r in sorted(kept, key=lambda k: (k[0], order.index(k[3]["Item Code"]), k[2])):
        flag = r["Flag"]
        notes = [f"FAO note: {r['Note']}"] if r["Note"] else []
        if r["Value"] == "":
            if not flag:
                raise FaostatBulkError(f"{entity} {item_id} {year}: empty value without a flag")
            nulls += 1
            obs.append(
                Observation(
                    entity=entity,
                    period=f"{year:04d}",
                    value=None,
                    missing_reason=f'FAO flag {flag}: "{words[flag]}".',
                    note=" ".join(notes) or None,
                    dims={"category": item_id},
                )
            )
            continue
        if several and flag:
            notes.append(f"FAO flag {flag}: {words[flag]}.")
        obs.append(
            Observation(
                entity=entity,
                period=f"{year:04d}",
                value=float(r["Value"]),
                note=" ".join(notes) or None,
                dims={"category": item_id},
            )
        )
    items = ", ".join(f'"{name}" ({code})' for code, (_, name, _) in ITEMS.items())
    years = sorted({y for _, _, y, _ in kept})
    steps = [
        f'Kept the rows of element "{element.name}" (code {element.code}, unit "{element.unit}") for items {items}, '
        f"{years[0]}–{years[-1]}, for every area FAO reports; values are published as printed.",
        not_published_step(left_out),
        flag_step(value_words, counts),
    ]
    if nulls:
        steps.append(f"{nulls} values are empty in the file and are published as null, with FAO's flag as the reason.")
    return obs, steps


@functools.lru_cache(maxsize=2)
def _read_zip(path: Path, element: Element) -> tuple[Table, dict[str, str]]:
    # Snapshot paths are content-addressed, so caching by path is caching by content.
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f, element)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _runner(element: Element):
    def run(files: dict[str, InputFile]) -> Result:
        table, flags = _read_zip(files[LAND_USE.key].path, element)
        updated, vintage_step = vintage_of(files, LAND_USE, DATASET_CODE, table.data_rows, DATA_MEMBER)
        obs, steps = observations(table, element, flags)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[vintage_step, *steps],
        )

    return run


_DIMENSION = Dimension(
    id="category",
    label="Land use",
    values=[DimensionValue(id=i, label=label) for i, _, label in ITEMS.values()],
)
_GEOGRAPHY = "Countries and territories, the European Union (27) and the world"
_BASIS = (
    "FAOSTAT Land Use (RL) categories: agricultural land = cropland (arable land and permanent crops) + permanent "
    "meadows and pastures; forest land as defined by FAO's Global Forest Resources Assessment (land over 0.5 ha with "
    "trees over 5 m and canopy cover over 10 percent, not mainly under agricultural or urban use), taken by FAO from "
    "FRA 2025 and available from 1990. Country reports, with FAO estimates and imputations where countries did not "
    "report (each value's flag is given)."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="land-use.faostat.area",
                title="Agricultural land, cropland, pasture and forest area",
                description="How much land each country, the European Union and the world use as cropland and as "
                "permanent meadows and pastures (together, agricultural land), and how much is forest, each year "
                "since 1961 (forest since 1990), in thousands of hectares, as reported to and estimated by FAO.",
                kind="series",
                unit=Unit(code="kha", label="thousand hectares", short="thousand ha"),
                display=Display(decimals=0),
                scope=Scope(geography=_GEOGRAPHY, basis=_BASIS),
                geo_coverage="mixed",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("category", "agricultural-land"),),
            ),
            inputs=(LAND_USE, CATALOGUE),
            run=_runner(AREA),
            module_file=here,
            validation=Validation(min_rows=20_000, value_range=(0.0, 6_000_000.0)),
        ),
        Transform(
            spec=Spec(
                id="land-use.faostat.share-of-land-area",
                title="Agricultural land, cropland, pasture and forest as a share of land area",
                description="The part of each country's land area, and of the world's, that is cropland, "
                "permanent meadows and pastures (together, agricultural land) or forest, each year since 1961 "
                "(forest since 1990), as calculated by FAO.",
                kind="series",
                unit=Unit(code="percent", label="percent of land area", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis=_BASIS + " Share = FAO's element \"Share in Land area\": the category's area divided by "
                    "the country's land area (country area less inland waters), as published by FAO.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("category", "agricultural-land"),),
            ),
            inputs=(LAND_USE, CATALOGUE),
            run=_runner(SHARE),
            module_file=here,
            validation=Validation(min_rows=20_000, value_range=(0.0, 100.0)),
        ),
    ]

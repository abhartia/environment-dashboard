"""FAOSTAT SDG indicators (SDGB): SDG 12.3.1a food loss percentage, world, total and by commodity group.

Input. The SDGB bulk zip holds SDG_BulkDownloads_E_All_Data_(Normalized).csv (UTF-8, CRLF, every field quoted; columns
Area Code, Area Code (M49), Area, Item Code, Item Code (SDG), Item, Element Code, Element, Year Code, Year, Unit, Value,
Flag, Note) and its flag codebook SDG_BulkDownloads_E_Flags.csv. The rows used are element 6121 "Value", unit "%", of
the five 12.3.1a food loss percentage items below (matched by code; the names and SDG series codes next to the codes
must be the ones below, or the transform stops).

What it measures (FAO's SDG 12.3.1a definition): the share of food, by economic value, lost along the supply chain
from post-harvest up to, but not including, retail, against the total quantity produced. Losses on the farm before
harvest and waste at retail, in food service and in households are not included (households, food service and retail
are SDG 12.3.1b, the UNEP Food Waste Index).

Geography. In this release the indicator is published only for the world and for FAO's regional groups (M49 regions,
LDCs, LLDCs, SIDS); the world rows are published, the regional groups are left out (M49 regions are not entities here).
Any country row would be mapped through faostat_bulk.AREAS.

Notes and flags. Every world row carries the same Note, FAO's remark that before July 2022 the series was disseminated
under SDG code AG_FLS_IDX; it is stated once in a processing step, not copied to each value (the bulk file renders its
quotation marks as mojibake). Any other Note stops the transform. Flags must be in the codebook.

Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
"""

from __future__ import annotations

import functools
import zipfile
from collections import Counter
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

SDG = Input(SOURCE, "sdg-indicators")
DATASET_CODE = "SDGB"
DATA_MEMBER = "SDG_BulkDownloads_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "SDG_BulkDownloads_E_Flags.csv"
COLUMNS = [
    "Area Code",
    "Area Code (M49)",
    "Area",
    "Item Code",
    "Item Code (SDG)",
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
ELEMENT = ("6121", "Value")
UNIT = "%"
ITEM_PREFIX = "24044"

# FAO item code -> (our dimension value id, "Item Code (SDG)" as printed in the data rows, FAO's item name, our label).
# The data rows cut the SDG code to 25 characters (the item list gives AG_FLS_PCT-CPC2_1_AGGS3001 to ...3004), so the
# commodity groups are told apart by Item Code.
ITEMS: dict[str, tuple[str, str, str, str]] = {
    "24044-_T": ("total", "AG_FLS_IDX-_T", "12.3.1a Food loss percentage: total", "All commodities"),
    "24044-AGGS3001": (
        "cereals-and-pulses",
        "AG_FLS_PCT-CPC2_1_AGGS300",
        "12.3.1a Food loss percentage: cereals and pulses",
        "Cereals and pulses",
    ),
    "24044-AGGS3002": (
        "fruits-and-vegetables",
        "AG_FLS_PCT-CPC2_1_AGGS300",
        "12.3.1a Food loss percentage: fruits and vegetables",
        "Fruits and vegetables",
    ),
    "24044-AGGS3003": (
        "roots-tubers-and-oil-bearing-crops",
        "AG_FLS_PCT-CPC2_1_AGGS300",
        "12.3.1a Food loss percentage: roots, tubers and oil-bearing crops",
        "Roots, tubers and oil-bearing crops",
    ),
    "24044-AGGS3004": (
        "meat-and-animal-products",
        "AG_FLS_PCT-CPC2_1_AGGS300",
        "12.3.1a Food loss percentage: meat and animals products",
        "Meat and animal products",
    ),
}
# The Note on every row, up to the first quotation mark (rendered as mojibake in the file).
NOTE_PREFIX = "Non-relevant | FAO | Prior to July 2022: data on "


def read(lines) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Item Code"].startswith(ITEM_PREFIX + "-") and r["Element Code"] == ELEMENT[0]

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, f'"{ITEM_PREFIX}-'.encode())


def observations(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    kept: list[tuple[str, str, int, dict[str, str]]] = []
    left_out: set[str] = set()
    notes: Counter[str] = Counter()
    for r in table.rows:
        if r["Item Code"] not in ITEMS:
            raise FaostatBulkError(f"unknown 12.3.1a item {r['Item Code']!r} ({r['Item']!r}); declare it in ITEMS")
        item_id, sdg_code, name, _ = ITEMS[r["Item Code"]]
        what = f"{r['Area Code']} {name} {r['Year']}"
        if (r["Item Code (SDG)"], r["Item"], r["Element"]) != (sdg_code, name, ELEMENT[1]):
            raise FaostatBulkError(
                f"item {r['Item Code']} is {r['Item Code (SDG)']!r} {r['Item']!r} / {r['Element']!r}, expected "
                f"{sdg_code!r} {name!r} / {ELEMENT[1]!r}"
            )
        if r["Unit"] != UNIT:
            raise FaostatBulkError(f"{what}: unit {r['Unit']!r}, expected {UNIT!r}")
        entity = area_entity(r["Area Code"], r["Area Code (M49)"])
        if entity is None:
            left_out.add(r["Area Code"])
            continue
        if r["Value"] == "":
            raise FaostatBulkError(f"{what}: empty value for a published area; decide how to show it first")
        if r["Note"] and not r["Note"].startswith(NOTE_PREFIX):
            raise FaostatBulkError(f"{what}: unexpected Note {r['Note']!r}")
        notes[r["Note"]] += 1
        kept.append((entity, item_id, year_of(r, what), r))
    if not kept:
        raise FaostatBulkError("no 12.3.1a food loss percentage rows for a published area")
    counts = Counter(r["Flag"] for *_, r in kept)
    words = flag_words(flags, counts, FLAGS_MEMBER)
    order = list(ITEMS)
    obs = [
        Observation(
            entity=entity,
            period=f"{year:04d}",
            value=float(r["Value"]),
            note=f"FAO flag {r['Flag']}: {words[r['Flag']]}." if len(words) > 1 else None,
            dims={"commodity": item_id},
        )
        for entity, item_id, year, r in sorted(kept, key=lambda k: (k[0], order.index(k[3]["Item Code"]), k[2]))
    ]
    years = sorted({y for _, _, y, _ in kept})
    entities = sorted({e for e, *_ in kept})
    steps = [
        f'Kept the rows of the five "12.3.1a Food loss percentage" items (total and four commodity groups), element '
        f'"{ELEMENT[1]}" (code {ELEMENT[0]}), unit "{UNIT}", {years[0]}–{years[-1]}, for {", ".join(entities)}; '
        "values are published as printed.",
        not_published_step(left_out),
        flag_step(words, counts),
    ]
    if notes.get("", 0) != sum(notes.values()):
        steps.append(
            f"{sum(n for k, n in notes.items() if k)} of the values carry FAO's note that before July 2022 the series "
            'was disseminated under the SDG code "AG_FLS_IDX".'
        )
    return obs, steps


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _run(files: dict[str, InputFile]) -> Result:
    table, flags = _read_zip(files[SDG.key].path)
    updated, vintage_step = vintage_of(files, SDG, DATASET_CODE, table.data_rows, DATA_MEMBER)
    obs, steps = observations(table, flags)
    return Result(
        observations=obs,
        vintage=updated.isoformat(),
        year=str(updated.year),
        date_published=updated.isoformat(),
        steps=[vintage_step, *steps],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="food-loss.faostat.sdg-12-3-1a",
                title="Food lost between harvest and retail (SDG 12.3.1a)",
                description="The share of the world's food, by economic value, lost after harvest on the farm, in "
                "storage, transport and processing, before it reaches shops, each year since 2015, in total and for "
                "four commodity groups, as estimated by FAO for SDG indicator 12.3.1a.",
                kind="series",
                unit=Unit(code="percent", label="percent of food produced, by economic value", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    basis="SDG 12.3.1a food loss percentage (FAO custodian): losses from post-harvest up to, but not "
                    "including, retail, as a share of production weighted by economic value (international dollar "
                    "prices). Pre-harvest losses and waste at retail, in food service and in households (SDG "
                    "12.3.1b) are not included.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="commodity",
                        label="Commodity group",
                        values=[DimensionValue(id=i, label=label) for i, _, _, label in ITEMS.values()],
                    ),
                ),
                headline_dims=(("commodity", "total"),),
            ),
            inputs=(SDG, CATALOGUE),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=40, value_range=(0.0, 60.0)),
        )
    ]

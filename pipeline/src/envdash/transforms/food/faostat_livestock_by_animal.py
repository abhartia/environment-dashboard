"""FAOSTAT Emissions from livestock (GLE): methane from farm animals by kind of animal, for the world and each country,
1961-2023, in million tonnes of methane.

Input. Emissions_livestock_E_All_Data_(Normalized).csv in the GLE bulk zip (1.1 GB uncompressed, read as a stream;
columns Area Code, Area Code (M49), Area, Item Code, Item Code (CPC), Item, Element Code, Element, Year Code, Year,
Source Code, Source, Unit, Value, Flag, Note) and its flag codebook Emissions_livestock_E_Flags.csv. Rows used: element
72441 "Livestock total (Emissions CH4)" (methane from enteric fermentation plus manure management), unit "kt", Source
"FAO TIER 1" (the "UNFCCC" rows are never mixed in), for the 16 animal items in ANIMALS, matched by code with FAO's
names checked. FAO's aggregates (Cattle, Swine, Chickens, Poultry Birds, Sheep and Goats, Mules and Asses, Camels and
Llamas, All Animals) are not published, so nothing is counted twice; "All Animals" (1755) is read only to check that the
16 add up to it, to within 0.01 kilotonnes, in every area and year (faostat_parts.check_parts). Values are converted
from kilotonnes to million tonnes of methane; they are never converted to CO₂-equivalent. FAO's projections for 2030
and 2050 (flag F) are left out.

Vintage. The catalogue entry for GLE (datasets_E.json) gives FileRows 6,941,916 while this file's CSV has 6,650,421
data rows, so FileRows cannot tie the entry to the file as faostat_bulk.vintage_of does for other domains. The entry is
tied to the file by its FileLocation (this zip's URL) and its FileSize, which must equal the zip's size in kilobytes
rounded up (the catalogue's convention: its GT and EI entries give 20022KB and 3556KB for zips of 20,501,708 and
3,640,396 bytes). Both checks are stated in a processing step, with the FileRows difference.

Areas are mapped by faostat_bulk.AREAS through faostat_parts (world and countries; the European Union and FAO's groups,
including "China", are left out).
"""

from __future__ import annotations

import functools
import json
import math
import zipfile
from collections import Counter
from datetime import date
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
)
from envdash.transforms.food.faostat_parts import areas_step, check_parts, entity_of, gather

LIVESTOCK = Input(SOURCE, "emissions-livestock")
DATASET_CODE = "GLE"
DATA_MEMBER = "Emissions_livestock_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "Emissions_livestock_E_Flags.csv"
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
    "Source Code",
    "Source",
    "Unit",
    "Value",
    "Flag",
    "Note",
]
TIER1 = "FAO TIER 1"
CH4_TOTAL = "72441"
ELEMENTS = {CH4_TOTAL: ("Livestock total (Emissions CH4)", "kt")}
ALL_ANIMALS = ("1755", "All Animals")
TOLERANCE_KT = Decimal("0.01")
# FAO Item Code -> (our animal id, FAO's item name as written in the data file).
ANIMALS: dict[str, tuple[str, str]] = {
    "960": ("cattle-dairy", "Cattle, dairy"),
    "961": ("cattle-non-dairy", "Cattle, non-dairy"),
    "946": ("buffalo", "Buffalo"),
    "976": ("sheep", "Sheep"),
    "1016": ("goats", "Goats"),
    "1049": ("swine-market", "Swine, market"),
    "1051": ("swine-breeding", "Swine, breeding"),
    "1053": ("chickens-broilers", "Chickens, broilers"),
    "1052": ("chickens-layers", "Chickens, layers"),
    "1068": ("ducks", "Ducks"),
    "1079": ("turkeys", "Turkeys"),
    "1096": ("horses", "Horses"),
    "1107": ("asses", "Asses"),
    "1110": ("mules-and-hinnies", "Mules and hinnies"),
    "1126": ("camels", "Camels"),
    "1177": ("llamas", "Llamas"),
}
ITEMS = {ALL_ANIMALS[0]: ALL_ANIMALS[1]} | {code: name for code, (_, name) in ANIMALS.items()}
MARKER = f'"{CH4_TOTAL}"'.encode()


def read(lines) -> Table:
    def keep(r: dict[str, str]) -> bool:
        return r["Element Code"] == CH4_TOTAL and r["Item Code"] in ITEMS and r["Source"] == TIER1

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, MARKER)


def observations(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    g = gather(table.rows, items=ITEMS, elements=ELEMENTS, source=TIER1, what=DATA_MEMBER)
    checked = check_parts(g, CH4_TOTAL, ALL_ANIMALS[0], ANIMALS, TOLERANCE_KT)
    order = list(ANIMALS)
    left_out: set[str] = set()
    rows = []
    for (area, _, item), series in g.values.items():
        if item not in ANIMALS:
            continue
        entity = entity_of(area, g, left_out)
        if entity is None:
            continue
        for year, cell in series.items():
            rows.append((entity, order.index(item), year, {"animal": ANIMALS[item][0]}, cell))
    if not any(r[0] == "WLD" for r in rows):
        raise FaostatBulkError("no World rows")
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    counts = Counter(r[4].flag for r in rows)
    words = flag_words(flags, counts, FLAGS_MEMBER)
    thousand = Decimal(1000)
    obs = []
    for entity, _, year, dims, cell in rows:
        notes = [f"FAO note: {cell.note}"] if cell.note else []
        if len(words) > 1:
            notes.append(f"FAO flag {cell.flag}: {words[cell.flag]}.")
        obs.append(
            Observation(
                entity=entity,
                period=f"{year:04d}",
                value=float(cell.value / thousand),
                dims=dims,
                note=" ".join(notes) or None,
            )
        )
    years = sorted({r[2] for r in rows})
    forecast = g.forecast_years()
    steps = [
        f'Kept the "{TIER1}" rows of element "{ELEMENTS[CH4_TOTAL][0]}" (code {CH4_TOTAL}): methane from enteric '
        "fermentation and manure management, in kilotonnes of methane, for the 16 animal items FAO estimates "
        f"separately, {years[0]}–{years[-1]}. FAO's aggregate items are not used. Rows from FAO's \"UNFCCC\" source "
        "are not used.",
        f"Checked, in all {checked:,} areas and years where FAO prints them (FAO's regions included), that item "
        f'"{ALL_ANIMALS[1]}" ({ALL_ANIMALS[0]}) equals the sum of the 16 animals present, to within {TOLERANCE_KT} '
        "kilotonnes. Nothing is computed from this check; it shows that the animals published are FAO's whole "
        "total, with no remainder.",
        areas_step(left_out),
        "Converted kilotonnes to million tonnes by dividing by 1,000 (exact decimal arithmetic on the printed "
        "values). The values stay in tonnes of methane; they are not converted to CO₂-equivalent.",
        flag_step(words, counts),
    ]
    if forecast:
        shown = " and ".join(str(y) for y in forecast)
        steps.append(f'Left out FAO\'s projections for {shown}, which the file flags F ("Forecast value").')
    return obs, steps


def catalogue_check(catalogue: bytes, url: str, zip_bytes: int, data_rows: int) -> tuple[date, str]:
    """(DateUpdate, the step stating how the catalogue entry was tied to this file)."""
    doc = json.loads(catalogue.decode("utf-8"))
    entries = [d for d in doc["Datasets"]["Dataset"] if d["DatasetCode"] == DATASET_CODE]
    if len(entries) != 1:
        raise FaostatBulkError(f"datasets_E.json has {len(entries)} entries for {DATASET_CODE}")
    e = entries[0]
    if e["FileLocation"] != url:
        raise FaostatBulkError(f"datasets_E.json gives {DATASET_CODE} at {e['FileLocation']!r}, not {url!r}")
    size = f"{math.ceil(zip_bytes / 1024)}KB"
    if e["FileSize"] != size:
        raise FaostatBulkError(
            f"datasets_E.json gives {DATASET_CODE} FileSize {e['FileSize']} but the zip is {zip_bytes:,} bytes "
            f"({size}): the catalogue describes another file, so its DateUpdate cannot be this file's vintage"
        )
    updated = date.fromisoformat(e["DateUpdate"][:10])
    rows = int(e["FileRows"])
    rows_words = (
        f"Its FileRows, {rows:,}, equals the number of data rows in this file."
        if rows == data_rows
        else f"Its FileRows, {rows:,}, is not the number of data rows in this file ({data_rows:,}), so it does not "
        "identify the file."
    )
    step = (
        f"Read {DATA_MEMBER} from FAOSTAT's {DATASET_CODE} bulk zip as a stream. The vintage is the domain's "
        f"DateUpdate, {updated.day} {updated:%B %Y}, from FAOSTAT's bulk-download catalogue (datasets_E.json), whose "
        f"entry names this zip as its FileLocation and gives FileSize {e['FileSize']}, this zip's {zip_bytes:,} "
        f"bytes in kilobytes rounded up. {rows_words}"
    )
    return updated, step


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _run(files: dict[str, InputFile]) -> Result:
    t, c = files[LIVESTOCK.key], files[CATALOGUE.key]
    table, flags = _read_zip(t.path)
    url = str(t.snapshot.url) if t.snapshot.url else ""
    updated, vintage_step = catalogue_check(c.path.read_bytes(), url, t.snapshot.bytes, table.data_rows)
    if t.snapshot.last_modified:
        vintage_step += f" The zip was last modified on the server on {t.snapshot.last_modified}."
    obs, steps = observations(table, flags)
    return Result(
        observations=obs,
        vintage=updated.isoformat(),
        year=str(updated.year),
        date_published=updated.isoformat(),
        steps=[vintage_step, *steps],
        changes="converted from kilotonnes to million tonnes of methane.",
    )


ANIMAL_DIM = Dimension(
    id="animal", label="Animal", values=[DimensionValue(id=i, label=name) for i, name in ANIMALS.values()]
)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="food.faostat.livestock-ch4-by-animal",
                title="Methane from farm animals' digestion and manure, by animal",
                description="Methane released each year since 1961 by farm animals, for the world and each country, "
                "from their digestion (enteric fermentation) and from manure management, for each of the 16 kinds "
                "of animal FAO estimates separately: dairy and non-dairy cattle, buffalo, sheep, goats, market and "
                "breeding pigs, broiler and laying chickens, ducks, turkeys, horses, asses, mules and hinnies, "
                "camels and llamas. They add up exactly to FAO's total for all animals. Manure here is only the "
                "methane from managing manure (storing and handling it); nitrous oxide from manure, and manure "
                "left on pasture or spread on fields (which emit nitrous oxide, not methane), are not included. In "
                "tonnes of methane, not carbon dioxide equivalent, so these values cannot be added to or compared "
                "with values in carbon dioxide equivalent.",
                kind="series",
                unit=Unit(
                    code="MtCH4", label="million tonnes of methane (not carbon dioxide equivalent)", short="Mt CH₄"
                ),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Countries and territories, and the world",
                    basis='FAOSTAT Emissions from livestock (GLE), element "Livestock total (Emissions CH4)": '
                    "methane from enteric fermentation and manure management, mass of methane (not "
                    "CO₂-equivalent), for 16 non-overlapping animal items that add up to FAO's item \"All "
                    "Animals\". FAO's aggregate items (Cattle, Swine, Chickens, Poultry Birds, Sheep and Goats, "
                    "Mules and Asses, Camels and Llamas) are not included. FAO Tier 1 estimates (IPCC 2006 "
                    "Guidelines) from FAOSTAT animal numbers, not country inventory submissions; FAO's projections "
                    "for 2030 and 2050 are not included.",
                ),
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(ANIMAL_DIM,),
                headline_dims=(("animal", "cattle-non-dairy"),),
            ),
            inputs=(LIVESTOCK, CATALOGUE),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=100_000, value_range=(0.0, 100.0)),
        )
    ]

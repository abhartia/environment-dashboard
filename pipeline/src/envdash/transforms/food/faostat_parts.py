"""Shared reading for the FAOSTAT breakdowns of food's emissions (by stage, process, product and animal). Not an
indicator module: `transforms()` returns nothing.

These indicators publish parts of a total exactly as FAO prints them. `gather` keeps the rows of the wanted items and
elements, checks the names next to the codes, the units and the years, and sets FAO's projections (flag F, "Forecast
value") aside after checking that they come after the last estimated year of their series. `check_parts` checks that
the parts add up to FAO's own published total in every area and year where either is printed, so a stacked chart of
the parts never shows more or less than FAO's total; it publishes nothing itself.

Areas are mapped by faostat_bulk.AREAS. These indicators cover the world and countries and territories only, so the
European Union (27), which faostat_bulk.AREAS maps for other indicators, is left out here, as are FAO's own regional
groups (including "China", FAO's sum of mainland China, Hong Kong, Macao and Taiwan, which are published separately).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from envdash.paths import Paths
from envdash.transform import Transform
from envdash.transforms.food.faostat_bulk import (
    AREAS,
    FAO_GROUPS,
    FORMER,
    NO_ENTITY,
    FaostatBulkError,
    area_entity,
    year_of,
)

FORECAST = "F"
REGIONS = {"EU27": "the European Union (27)"}
"""Entities of faostat_bulk.AREAS that are regions, left out of these world-and-country indicators."""


@dataclass(frozen=True)
class Cell:
    value: Decimal
    flag: str
    note: str


Key = tuple[str, str, str]
"""(FAO Area Code, Element Code, Item Code)."""


@dataclass
class Gathered:
    values: dict[Key, dict[int, Cell]] = field(default_factory=lambda: defaultdict(dict))
    forecast: dict[Key, list[int]] = field(default_factory=lambda: defaultdict(list))
    m49: dict[str, str] = field(default_factory=dict)
    """FAO Area Code -> "Area Code (M49)" as printed."""

    def forecast_years(self) -> list[int]:
        return sorted({y for ys in self.forecast.values() for y in ys})


def gather(
    rows: Iterable[dict[str, str]],
    *,
    items: Mapping[str, str],
    elements: Mapping[str, tuple[str, str]],
    source: str | None,
    what: str,
) -> Gathered:
    """Rows of `items` (code -> FAO's name) and `elements` (code -> (FAO's name, unit)), from `source` when the file
    has a Source column (None when it has none). Every value must be printed; F rows are projections."""
    g = Gathered()
    for r in rows:
        item, element = r["Item Code"], r["Element Code"]
        if item not in items or element not in elements:
            continue
        if source is not None and r["Source"] != source:
            continue
        if r["Item"] != items[item] or r["Element"] != elements[element][0]:
            raise FaostatBulkError(
                f"{what}: item {item} / element {element} are named {r['Item']!r} / {r['Element']!r}, expected "
                f"{items[item]!r} / {elements[element][0]!r}"
            )
        where = f"{what}: area {r['Area Code']} item {item} element {element} {r['Year']}"
        if r["Unit"] != elements[element][1]:
            raise FaostatBulkError(f"{where}: unit {r['Unit']!r}, expected {elements[element][1]!r}")
        year = year_of(r, where)
        if r["Value"] == "":
            raise FaostatBulkError(f"{where}: empty Value; re-read the file before trusting it")
        prev = g.m49.setdefault(r["Area Code"], r["Area Code (M49)"])
        if prev != r["Area Code (M49)"]:
            raise FaostatBulkError(f"{where}: M49 {r['Area Code (M49)']} differs from {prev} in earlier rows")
        key = (r["Area Code"], element, item)
        if r["Flag"] == FORECAST:
            g.forecast[key].append(year)
            continue
        if year in g.values[key]:
            raise FaostatBulkError(f"{where}: more than one value for the year")
        g.values[key][year] = Cell(Decimal(r["Value"]), r["Flag"], r.get("Note", ""))
    for key, years in g.forecast.items():
        last = max(g.values[key]) if g.values.get(key) else None
        if last is None or min(years) <= last:
            raise FaostatBulkError(f"{what}: {key} forecast years {sorted(years)} are not all after {last}")
    if not g.values:
        raise FaostatBulkError(f"{what}: no rows of items {sorted(items)} / elements {sorted(elements)}")
    return g


def entity_of(code: str, g: Gathered, left_out: set[str]) -> str | None:
    """Our entity for an FAO area, or None (recorded in left_out) for areas these indicators do not publish."""
    e = area_entity(code, g.m49[code])
    if e is None or e in REGIONS:
        left_out.add(code)
        return None
    return e


def plain_labels(names: Mapping[str, str], labels: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """(our id, FAO's item name, the label shown) for each id in `names` (id -> FAO's name), in that order. FAO's item
    names are terms of art ("Enteric Fermentation"), so each value is shown under a label in plain words instead."""
    if set(names) != set(labels):
        raise FaostatBulkError(f"plain labels do not match the items: {sorted(set(names) ^ set(labels))}")
    return [(i, names[i], labels[i]) for i in names]


def labels_step(labelled: Iterable[tuple[str, str, str]]) -> str:
    """Words for the plain labels given to FAO's item names, so each shown name traces back to FAO's."""
    pairs = [f'"{fao}" as "{ours}"' for _, fao, ours in labelled if fao != ours]
    return (
        "Labelled FAO's items in plain words: " + "; ".join(pairs) + ". Only the names shown differ; every value is "
        "FAO's item of that name."
    )


def areas_step(left_out: Iterable[str]) -> str:
    """Words for the areas of the file that were left out, by reason."""
    left_out = set(left_out)
    parts = []
    for table, why in (
        (FORMER, "former states and territories reported only before their dissolution, with no entity here"),
        (NO_ENTITY, "territories with no entity in pipeline/geo/entities.csv"),
        (FAO_GROUPS, "FAO regional and analytical groups"),
    ):
        names = sorted(table[c][1] for c in left_out if c in table)
        if names:
            parts.append(f"{why} ({', '.join(names)})")
    regions = sorted(REGIONS[AREAS[c][1]] for c in left_out if c in AREAS and AREAS[c][1] in REGIONS)
    if regions:
        parts.append(f"{', '.join(regions)}, a region (only the world and countries and territories are published)")
    if not parts:
        return "Every area in the rows used is published."
    return "Left out " + "; ".join(parts) + ". Their values are never re-assigned to other entities."


def check_parts(
    g: Gathered, element: str, total: str, parts: Iterable[str], tolerance: Decimal, years: range | None = None
) -> int:
    """FAO's total item equals the sum of the part items present, in every area and year (in `years`, if given) where
    the total or any part is printed. Returns the number of area-years checked; raises on the first mismatch."""
    parts = list(parts)
    by: dict[tuple[str, int], dict[str, Decimal]] = defaultdict(dict)
    for (area, el, item), series in g.values.items():
        if el != element or (item != total and item not in parts):
            continue
        for year, cell in series.items():
            if years is None or year in years:
                by[(area, year)][item] = cell.value
    checked = 0
    for (area, year), d in sorted(by.items()):
        present = [p for p in parts if p in d]
        if total not in d:
            raise FaostatBulkError(f"area {area} {year}: parts {present} of item {total} are printed but not the total")
        if not present:
            raise FaostatBulkError(f"area {area} {year}: item {total} is printed but none of its parts {parts}")
        diff = abs(d[total] - sum(d[p] for p in present))
        if diff > tolerance:
            raise FaostatBulkError(
                f"area {area} {year}: item {total} = {d[total]} but its parts add up to {sum(d[p] for p in present)}"
            )
        checked += 1
    return checked


def transforms(paths: Paths) -> list[Transform]:
    return []

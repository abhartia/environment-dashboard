"""FAOSTAT World Census of Agriculture (WCAD): the number of agricultural holdings in each country, and the number and
area of holdings by FAO's land-size classes, from each country's census of agriculture.

Input. The WCAD bulk zip holds World_Census_Agriculture_E_All_Data_(Normalized).csv (UTF-8, CRLF, data fields quoted;
columns COLUMNS below) and its flag codebook World_Census_Agriculture_E_Flags.csv. The rows used are matched by code:
item 27002 "Holdings" with element 60850 "Number" (unit "No") for the total, and the land-size items of SIZE_CLASSES
with elements 60850 "Number" and 50260 "Area" (unit "ha"). Each item's and element's name and unit must be the ones
declared here, or the transform stops.

Censuses, not years. Countries take their census in different years of a ten-year World Census of Agriculture (WCA)
round, and a few take two in one round (the United States in 2017 and 2022). Each observation is one country's census:
its period is the census year as FAO prints it, written in ISO form ("2015/16" and "2018-2021" become 2015/2016 and
2018/2021; a split year must run into the next year and a range must run forward, or the transform stops), and its
note names the WCA round, the census year as printed, FAO's flag and, where FAO recorded one, FAO's note on how the
country defines a holding. FAO says "countries may apply their own definitions of agricultural holdings, which could
affect the international comparability of census data" (datasets_E.json, WCAD). So nothing is summed: there is no world
or regional total (it would add censuses of different years and leave out countries without one), and the size
classes are never added up either.

Land-size classes. FAO's own classes as named in the item list ("Holdings with land size 0-<1", ...). Countries report
different sets, and some classes nest (2-<5 against 2-<3, 3-<4 and 4-<5; >=1000 against 1000-<2500 and >=2500); in this
file no census reports a class together with one nested in it, which the transform checks, so no value is counted
twice within a census. The item names state no unit for the classes; the areas are in hectares (unit "ha").

Areas. Mapped by faostat_bulk.area_entity. Left out, with the reason stated in a processing step: FAO's area 351
"China" (M49 159), which in FAOSTAT's area standard is China including Hong Kong, Macao and Taiwan, so its census rows
are not assigned to mainland China (CHN); and former states (Czechoslovakia, Yugoslav SFR), whose values are never
re-assigned to successor states.

Flags: A "Official figure" and I "Value imputed by a receiving agency" in the release of 27 April 2026; every
observation's note names its flag. Vintage: faostat_bulk.vintage_of (catalogue DateUpdate, checked against FileRows).
"""

from __future__ import annotations

import functools
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, OriginMeta, Result, Spec, Transform, Validation
from envdash.transforms.food.faostat_bulk import (
    CATALOGUE,
    SOURCE,
    FaostatBulkError,
    Table,
    area_entity,
    flag_words,
    not_published_step,
    read_flags,
    read_member,
    vintage_of,
)

WCAD = Input(SOURCE, "world-census-agriculture")
WCAD_PAGE = "https://www.fao.org/faostat/en/#data/WCAD"
DATASET_CODE = "WCAD"
DATA_MEMBER = "World_Census_Agriculture_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "World_Census_Agriculture_E_Flags.csv"
COLUMNS = [
    "Area Code",
    "Area Code (M49)",
    "Area",
    "Item Code",
    "Item",
    "Element Code",
    "Element",
    "WCA Round code",
    "WCA Round",
    "Census Year Code",
    "Census Year",
    "Unit",
    "Value",
    "Flag",
    "Note",
]
TOTAL_ITEM = ("27002", "Holdings")
NUMBER = ("60850", "Number", "No")
AREA = ("50260", "Area", "ha")
CHINA_GROUP = "351"
# The land-size class of each item stays within one census unless it nests with another class of FAO's list.
NESTED: dict[str, frozenset[str]] = {
    "270033": frozenset({"270032", "270034", "270035"}),
    "2700304": frozenset({"2700303", "2700305"}),
}


@dataclass(frozen=True)
class SizeClass:
    item: str
    """FAO item code."""
    printed: str
    """The class as FAO names it, after "Holdings with land size "."""
    id: str
    label: str

    @property
    def fao_name(self) -> str:
        return f"Holdings with land size {self.printed}"


# FAO's land-size items, in order of size (nested alternatives after the classes they contain).
SIZE_CLASSES: tuple[SizeClass, ...] = (
    SizeClass("270030", "0-<1", "0-1", "0 to under 1"),
    SizeClass("270031", "1-<2", "1-2", "1 to under 2"),
    SizeClass("270032", "2-<3", "2-3", "2 to under 3"),
    SizeClass("270034", "3-<4", "3-4", "3 to under 4"),
    SizeClass("270035", "4-<5", "4-5", "4 to under 5"),
    SizeClass("270033", "2-<5", "2-5", "2 to under 5"),
    SizeClass("270036", "5-<10", "5-10", "5 to under 10"),
    SizeClass("270037", "10-<20", "10-20", "10 to under 20"),
    SizeClass("270038", "20-<50", "20-50", "20 to under 50"),
    SizeClass("270039", "50-<100", "50-100", "50 to under 100"),
    SizeClass("2700300", "100-<200", "100-200", "100 to under 200"),
    SizeClass("2700301", "200-<500", "200-500", "200 to under 500"),
    SizeClass("2700302", "500-<1000", "500-1000", "500 to under 1,000"),
    SizeClass("2700303", "1000-<2500", "1000-2500", "1,000 to under 2,500"),
    SizeClass("2700305", ">=2500", "2500-plus", "2,500 or more"),
    SizeClass("2700304", ">=1000", "1000-plus", "1,000 or more"),
)
_BY_ITEM = {c.item: c for c in SIZE_CLASSES}
_ORDER = {c.item: i for i, c in enumerate(SIZE_CLASSES)}


@dataclass(frozen=True)
class Census:
    entity: str
    period: str
    start: int
    end: int
    round: str
    printed: str


def census_period(year: str, code: str, what: str) -> tuple[str, int, int]:
    """(ISO period, first year, last year) of FAO's "Census Year" and "Census Year Code", which must agree."""
    if re.fullmatch(r"\d{4}", year):
        if code != year:
            raise FaostatBulkError(f"{what}: Census Year {year!r} with code {code!r}")
        return year, int(year), int(year)
    m = re.fullmatch(r"(\d{4})/(\d{2})", year)
    if m:
        first = int(m.group(1))
        if int(m.group(2)) != (first + 1) % 100 or code != m.group(1) + m.group(2):
            raise FaostatBulkError(f"{what}: Census Year {year!r} (code {code!r}) is not one split year")
        return f"{first:04d}/{first + 1:04d}", first, first + 1
    m = re.fullmatch(r"(\d{4})-(\d{4})", year)
    if m:
        first, last = int(m.group(1)), int(m.group(2))
        if not first < last or code != m.group(1) + m.group(2):
            raise FaostatBulkError(f"{what}: Census Year {year!r} (code {code!r}) is not a forward range of years")
        return f"{first:04d}/{last:04d}", first, last
    raise FaostatBulkError(f"{what}: Census Year {year!r} is not a year, a split year or a range of years")


def read(lines) -> Table:
    items = {TOTAL_ITEM[0], *_BY_ITEM}

    def keep(r: dict[str, str]) -> bool:
        if r["Item Code"] == TOTAL_ITEM[0]:
            return r["Element Code"] == NUMBER[0]
        return r["Item Code"] in items and r["Element Code"] in (NUMBER[0], AREA[0])

    return read_member(lines, DATA_MEMBER, COLUMNS, keep, b'"2700')


def _check_row(r: dict[str, str], what: str) -> None:
    item = r["Item Code"]
    name = TOTAL_ITEM[1] if item == TOTAL_ITEM[0] else _BY_ITEM[item].fao_name
    element = NUMBER if r["Element Code"] == NUMBER[0] else AREA
    if (r["Item"], r["Element"], r["Unit"]) != (name, element[1], element[2]):
        raise FaostatBulkError(
            f"{what}: item {item} / element {r['Element Code']} is named {r['Item']!r} / {r['Element']!r} in "
            f"{r['Unit']!r}, expected {name!r} / {element[1]!r} in {element[2]!r}"
        )
    if r["WCA Round"] != r["WCA Round code"] or not re.fullmatch(r"\d{4}", r["WCA Round"]):
        raise FaostatBulkError(f"{what}: WCA Round {r['WCA Round']!r} / code {r['WCA Round code']!r}")


def _note(c: Census, flag: str, words: dict[str, str], fao_note: str) -> str:
    note = f"WCA {c.round} round, census {c.printed}. FAO flag {flag}: {words[flag]}."
    return f"{note} FAO's note: {fao_note}" if fao_note else note


@dataclass(frozen=True)
class Parsed:
    total: list[Observation]
    by_size: dict[str, list[Observation]]
    """element code -> observations by land-size class."""
    steps: list[str]


def parse(table: Table, flags: dict[str, str]) -> Parsed:
    kept: list[tuple[Census, dict[str, str]]] = []
    left_out: set[str] = set()
    for r in table.rows:
        what = f"{r['Area Code']} {r['Item Code']}/{r['Element Code']} {r['Census Year']}"
        _check_row(r, what)
        entity = area_entity(r["Area Code"], r["Area Code (M49)"])
        if entity is None:
            left_out.add(r["Area Code"])
            continue
        if r["Value"] == "":
            raise FaostatBulkError(f"{what}: empty value for a published area; decide how to show it first")
        period, start, end = census_period(r["Census Year"], r["Census Year Code"], what)
        kept.append((Census(entity, period, start, end, r["WCA Round"], r["Census Year"]), r))
    if not kept:
        raise FaostatBulkError("no WCAD rows for a published area")

    # Nested classes never side by side in one census, so no holding is counted twice within it.
    reported: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for c, r in kept:
        if r["Item Code"] in _BY_ITEM:
            reported[(c.entity, c.period, r["Element Code"])].add(r["Item Code"])
    for key, codes in reported.items():
        for outer, inner in NESTED.items():
            if outer in codes and codes & inner:
                raise FaostatBulkError(f"{key}: class {outer} is reported together with a class nested in it")

    counts = Counter(r["Flag"] for _, r in kept)
    words = flag_words(flags, counts, FLAGS_MEMBER)

    def obs(rows: list[tuple[Census, dict[str, str]]], dims: bool, whole: bool) -> list[Observation]:
        out = []
        for c, r in sorted(rows, key=lambda k: (k[0].entity, _ORDER.get(k[1]["Item Code"], -1), k[0].start, k[0].end)):
            value = Decimal(r["Value"])
            if whole and value != value.to_integral_value():
                raise FaostatBulkError(
                    f"{c.entity} {c.printed} {r['Item Code']}: a number of holdings {value} is not whole"
                )
            out.append(
                Observation(
                    entity=c.entity,
                    period=c.period,
                    value=float(value),
                    note=_note(c, r["Flag"], words, r["Note"]),
                    dims={"land-size": _BY_ITEM[r["Item Code"]].id} if dims else {},
                )
            )
        _check_order(out)
        return out

    total = obs([k for k in kept if k[1]["Item Code"] == TOTAL_ITEM[0]], dims=False, whole=True)
    by_size = {
        el: obs(
            [k for k in kept if k[1]["Item Code"] in _BY_ITEM and k[1]["Element Code"] == el], True, el == NUMBER[0]
        )
        for el in (NUMBER[0], AREA[0])
    }
    rounds = sorted({c.round for c, _ in kept})
    steps = [
        f'Kept the rows of item {TOTAL_ITEM[0]} "{TOTAL_ITEM[1]}" (element {NUMBER[0]} "{NUMBER[1]}") and of FAO\'s '
        f'{len(SIZE_CLASSES)} land-size items (elements {NUMBER[0]} "{NUMBER[1]}" and {AREA[0]} "{AREA[1]}", in '
        f"hectares), for every country and census in the WCA rounds {rounds[0]} to {rounds[-1]}. Values are "
        "published as printed, one per country and census, with the census year as the period (split years such as "
        '"2015/16" and ranges such as "2018-2021" written as 2015/2016 and 2018/2021) and the WCA round, census year '
        "as printed, FAO's flag and FAO's note in each value's note.",
        "Nothing is added up: there is no world or regional total, because each country's census is of a different "
        "year and countries define a holding in their own way, and the land-size classes, which differ between "
        "countries and partly nest, are not summed. No census in this file reports a class together with a class "
        "nested in it.",
        not_published_step(left_out),
    ]
    if CHINA_GROUP in left_out:
        steps.append(
            "FAO reports China's census rows under area 351 \"China\" (M49 159), which FAOSTAT's area standard uses "
            "for China including Hong Kong, Macao and Taiwan; they are not assigned to mainland China (CHN)."
        )
    listed = "; ".join(f'{f} "{w}" ({counts[f]:,} values)' for f, w in words.items())
    steps.append(f"Flags in the rows used: {listed}; each value's note names its flag.")
    return Parsed(total, by_size, steps)


def _check_order(obs: list[Observation]) -> None:
    """Within each country and class, censuses follow one another: each starts after the previous one started."""
    last: dict[tuple, int] = {}
    for o in obs:
        assert o.period is not None
        start = int(o.period[:4])
        key = (o.entity, tuple(sorted(o.dims.items())))
        if key in last and start <= last[key]:
            raise FaostatBulkError(f"{key}: census {o.period} does not start after the previous census")
        last[key] = start


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Table, dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            table = read(f)
        flags = read_flags(z.read(FLAGS_MEMBER), FLAGS_MEMBER)
    return table, flags


def _runner(which: str):
    def run(files: dict[str, InputFile]) -> Result:
        table, flags = _read_zip(files[WCAD.key].path)
        updated, vintage_step = vintage_of(files, WCAD, DATASET_CODE, table.data_rows, DATA_MEMBER)
        parsed = parse(table, flags)
        obs = parsed.total if which == "total" else parsed.by_size[which]
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[vintage_step, *parsed.steps],
            # Both origins (the WCAD zip and the catalogue entry read for its DateUpdate) name WCAD's own page.
            origin_meta={i.key: OriginMeta(url_main=WCAD_PAGE) for i in (WCAD, CATALOGUE)},
        )

    return run


_SIZE = Dimension(
    id="land-size",
    label="Land-size class of the holding (FAO's classes)",
    values=[DimensionValue(id=c.id, label=c.label) for c in SIZE_CLASSES],
)
_BASIS = (
    "Agricultural holdings counted in each country's census of agriculture, as compiled by FAO for the World Census of "
    "Agriculture (WCA) rounds 1930 to 2020. Each value is one census; the period is the census year, and each value's "
    "note gives the WCA round and FAO's note on how the country defines a holding (countries set their own minimum "
    "size limits and scope, which affects comparisons between countries). No world or regional total."
)
_SIZE_BASIS = (
    f'{_BASIS} Land-size classes are FAO\'s, as named in its item list (for example "0-<1"); countries report '
    "different sets of classes, some classes contain others (2 to under 5 contains 2 to under 3, 3 to under 4 and 4 "
    "to under 5), and the classes are never added up here. The item names state no unit for the classes."
)
_HOLDINGS = Unit(code="holdings", label="agricultural holdings", short="holdings")


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    common = dict(geo_coverage="country", headline_entity="IND")
    return [
        Transform(
            spec=Spec(
                id="farms.faostat-wcad.holdings",
                title="Number of farms, by country and census",
                description="How many agricultural holdings (farms) each country counted in its census of "
                "agriculture, for every census FAO has compiled since the 1930 World Census of Agriculture round. "
                "Each country's census year is its own, so the values are not added into a world total.",
                kind="series",
                unit=_HOLDINGS,
                display=Display(decimals=0),
                scope=Scope(geography="Countries and territories, each in its own census years", basis=_BASIS),
                **common,  # type: ignore[arg-type]
            ),
            inputs=(WCAD, CATALOGUE),
            run=_runner("total"),
            module_file=here,
            validation=Validation(min_rows=500, value_range=(0.0, 1e9), monotonic_periods=False),
        ),
        Transform(
            spec=Spec(
                id="farms.faostat-wcad.holdings-by-land-size",
                title="Number of farms by land size, by country and census",
                description="How many agricultural holdings each country counted in its census of agriculture in "
                "each of FAO's land-size classes, for every census FAO has compiled since the 1930 round.",
                kind="series",
                unit=_HOLDINGS,
                display=Display(decimals=0),
                scope=Scope(geography="Countries and territories, each in its own census years", basis=_SIZE_BASIS),
                dimensions=(_SIZE,),
                headline_dims=(("land-size", "0-1"),),
                **common,  # type: ignore[arg-type]
            ),
            inputs=(WCAD, CATALOGUE),
            run=_runner(NUMBER[0]),
            module_file=here,
            validation=Validation(min_rows=4_000, value_range=(0.0, 1e9), monotonic_periods=False),
        ),
        Transform(
            spec=Spec(
                id="farms.faostat-wcad.area-by-land-size",
                title="Farmland by land size of the farm, by country and census",
                description="How much land the agricultural holdings in each of FAO's land-size classes held, in "
                "hectares, as counted in each country's census of agriculture, for every census FAO has compiled "
                "since the 1930 round.",
                kind="series",
                unit=Unit(code="ha", label="hectares", short="ha"),
                display=Display(decimals=0),
                scope=Scope(geography="Countries and territories, each in its own census years", basis=_SIZE_BASIS),
                dimensions=(_SIZE,),
                headline_dims=(("land-size", "0-1"),),
                **common,  # type: ignore[arg-type]
            ),
            inputs=(WCAD, CATALOGUE),
            run=_runner(AREA[0]),
            module_file=here,
            validation=Validation(min_rows=4_000, value_range=(0.0, 1e10), monotonic_periods=False),
        ),
    ]

"""The Global Carbon Project's fossil CO2 emissions dataset, 2025v15: fossil carbon dioxide by country, by fuel, per
person, and cumulative since 1750 with each country's share of the world's cumulative total.

Input. GCB2025v15_MtCO2_flat.csv (Zenodo record 17417124): one row per country and year 1750-2024, columns Country, ISO
3166-1 alpha-3, UN M49, Year, Total, Coal, Oil, Gas, Cement, Flaring, Other, Per Capita. Every country has all 275
years, in order. Its metadata file GCB2025v15_MtCO2_flat_metadata.json (also read) gives each column's title, unit
("millions of tonnes of CO2"; "tonnes of CO2 per capita" for Per Capita) and version ("2025v15"); the transform stops
if the columns, units or version differ from what is written here.

Entities. Countries and territories by their ISO code, through geo.resolve with the source's alias table in
envdash/geo.py (KSV is Kosovo, XIA and XIS are international aviation and shipping, and three historical rows without a
code, the Kuwaiti oil fires of 1991, the Pacific Islands Trust Territory and the Ryukyu Islands, by name). "Global"
(WLD) is the world. Any other code stops the build.

What the numbers are. Territorial emissions from fossil fuels, cement production (process emissions), gas flaring
and other carbonates, before the cement carbonation sink is subtracted (so the world total, 38,598.6 Mt CO2 in 2024,
is higher than the Global Carbon Budget's headline fossil value, which is net of that sink). National values exclude
international aviation and shipping, which are rows of their own; the world value includes them. The file's Global row
equals the sum of every other row to within 0.00001 Mt in every year, which the transform checks.

Empty cells. A cell left empty in the file is not published (there is no observation for it) and is never read as
zero. The Global row's Other column is empty for 1904-1989 although countries report other carbonates in those years
(the Global total includes them), so the world has no "other" value in those years.

Per person. The Per Capita column is published as the producer states it, never recomputed. International aviation
and shipping have no population; the file's per-person cell for them is 0 or empty, which is not a per-person value,
so they are left out (the transform stops if either ever has a non-zero value). For the Netherlands from 1900 to 1949
the file's per-person values (1,317 to 5,620 tonnes) are about a thousand times those of the neighbouring
years: Total divided by Per Capita implies a population of 5,000 to 10,000 people, against 5.1 million in 1899 and
10.1 million in 1950 from the same two columns. Those 50 years are published as null with that reason; the transform
checks that every one of them still implies fewer than 20,000 people, and stops otherwise (a corrected file then needs
a person to remove the exception).

Cumulative. For each entity, the running sum of its Total column from the first year the file gives a value, in
billion tonnes (Mt / 1,000, exact decimal arithmetic on the six-decimal values). A year whose Total cell is empty adds
nothing, which is how the producer's own Global row is built (it equals the sum of the stated values); the observation
says how many such years the sum spans. Share: an entity's cumulative total divided by the Global row's cumulative
total for the same year, times 100. Countries' shares do not add to 100 % on their own: international aviation and
shipping and the three historical rows hold the rest.

Version. The flat file carries no version itself; PINNED maps its Zenodo URL to the version and publication date, and
the metadata file must state the same version.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "gcp-fossil-co2-2025"
FLAT = Input(SOURCE, "mtco2-flat")
METADATA = Input(SOURCE, "mtco2-metadata")

HEADER = ("Country", "ISO 3166-1 alpha-3", "UN M49", "Year", "Total", "Coal", "Oil", "Gas", "Cement", "Flaring",
          "Other", "Per Capita")  # fmt: skip
MT_UNIT = "millions of tonnes of CO2"
PC_UNIT = "tonnes of CO2 per capita"
FIRST_YEAR = 1750

PINNED: dict[str, tuple[str, date]] = {
    # zenodo.org/api/records/17417124 (read 2026-10-04): version 2025v15, publication_date 2025-10-22.
    "https://zenodo.org/api/records/17417124/files/GCB2025v15_MtCO2_flat.csv/content": ("2025v15", date(2025, 10, 22)),
}

FUELS: tuple[tuple[str, str, str], ...] = (
    # (dimension value id, label, column)
    ("coal", "Coal", "Coal"),
    ("oil", "Oil", "Oil"),
    ("gas", "Gas", "Gas"),
    ("cement", "Cement production (process emissions)", "Cement"),
    ("flaring", "Gas flaring (including vented methane)", "Flaring"),
    ("other", "Other carbonates", "Other"),
)
# Titles the metadata file gives each column; checked so that a renamed or redefined column stops the build.
TITLES = {
    "Total": "Total fossil CO2 emissions",
    "Coal": "Fossil CO2 emissions from Coal",
    "Oil": "Fossil CO2 emissions from Oil",
    "Gas": "Fossil CO2 emissions from Gas",
    "Cement": "Fossil CO2 emissions from Cement (process emissions)",
    "Flaring": "Fossil CO2 emissions from Flaring (includes vented methane)",
    "Other": "Fossil CO2 emissions from Other carbonates",
    "Per Capita": "Per capita fossil CO2 emissions",
}

WORLD_CODE = "WLD"
# Entities without a population: their per-person cells are 0 or empty and are not published.
NO_POPULATION = {"INTL_AIR": "International aviation", "INTL_SEA": "International shipping"}
# Per-person cells the transform withholds, with the check that keeps the exception honest (see the module text).
PER_CAPITA_WITHHELD: dict[str, tuple[range, int]] = {"NLD": (range(1900, 1950), 20_000)}
WORLD_SUM_TOLERANCE = Decimal("0.00001")

MT_YR = Unit(code="MtCO2/yr", label="million tonnes of carbon dioxide per year", short="Mt CO₂/yr")
T_PER_PERSON = Unit(code="tCO2/person/yr", label="tonnes of carbon dioxide per person per year", short="t CO₂/person")
GT = Unit(code="GtCO2", label="billion tonnes of carbon dioxide", short="Gt CO₂")
PERCENT = Unit(code="percent", label="percent", short="%")


class GcpFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    entity: str
    country: str
    year: int
    cells: dict[str, Decimal | None]
    """Column -> value as written (None for an empty cell), for Total ... Per Capita."""


@dataclass(frozen=True)
class Table:
    version: str
    published: date
    rows: tuple[Row, ...]

    def series(self) -> Iterator[tuple[str, list[Row]]]:
        """(entity, its rows in year order), in file order."""
        start = 0
        for i in range(1, len(self.rows) + 1):
            if i == len(self.rows) or self.rows[i].entity != self.rows[start].entity:
                yield self.rows[start].entity, list(self.rows[start:i])
                start = i


def read_metadata(raw: bytes) -> str:
    """The version the metadata file states, after checking each column's title and unit."""
    fields = {f["name"]: f for f in json.loads(raw)["fields"]}
    if tuple(fields) != HEADER:
        raise GcpFormatError(f"metadata fields {list(fields)} != {list(HEADER)}")
    versions = set()
    for col, title in TITLES.items():
        f = fields[col]
        unit = PC_UNIT if col == "Per Capita" else MT_UNIT
        if f.get("title") != title or f.get("units") != unit:
            raise GcpFormatError(f"metadata for {col!r}: title {f.get('title')!r}, units {f.get('units')!r}")
        versions.add(f.get("version"))
    if len(versions) != 1:
        raise GcpFormatError(f"metadata columns carry several versions: {sorted(map(str, versions))}")
    return versions.pop()


def _cell(v: str, where: str) -> Decimal | None:
    if v == "":
        return None
    try:
        d = Decimal(v)
    except ArithmeticError:
        raise GcpFormatError(f"{where}: {v!r} is not a number") from None
    if not d.is_finite() or d < 0:
        raise GcpFormatError(f"{where}: {v!r} is not a non-negative number")
    return d


def read_flat(raw: bytes, *, entities: geo.EntityTable | None = None) -> list[Row]:
    reader = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""))
    header = tuple(next(reader))
    if header != HEADER:
        raise GcpFormatError(f"header {header} != {HEADER}")
    rows: list[Row] = []
    codes: dict[tuple[str, str], str] = {}
    for n, r in enumerate(reader, start=2):
        if len(r) != len(HEADER):
            raise GcpFormatError(f"line {n}: {len(r)} fields")
        country, iso, _, year = r[0], r[1], r[2], r[3]
        key = (country, iso)
        if key not in codes:
            codes[key] = geo.resolve(iso or country, SOURCE, entities=entities)
        cells = {col: _cell(v, f"line {n} {col}") for col, v in zip(HEADER[4:], r[4:], strict=True)}
        rows.append(Row(codes[key], country, int(year), cells))
    if len(set(codes.values())) != len(codes):
        raise GcpFormatError("two of the file's countries resolve to the same entity")
    if WORLD_CODE not in codes.values():
        raise GcpFormatError("no Global row")
    return rows


def _check_series(rows: list[Row]) -> None:
    by_entity: dict[str, list[int]] = {}
    for r in rows:
        by_entity.setdefault(r.entity, []).append(r.year)
    span = list(range(FIRST_YEAR, max(r.year for r in rows) + 1))
    order = [r.entity for r in rows]
    for e, years in by_entity.items():
        if years != span:
            raise GcpFormatError(f"{e}: years {years[0]}-{years[-1]} ({len(years)}) are not {span[0]}-{span[-1]}")
        first = order.index(e)
        if order[first : first + len(span)] != [e] * len(span):
            raise GcpFormatError(f"{e}: its rows are not contiguous")


def largest_world_residual(rows: list[Row]) -> Decimal:
    """Checks that the Global row's Total equals the sum of every other row's Total in each year."""
    world: dict[int, Decimal | None] = {}
    others: dict[int, Decimal] = {}
    for r in rows:
        if r.entity == WORLD_CODE:
            world[r.year] = r.cells["Total"]
        elif r.cells["Total"] is not None:
            others[r.year] = others.get(r.year, Decimal(0)) + r.cells["Total"]  # type: ignore[operator]
    worst = Decimal(0)
    for y, w in world.items():
        if w is None:
            raise GcpFormatError(f"the Global row has no Total for {y}")
        diff = abs(w - others.get(y, Decimal(0)))
        if diff > WORLD_SUM_TOLERANCE:
            raise GcpFormatError(f"{y}: Global {w} != sum of the other rows {others.get(y)}; the rows no longer add up")
        worst = max(worst, diff)
    return worst


def _pinned(f: InputFile) -> tuple[str, date]:
    url = str(f.snapshot.url) if f.snapshot.url else None
    if url not in PINNED:
        raise GcpFormatError(f"{url!r} is not a pinned version of the fossil CO2 dataset; add it to PINNED")
    return PINNED[url]


def load(files: dict[str, InputFile], *, entities: geo.EntityTable | None = None) -> Table:
    version, published = _pinned(files[FLAT.key])
    stated = read_metadata(files[METADATA.key].path.read_bytes())
    if stated != version:
        raise GcpFormatError(f"the metadata file says version {stated!r}; PINNED says {version!r}")
    rows = read_flat(files[FLAT.key].path.read_bytes(), entities=entities)
    _check_series(rows)
    return Table(version, published, tuple(rows))


def _period(y: int) -> str:
    return f"{y:04d}"


def total_observations(t: Table) -> list[Observation]:
    return [
        Observation(entity=r.entity, period=_period(r.year), value=float(v))
        for r in t.rows
        if (v := r.cells["Total"]) is not None
    ]


def fuel_observations(t: Table) -> list[Observation]:
    return [
        Observation(entity=r.entity, period=_period(r.year), value=float(v), dims={"fuel": fid})
        for fid, _, col in FUELS
        for r in t.rows
        if (v := r.cells[col]) is not None
    ]


def per_capita_observations(t: Table) -> list[Observation]:
    obs: list[Observation] = []
    for r in t.rows:
        v = r.cells["Per Capita"]
        if r.entity in NO_POPULATION:
            if v not in (None, Decimal(0)):
                raise GcpFormatError(f"{r.entity} {r.year}: per-person value {v} where the file has no population")
            continue
        if v is None:
            continue
        withheld = PER_CAPITA_WITHHELD.get(r.entity)
        if withheld and r.year in withheld[0]:
            total = r.cells["Total"]
            implied = None if total is None or v == 0 else total * Decimal(1_000_000) / v
            if implied is None or implied >= withheld[1]:
                raise GcpFormatError(
                    f"{r.entity} {r.year}: Total / Per Capita implies {implied} people, no longer fewer than "
                    f"{withheld[1]:,}; the per-person exception in PER_CAPITA_WITHHELD needs a person to re-check it"
                )
            obs.append(
                Observation(
                    entity=r.entity,
                    period=_period(r.year),
                    value=None,
                    missing_reason=f"The file's per-person value for this year, {v} tonnes, implies a population of "
                    f"about {implied:,.0f} people (Total divided by Per Capita), a thousandth of the population the "
                    "same columns imply for 1899 and 1950. It is not published until the producer corrects it.",
                )
            )
            continue
        obs.append(Observation(entity=r.entity, period=_period(r.year), value=float(v)))
    return obs


@dataclass(frozen=True)
class Cumulative:
    year: int
    mt: Decimal
    first_year: int
    empty_years: int


def cumulative(rows: list[Row]) -> list[Cumulative]:
    """Running sum of Total from the entity's first stated value; empty years add nothing and are counted."""
    out: list[Cumulative] = []
    acc = Decimal(0)
    first: int | None = None
    empty = 0
    for r in rows:
        v = r.cells["Total"]
        if v is None:
            if first is not None:
                empty += 1
                out.append(Cumulative(r.year, acc, first, empty))
            continue
        if first is None:
            first = r.year
        acc += v
        out.append(Cumulative(r.year, acc, first, empty))
    return out


def _span_note(c: Cumulative) -> str | None:
    if not c.empty_years:
        return None
    gap = "1 year in that span has" if c.empty_years == 1 else f"{c.empty_years} years in that span have"
    return (
        f"Sum of the file's values from {c.first_year} to {c.year}; {gap} no value in the file, which adds nothing "
        "to the sum."
    )


def cumulative_observations(t: Table) -> list[Observation]:
    obs: list[Observation] = []
    for entity, rows in t.series():
        for c in cumulative(rows):
            obs.append(Observation(entity=entity, period=_period(c.year), value=float(c.mt / 1000), note=_span_note(c)))
    return obs


def share_observations(t: Table) -> list[Observation]:
    series = dict(t.series())
    world = {c.year: c for c in cumulative(series[WORLD_CODE])}
    obs: list[Observation] = []
    for entity, rows in series.items():
        if entity == WORLD_CODE:
            continue
        for c in cumulative(rows):
            w = world[c.year]
            if w.empty_years:
                raise GcpFormatError(f"the Global row has an empty Total before {c.year}")
            obs.append(
                Observation(entity=entity, period=_period(c.year), value=float(c.mt / w.mt * 100), note=_span_note(c))
            )
    return obs


def _read_step(t: Table) -> str:
    return (
        f"Read GCB2025v15_MtCO2_flat.csv (version {t.version}): {len({r.entity for r in t.rows})} entities (countries, "
        f"territories, international aviation, international shipping, three historical entities and the world), "
        f"each {FIRST_YEAR}–{t.rows[-1].year}, in million tonnes of carbon dioxide. The metadata file's titles, units "
        "and version were checked against the columns. Producer codes were mapped to entity codes through an explicit "
        "alias table (KSV Kosovo, XIA international aviation, XIS international shipping; the Kuwaiti oil fires, the "
        "Pacific Islands (Palau) and the Ryukyu Islands by name)."
    )


EMPTY_STEP = "Cells left empty in the file are not published and are never read as zero."


def _world_step(residual: Decimal) -> str:
    return (
        "Checked that the file's Global row equals the sum of all other rows (countries, international aviation and "
        f"shipping, historical entities) in every year (largest difference {residual} Mt)."
    )


def _run_total(files: dict[str, InputFile]) -> Result:
    t = load(files)
    residual = largest_world_residual(list(t.rows))
    return Result(
        observations=total_observations(t),
        vintage=t.version,
        date_published=t.published.isoformat(),
        steps=[_read_step(t), _world_step(residual), "Published the Total column as stated.", EMPTY_STEP],
    )


def _run_fuel(files: dict[str, InputFile]) -> Result:
    t = load(files)
    return Result(
        observations=fuel_observations(t),
        vintage=t.version,
        date_published=t.published.isoformat(),
        steps=[
            _read_step(t),
            "Published the Coal, Oil, Gas, Cement, Flaring and Other columns as stated, one value of the fuel "
            "dimension each.",
            EMPTY_STEP + " The Global row's Other column is empty for 1904–1989, so the world has no 'other "
            "carbonates' value in those years, although its Total includes the other carbonates countries report.",
        ],
    )


def _run_per_capita(files: dict[str, InputFile]) -> Result:
    t = load(files)
    withheld = ", ".join(
        f"{e} {r.start}–{r.stop - 1} (Total divided by Per Capita implies fewer than {limit:,} people)"
        for e, (r, limit) in PER_CAPITA_WITHHELD.items()
    )
    return Result(
        observations=per_capita_observations(t),
        vintage=t.version,
        date_published=t.published.isoformat(),
        steps=[
            _read_step(t),
            "Published the Per Capita column as the producer states it (tonnes of carbon dioxide per person); it was "
            "not recomputed.",
            "Left out international aviation and international shipping: they have no population, and the file's "
            "per-person cell for them is 0 or empty.",
            f"Published as null, with the reason, the per-person values the file gives for {withheld}: a thousand "
            "times the values of the neighbouring years.",
            EMPTY_STEP,
        ],
    )


def _cumulative_step(t: Table) -> str:
    return (
        "For each entity, added up its Total column year by year from the first year the file gives a value "
        f"(the file starts in {FIRST_YEAR}), with exact decimal arithmetic. A year whose cell is empty adds nothing: "
        "the producer's Global row is built the same way (it equals the sum of the stated values). Observations "
        "whose sum spans such years say how many."
    )


def _run_cumulative(files: dict[str, InputFile]) -> Result:
    t = load(files)
    residual = largest_world_residual(list(t.rows))
    return Result(
        observations=cumulative_observations(t),
        vintage=t.version,
        date_published=t.published.isoformat(),
        steps=[
            _read_step(t),
            _world_step(residual),
            _cumulative_step(t),
            "Converted from million to billion tonnes (divided by 1,000).",
        ],
        changes="annual values added up into a running total since the first year with a value; converted from "
        "million to billion tonnes.",
    )


def _run_share(files: dict[str, InputFile]) -> Result:
    t = load(files)
    residual = largest_world_residual(list(t.rows))
    return Result(
        observations=share_observations(t),
        vintage=t.version,
        date_published=t.published.isoformat(),
        steps=[
            _read_step(t),
            _world_step(residual),
            _cumulative_step(t),
            "Divided each entity's cumulative total by the cumulative total of the file's Global row for the same "
            "year and multiplied by 100. International aviation, international shipping and the historical entities "
            "have shares too, so the countries' shares add up to less than 100 %.",
        ],
        changes="annual values added up into running totals and divided by the world's running total (percent).",
    )


GEOGRAPHY = (
    "Countries and territories, international aviation, international shipping, three historical entities and the world"
)
BASIS = (
    "Carbon dioxide only, from fossil fuels, cement production (process emissions), gas flaring and other carbonates, "
    "before the cement carbonation sink is subtracted (gross). National values exclude international aviation and "
    "shipping, which are separate entities; the world value includes them. Territorial (production-based) accounting."
)
SINCE_1750 = "Sum since 1750, the first year of the file"


def _scope(extra: str = "", baseline: str | None = None) -> Scope:
    return Scope(geography=GEOGRAPHY, baseline=baseline, lulucf="excluded", bunkers="excluded", basis=BASIS + extra)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (FLAT, METADATA)
    return [
        Transform(
            spec=Spec(
                id="emissions.gcp-2025.fossil-co2-by-country",
                title="Fossil carbon dioxide emissions by country",
                description="Carbon dioxide released each year since 1750 by burning coal, oil and gas, making "
                "cement, flaring gas and other industrial uses of carbonates, in each country where it was emitted. "
                "International aviation and shipping are shown on their own and counted in the world total.",
                kind="series",
                unit=MT_YR,
                display=Display(decimals=1),
                scope=_scope(),
                geo_coverage="mixed",
                headline_entity=WORLD_CODE,
            ),
            inputs=inputs,
            run=_run_total,
            module_file=here,
            validation=Validation(min_rows=24_000, value_range=(0.0, 50_000.0)),
        ),
        Transform(
            spec=Spec(
                id="emissions.gcp-2025.fossil-co2-by-fuel",
                title="Fossil carbon dioxide emissions by country and fuel",
                description="Each country's fossil carbon dioxide emissions since 1750 split by source: coal, oil, "
                "gas, cement production, gas flaring and other carbonates.",
                kind="series",
                unit=MT_YR,
                display=Display(decimals=1),
                scope=_scope(),
                geo_coverage="mixed",
                headline_entity=WORLD_CODE,
                dimensions=(
                    Dimension(
                        id="fuel",
                        label="Fuel or source",
                        values=[DimensionValue(id=i, label=label) for i, label, _ in FUELS],
                    ),
                ),
                headline_dims=(("fuel", "coal"),),
            ),
            inputs=inputs,
            run=_run_fuel,
            module_file=here,
            validation=Validation(min_rows=95_000, value_range=(0.0, 50_000.0)),
        ),
        Transform(
            spec=Spec(
                id="emissions.gcp-2025.fossil-co2-per-capita",
                title="Fossil carbon dioxide emissions per person",
                description="Each country's fossil carbon dioxide emissions in a year divided by its population, as "
                "the Global Carbon Project publishes them.",
                kind="series",
                unit=T_PER_PERSON,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Countries and territories, three historical entities and the world",
                    lulucf="excluded",
                    bunkers="excluded",
                    basis=BASIS + " Per person values are the producer's own; the world value counts international "
                    "aviation and shipping in its emissions.",
                ),
                geo_coverage="mixed",
                headline_entity=WORLD_CODE,
            ),
            inputs=inputs,
            run=_run_per_capita,
            module_file=here,
            validation=Validation(min_rows=22_000, value_range=(0.0, 1_000.0)),
        ),
        Transform(
            spec=Spec(
                id="emissions.gcp-2025.fossil-co2-cumulative",
                title="Cumulative fossil carbon dioxide emissions since 1750",
                description="All the fossil carbon dioxide each country has emitted from 1750 up to each year: the "
                "running total of its annual emissions.",
                kind="derived",
                unit=GT,
                display=Display(decimals=2),
                scope=_scope(" Running total of annual values.", baseline=SINCE_1750),
                geo_coverage="mixed",
                headline_entity=WORLD_CODE,
            ),
            inputs=inputs,
            run=_run_cumulative,
            module_file=here,
            validation=Validation(min_rows=23_000, value_range=(0.0, 2_500.0)),
        ),
        Transform(
            spec=Spec(
                id="emissions.gcp-2025.fossil-co2-cumulative-share",
                title="Share of the world's cumulative fossil carbon dioxide emissions since 1750",
                description="Each country's cumulative fossil carbon dioxide emissions since 1750 as a percentage of "
                "the world's, up to each year.",
                kind="derived",
                unit=PERCENT,
                display=Display(decimals=2),
                scope=_scope(
                    " Running totals divided by the world's running total; international aviation and shipping "
                    "hold their own shares.",
                    baseline=SINCE_1750,
                ),
                geo_coverage="mixed",
                headline_entity="USA",
            ),
            inputs=inputs,
            run=_run_share,
            module_file=here,
            validation=Validation(min_rows=23_000, value_range=(0.0, 100.0)),
        ),
    ]

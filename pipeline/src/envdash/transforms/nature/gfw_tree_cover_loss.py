"""Tree cover loss (Hansen/UMD Global Forest Change v1.13), as tabulated by country by WRI in the Global Forest Watch
(now Global Nature Watch) Data API table gadm__tcl__iso_change v20260424: all loss and loss due to fire, loss inside
humid tropical primary forest, and loss by dominant driver, by country and for the world, 2001-2025.

Inputs: the four CSV downloads of source gfw-tree-cover-loss. Each is our SQL query against WRI's table, summing
umd_tree_cover_loss__ha (and umd_tree_cover_loss_from_fires__ha) at a tree canopy cover in 2000 of at least 30 percent
(the threshold Global Forest Watch's dashboards use; the table holds one row per threshold, so leaving the filter out
would count the same loss several times). The query is in each artifact's URL. The header line of each file must be
exactly the one below, or the transform stops.

Entities. The iso column holds GADM's country codes. ISO 3166-1 codes resolve through geo.resolve; GADM's own codes
XKO (Kosovo) and ZNC (Northern Cyprus) are aliases in envdash/geo.py SOURCE_SCHEMES. GADM codes with no row in
pipeline/geo/entities.csv (LEFT_OUT: XAD, Z01, Z06, Z07) are not published as countries; their loss stays in the world
totals, and a processing step names them with their hectares. Any other unknown code stops the transform.

World. Tree cover loss and loss due to fire come from the loss-global-annual download, which sums the whole table.
The world values of primary forest loss and of loss by driver are this module's sums over every row of their file,
including the codes left out above. Checks: in every year the countries of loss-country-annual add up to the world
file exactly (loss and fire), and the eight drivers add up to the world loss to within 0.01 hectare.

Gaps. A country-year without a row has no loss recorded in WRI's table for that query; nothing is filled in for it.
Values are hectares, the shortest decimal form of each number in the file, not rounded.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "gfw-tree-cover-loss"
GLOBAL = Input(SOURCE, "loss-global-annual")
COUNTRY = Input(SOURCE, "loss-country-annual")
PRIMARY = Input(SOURCE, "loss-primary-forest-country-annual")
DRIVERS = Input(SOURCE, "loss-drivers-country-annual")

YEAR = "umd_tree_cover_loss__year"
LOSS = "umd_tree_cover_loss__ha"
FIRE = "umd_tree_cover_loss_from_fires__ha"
DRIVER = "wri_google_tree_cover_loss_drivers__driver"

HEADERS: dict[str, tuple[str, ...]] = {
    GLOBAL.key: (YEAR, LOSS, FIRE),
    COUNTRY.key: ("iso", YEAR, LOSS, FIRE),
    PRIMARY.key: ("iso", YEAR, LOSS),
    DRIVERS.key: ("iso", DRIVER, YEAR, LOSS),
}

FIRST_YEAR = 2001
TOLERANCE_HA = Decimal("0.01")
TABLE = "gadm__tcl__iso_change v20260424"
VINTAGE = f"GFC-2025-v1.13, WRI table {TABLE}"
CHANGES = (
    "Summed WRI's country table by country and year at a tree canopy cover in 2000 of at least 30 percent; world "
    "totals of primary forest loss and of loss by driver summed by Environment Dashboard."
)

# GADM codes in the table that have no row in pipeline/geo/entities.csv (seen in the 2026-10-06 snapshots).
LEFT_OUT = frozenset({"XAD", "Z01", "Z06", "Z07"})

# (dimension value, WRI's driver class as written in the file)
DRIVER_CLASSES: tuple[tuple[str, str], ...] = (
    ("permanent-agriculture", "Permanent agriculture"),
    ("hard-commodities", "Hard commodities"),
    ("shifting-cultivation", "Shifting cultivation"),
    ("logging", "Logging"),
    ("wildfire", "Wildfire"),
    ("settlements-and-infrastructure", "Settlements & Infrastructure"),
    ("other-natural-disturbances", "Other natural disturbances"),
    ("unknown", "Unknown"),
)
DRIVER_LABELS = {
    "permanent-agriculture": "Permanent agriculture",
    "hard-commodities": "Mining and energy (hard commodities)",
    "shifting-cultivation": "Shifting cultivation",
    "logging": "Logging",
    "wildfire": "Wildfire",
    "settlements-and-infrastructure": "Settlements and infrastructure",
    "other-natural-disturbances": "Other natural disturbances",
    "unknown": "Unknown",
}
_DRIVER_ID = {name: d for d, name in DRIVER_CLASSES}

PARTS: tuple[tuple[str, str], ...] = (
    ("all", "All tree cover loss"),
    ("fire", "Of which, due to fire"),
)


class GfwFormatError(ValueError):
    pass


def read_rows(raw: bytes, key: str) -> list[dict[str, str]]:
    """The rows of one download, after checking its header line."""
    text = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != HEADERS[key]:
        raise GfwFormatError(f"{key}: header {reader.fieldnames!r}, expected {list(HEADERS[key])!r}")
    rows = list(reader)
    if not rows:
        raise GfwFormatError(f"{key}: no data rows")
    return rows


def _year(r: dict[str, str], where: str, last: int | None = None) -> int:
    try:
        y = int(r[YEAR])
    except ValueError:
        raise GfwFormatError(f"{where}: year {r[YEAR]!r} is not a whole number") from None
    if y < FIRST_YEAR or (last is not None and y > last):
        raise GfwFormatError(f"{where}: year {y} outside {FIRST_YEAR}-{last}")
    return y


def _ha(r: dict[str, str], field: str, where: str) -> Decimal:
    v = r[field]
    try:
        d = Decimal(v)
    except ArithmeticError:
        raise GfwFormatError(f"{where}: {field} {v!r} is not a number") from None
    if not d.is_finite() or d < 0:
        raise GfwFormatError(f"{where}: {field} is {v!r}")
    return d


def read_global(raw: bytes) -> dict[int, tuple[Decimal, Decimal]]:
    """Year -> (loss, loss due to fire), every year from 2001 once and in order."""
    out: dict[int, tuple[Decimal, Decimal]] = {}
    for i, r in enumerate(read_rows(raw, GLOBAL.key)):
        where = f"{GLOBAL.key} row {i + 2}"
        y = _year(r, where)
        if y != FIRST_YEAR + i:
            raise GfwFormatError(f"{where}: year {y}, expected {FIRST_YEAR + i}")
        loss, fire = _ha(r, LOSS, where), _ha(r, FIRE, where)
        if fire > loss:
            raise GfwFormatError(f"{where}: loss due to fire {fire} exceeds all loss {loss}")
        out[y] = (loss, fire)
    return out


def _entity(iso: str, entities: geo.EntityTable) -> str | None:
    """Our code for a GADM code, or None for a code in LEFT_OUT."""
    if iso in LEFT_OUT:
        return None
    return geo.resolve(iso, SOURCE, entities=entities)


Key = tuple[str, str, int]
"""(entity, dimension value, year)"""


def read_country(
    raw: bytes, key: str, last: int, entities: geo.EntityTable
) -> tuple[dict[Key, Decimal], dict[str, Decimal], dict[int, Decimal]]:
    """For one country download: published values by (entity, dimension value, year); hectares left out by GADM
    code; and the sum of every row by year (the world)."""
    values: dict[Key, Decimal] = {}
    left: dict[str, Decimal] = defaultdict(Decimal)
    world: dict[int, Decimal] = defaultdict(Decimal)
    for i, r in enumerate(read_rows(raw, key)):
        where = f"{key} row {i + 2} ({r['iso']})"
        y = _year(r, where, last)
        loss = _ha(r, LOSS, where)
        world[y] += loss
        entity = _entity(r["iso"], entities)
        if entity is None:
            left[r["iso"]] += loss
            continue
        parts: list[tuple[str, Decimal]]
        if key == DRIVERS.key:
            if r[DRIVER] not in _DRIVER_ID:
                raise GfwFormatError(f"{where}: driver class {r[DRIVER]!r} is not one of WRI's eight")
            parts = [(_DRIVER_ID[r[DRIVER]], loss)]
        elif key == COUNTRY.key:
            fire = _ha(r, FIRE, where)
            if fire > loss:
                raise GfwFormatError(f"{where}: loss due to fire {fire} exceeds all loss {loss}")
            parts = [("all", loss), ("fire", fire)]
        else:
            parts = [("", loss)]
        for dim, v in parts:
            k = (entity, dim, y)
            if k in values:
                raise GfwFormatError(f"{where}: a second row for {entity} {dim or ''} {y}".replace("  ", " "))
            values[k] = v
    return values, dict(left), dict(world)


def _obs(values: dict[Key, Decimal], dim_id: str | None, order: list[str]) -> list[Observation]:
    keys = sorted(values, key=lambda k: (k[0] != "WLD", k[0], order.index(k[1]), k[2]))
    return [
        Observation(
            entity=e,
            period=f"{y:04d}",
            value=float(values[(e, d, y)]),
            dims={dim_id: d} if dim_id else {},
        )
        for e, d, y in keys
    ]


def _left_out_step(left: dict[str, Decimal]) -> str:
    named = "; ".join(f"{c} {left[c]:,.0f} ha" for c in sorted(left))
    return (
        "Not published as countries: GADM codes with no entity in our table (" + named + ", all years together). "
        "Their loss is included in the world totals."
    )


def _base_steps(files: dict[str, InputFile], key: str) -> list[str]:
    f = files[key]
    return [
        f"Read {key.split('/')[1]}: WRI's table {TABLE} queried through the Global Forest Watch Data API with the SQL "
        f"in the file's URL ({f.snapshot.url}), at a tree canopy cover in 2000 of at least 30 percent. Hectares as "
        "in the file, not rounded.",
        "A country and year with no row in the file has no loss recorded for it; nothing is filled in.",
    ]


def _run_loss(files: dict[str, InputFile]) -> Result:
    world = read_global(files[GLOBAL.key].path.read_bytes())
    last = max(world)
    values, left, sums = read_country(files[COUNTRY.key].path.read_bytes(), COUNTRY.key, last, geo.table())
    fire_sum: dict[int, Decimal] = defaultdict(Decimal)
    for (_, d, y), v in values.items():
        if d == "fire":
            fire_sum[y] += v
    # Fire in the left-out codes is not read separately: re-read their rows for the check.
    for r in read_rows(files[COUNTRY.key].path.read_bytes(), COUNTRY.key):
        if r["iso"] in LEFT_OUT:
            fire_sum[int(r[YEAR])] += Decimal(r[FIRE])
    for y, (loss, fire) in world.items():
        if sums.get(y, Decimal(0)) != loss or fire_sum.get(y, Decimal(0)) != fire:
            raise GfwFormatError(
                f"{y}: countries add up to {sums.get(y)} ha loss and {fire_sum.get(y)} ha from fire; the world file "
                f"says {loss} and {fire}"
            )
    for y, (loss, fire) in world.items():
        values[("WLD", "all", y)] = loss
        values[("WLD", "fire", y)] = fire
    steps = [
        *_base_steps(files, COUNTRY.key),
        f"World: read loss-global-annual (the same query without the country grouping), {FIRST_YEAR}–{last}. Checked "
        "that the countries, with the codes left out below, add up to it exactly in every year, for all loss and for "
        "loss due to fire.",
        _left_out_step(left),
    ]
    return Result(
        observations=_obs(values, "part", [p for p, _ in PARTS]),
        vintage=VINTAGE,
        year=str(last + 1),
        steps=steps,
        changes=CHANGES,
    )


def _run_world_sum(key: str, dim_id: str | None, order: list[str]):
    def run(files: dict[str, InputFile]) -> Result:
        world = read_global(files[GLOBAL.key].path.read_bytes())
        last = max(world)
        values, left, _ = read_country(files[key].path.read_bytes(), key, last, geo.table())
        world_sum: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
        for r in read_rows(files[key].path.read_bytes(), key):
            d = _DRIVER_ID[r[DRIVER]] if dim_id == "driver" else ""
            world_sum[(d, int(r[YEAR]))] += Decimal(r[LOSS])
        steps = _base_steps(files, key)
        if dim_id == "driver":
            for y, (loss, _) in world.items():
                total = sum((v for (_, yy), v in world_sum.items() if yy == y), Decimal(0))
                if abs(total - loss) > TOLERANCE_HA:
                    raise GfwFormatError(f"{y}: the drivers add up to {total} ha; the world file says {loss}")
            steps.append(
                'Driver classes as WRI names them; "Hard commodities" is labelled "Mining and energy (hard '
                'commodities)" and "Settlements & Infrastructure" "Settlements and infrastructure". Each 1 km '
                "cell's loss is assigned to its one dominant driver (WRI/Google DeepMind, Sims et al. 2025)."
            )
        steps.append(
            "World: the sum of every row of the file by year"
            + (" and driver" if dim_id == "driver" else "")
            + ", including the codes left out below."
            + (
                f" Checked that the drivers add up to loss-global-annual in every year, to within {TOLERANCE_HA} ha."
                if dim_id == "driver"
                else ""
            )
        )
        steps.append(_left_out_step(left))
        for (d, y), v in world_sum.items():
            values[("WLD", d, y)] = v
        return Result(
            observations=_obs(values, dim_id, order),
            vintage=VINTAGE,
            steps=steps,
            changes=CHANGES,
        )

    return run


_UNIT = Unit(code="ha", label="hectares", short="ha")
_GEOGRAPHY = (
    "Countries and territories (GADM's country codes, mapped to ISO 3166-1) and the world, which also includes "
    "areas GADM codes separately (XAD, Z01, Z06, Z07)."
)
_BASIS = (
    "Tree cover loss: stand-replacing disturbance, or the complete removal of tree cover canopy, of vegetation taller "
    "than 5 m, mapped each year from Landsat at 30 m (Hansen/UMD, Global Forest Change v1.13), where tree canopy "
    "cover was at least 30 percent in 2000. Loss is not deforestation: it includes plantation harvest, fire and "
    "natural disturbance, and regrowth is not subtracted. Method changes from 2011 and 2015 make early and late years "
    "less comparable."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    order_drivers = [d for d, _ in DRIVER_CLASSES]
    return [
        Transform(
            spec=Spec(
                id="forest.gfw.tree-cover-loss",
                title="Tree cover lost each year, and the part due to fire",
                description="Hectares of tree cover lost each year since 2001, worldwide and in each country, and "
                "how much of it was lost to fire, mapped from Landsat satellites by the University of Maryland and "
                "tabulated by World Resources Institute for Global Forest Watch.",
                kind="series",
                unit=_UNIT,
                display=Display(decimals=0),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis=_BASIS + " Loss due to fire: UMD/GLAD (Tyukavina et al. 2022), a part of all loss.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
                dimensions=(
                    Dimension(id="part", label="Part", values=[DimensionValue(id=p, label=lbl) for p, lbl in PARTS]),
                ),
                headline_dims=(("part", "all"),),
            ),
            inputs=(GLOBAL, COUNTRY),
            run=_run_loss,
            module_file=here,
            validation=Validation(min_rows=8_000, value_range=(0.0, 1.0e8)),
        ),
        Transform(
            spec=Spec(
                id="forest.gfw.primary-forest-loss",
                title="Humid tropical primary forest lost each year",
                description="Hectares of tree cover lost each year since 2001 inside the humid tropical primary "
                "forest that stood in 2001: mature natural forest that had not been cleared and regrown in recent "
                "history, mapped by the University of Maryland.",
                kind="series",
                unit=_UNIT,
                display=Display(decimals=0),
                scope=Scope(
                    geography=_GEOGRAPHY + " Only countries with humid tropical primary forest have rows.",
                    basis=_BASIS + " Primary forest: the 2001 extent of humid tropical primary forest (Turubanova "
                    "et al. 2018); loss outside the humid tropics is not counted.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=(GLOBAL, PRIMARY),
            run=_run_world_sum(PRIMARY.key, None, [""]),
            module_file=here,
            validation=Validation(min_rows=2_000, value_range=(0.0, 1.0e8)),
        ),
        Transform(
            spec=Spec(
                id="forest.gfw.tree-cover-loss-by-driver",
                title="Tree cover lost each year, by what drove it",
                description="Hectares of tree cover lost each year since 2001, worldwide and in each country, split "
                "by the dominant driver of loss in each square kilometre: permanent agriculture, mining and energy, "
                "shifting cultivation, logging, wildfire, settlements and infrastructure, other natural "
                "disturbances, or unknown (WRI and Google DeepMind).",
                kind="series",
                unit=_UNIT,
                display=Display(decimals=0),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis=_BASIS + " Drivers: the dominant driver of loss in each 1 km cell, 2001–2025, from a "
                    "model trained on labelled samples (WRI/Google DeepMind, Sims et al. 2025). WRI counts "
                    "permanent agriculture, hard commodities and settlements and infrastructure as permanent "
                    "conversion to another land use; the other drivers are usually followed by regrowth.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="driver",
                        label="Driver",
                        values=[DimensionValue(id=d, label=DRIVER_LABELS[d]) for d in order_drivers],
                    ),
                ),
                headline_dims=(("driver", "permanent-agriculture"),),
            ),
            inputs=(GLOBAL, DRIVERS),
            run=_run_world_sum(DRIVERS.key, "driver", order_drivers),
            module_file=here,
            validation=Validation(min_rows=25_000, value_range=(0.0, 1.0e8)),
        ),
    ]

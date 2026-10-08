"""Ember yearly electricity data: the world's electricity demand, in terawatt-hours and as average power in terawatts.

Input: release_generation_yearly_global.csv and Ember's methodology PDF (ember-yearly), read with the functions of
envdash.transforms.energy.ember_yearly (same columns check, same vintage, same methodology sentences).

Values. Area 'World', Electricity source 'Demand' (an aggregated row), column 'Generation (TWh)', one value per year,
published as printed. The file has no World net imports row, and the build checks that World demand equals World
total generation in every year (plus World net imports, if Ember ever adds that row), to within the rounding of the
printed values, so the value is the world's electricity generation counted as demand.

Partly estimated years, as in ember_yearly: a World year is preliminary, with a note giving the count, whenever the
file has no Demand for that year for a country or economy that has Demand for an earlier year.

Average power. Each year's terawatt-hours are divided by the hours in that calendar year (8,760, or 8,784 in a leap
year; envdash.power) to give terawatts, in exact decimal arithmetic. Ember labels its values by calendar year.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash import power
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import InputFile, Result, Spec, Transform, Validation
from envdash.transforms.energy import ember_yearly as ey

SOURCE = ey.SOURCE
GENERATION, METHODOLOGY = ey.GENERATION, ey.METHODOLOGY
DEMAND = "Demand"


class EmberDemandError(ValueError):
    pass


def world_demand(df: pl.DataFrame) -> dict[str, Decimal]:
    """year -> World demand (TWh), checked against World total generation plus any World net imports."""
    w = df.filter((pl.col("Area") == ey.WORLD) & (pl.col("Area type") == "Region"))
    by_year: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in w.iter_rows(named=True):
        src = r["Electricity source"]
        if src in by_year[r["Year"]]:
            raise EmberDemandError(f"World {r['Year']} has two rows for {src!r}")
        by_year[r["Year"]][src] = r
    out: dict[str, Decimal] = {}
    for year in sorted(by_year, key=int):
        rows = by_year[year]
        d, g = rows.get(DEMAND), rows.get("Total generation")
        if d is None or g is None or d["Is aggregated source"] != "True":
            raise EmberDemandError(f"World {year}: no aggregated Demand row, or no Total generation row")
        demand, gen = ey._dec(d[ey.GEN]), ey._dec(g[ey.GEN])
        if demand is None or gen is None:
            raise EmberDemandError(f"World {year}: Demand or Total generation is empty")
        parts = [gen]
        imports = rows.get("Net imports")
        if imports is not None and ey._dec(imports[ey.GEN]) is not None:
            parts.append(ey._dec(imports[ey.GEN]))  # type: ignore[arg-type]
        if abs(demand - sum(parts, Decimal(0))) > ey._half_unit(demand, *parts):
            raise EmberDemandError(f"World {year}: Demand {demand} TWh is not generation plus net imports {parts}")
        out[year] = demand
    return out


def _status(year: str, gaps: dict[str, tuple[int, list[str]]]) -> tuple[str, str | None]:
    earlier, missing = gaps[year]
    if not missing:
        return "final", None
    return "preliminary", (
        f"Partly Ember's estimate: the file has no {year} demand for {len(missing)} of the {earlier} countries and "
        "economies with demand for an earlier year, and Ember's methodology says it estimates a country's missing "
        "years from its historical trends of demand and generation by source."
    )


def demand_observations(df: pl.DataFrame) -> list[Observation]:
    gaps = ey.country_gaps(df, DEMAND)
    obs = []
    for year, v in world_demand(df).items():
        status, note = _status(year, gaps)
        obs.append(Observation(entity="WLD", period=year, value=float(v), status=status, note=note))  # type: ignore[arg-type]
    return obs


def power_observations(df: pl.DataFrame) -> list[Observation]:
    gaps = ey.country_gaps(df, DEMAND)
    obs = []
    for year, v in world_demand(df).items():
        status, note = _status(year, gaps)
        tw = power.average_power(v, power.year_hours(int(year)))
        obs.append(Observation(entity="WLD", period=year, value=float(tw), status=status, note=note))  # type: ignore[arg-type]
    return obs


def _steps(r: ey._Read, years: list[str]) -> list[str]:
    gaps = ey.country_gaps(r.df, DEMAND)
    prelim = [y for y in years if gaps[y][1]]
    pages = ", ".join(str(p) for p in sorted(set(r.pages.values())))
    return [
        f"Read release_generation_yearly_global.csv, last modified by Ember on {r.vintage} (Ember gives no version "
        "label, so that date is the vintage), and kept Area 'World', Electricity source 'Demand', column "
        "'Generation (TWh)'.",
        "Checked that World demand equals World total generation (the world has no net imports) in every year, to "
        "within the rounding of the printed values.",
        "Marked a year preliminary, with a note giving the count, when the file has no Demand for that year for a "
        "country or economy that has it for an earlier year; Ember's data methodology (PDF last modified "
        f"{r.methodology_date}, sha256 {r.methodology_sha256[:12]}…; both sentences found on pages {pages}) says it "
        "estimates the latest annual values from monthly data and a country's missing years from historical trends. "
        f"Preliminary years in this vintage: {', '.join(prelim) if prelim else 'none'}.",
    ]


def _run_demand(files: dict[str, InputFile]) -> Result:
    r = ey._read(files)
    obs = demand_observations(r.df)
    return Result(
        observations=obs,
        vintage=r.vintage,
        date_published=r.vintage,
        steps=[*_steps(r, [o.period for o in obs if o.period]), "Published World demand as printed."],
    )


def _run_power(files: dict[str, InputFile]) -> Result:
    r = ey._read(files)
    obs = power_observations(r.df)
    return Result(
        observations=obs,
        vintage=r.vintage,
        date_published=r.vintage,
        steps=[
            *_steps(r, [o.period for o in obs if o.period]),
            "Unit conversion to average power: divided each year's World demand in terawatt-hours by the hours in "
            "that calendar year (8,760, or 8,784 in a leap year), giving terawatts (TWh / h = TW), in exact decimal "
            "arithmetic. The result is the constant power that would deliver the same electricity over the year, not "
            "the world's peak demand.",
        ],
        changes="world electricity demand divided by the hours in each year to give average power in terawatts.",
    )


BASIS = (
    "Electricity demand as Ember publishes it for the world, which equals the world's total electricity generation "
    "in every year of the file (checked at each build). Ember reports generation as gross generation where it can. "
    "The latest years are partly Ember's estimates (marked preliminary)."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (GENERATION, METHODOLOGY)
    return [
        Transform(
            spec=Spec(
                id="electricity-demand.ember.world",
                title="World electricity demand",
                description="Electricity the world used each year since 2000, in terawatt-hours, as published by "
                "Ember.",
                kind="series",
                unit=Unit(code="TWh", label="terawatt-hours per year", short="TWh"),
                display=Display(decimals=0),
                scope=Scope(geography="World", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_run_demand,
            module_file=here,
            validation=Validation(min_rows=26, value_range=(10_000.0, 100_000.0)),
            key_files=(Path(ey.__file__),),
        ),
        Transform(
            spec=Spec(
                id="power-scale.ember.world-electricity",
                title="Average electric power of the world",
                description="The electricity the world used each year since 2000, expressed as average power in "
                "terawatts: the year's terawatt-hours spread evenly over its hours. From Ember's yearly electricity "
                "data.",
                kind="derived",
                unit=Unit(code="TW", label="terawatts (average over the year)", short="TW"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="World",
                    basis=BASIS + " Average power is the annual energy divided by the hours in the year, not the "
                    "peak demand.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_run_power,
            module_file=here,
            validation=Validation(min_rows=26, value_range=(1.0, 10.0)),
            key_files=(Path(ey.__file__), Path(power.__file__)),
        ),
    ]

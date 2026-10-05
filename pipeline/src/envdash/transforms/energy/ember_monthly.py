"""Ember monthly electricity data: the world's monthly generation mix, clean share and fossil generation change.

Input: release_generation_monthly_global.csv (registry entry ember-monthly): one row per area, month and electricity
source, with generation, share, emissions and intensity as columns, and year-on-year changes for each.

Vintage. As for the yearly file, Ember prints no version label, so the vintage is the date of the file's HTTP
Last-Modified header (e.g. "2026-09-18"); a snapshot without it stops the build.

Values, all for Area "World" (Area type "Region"), published as printed:
- mix: "Share of generation (%)" of the nine non-aggregated sources (Solar, Wind, Hydro, Bioenergy, Other
  renewables, Nuclear, Coal, Gas, Other fossil);
- clean share: "Share of generation (%)" of the aggregated source "Clean";
- fossil change: "Generation YoY change (%)" of the aggregated source "Fossil", the change in fossil generation from
  the same month a year earlier. The file's first World month is January 2019, so this series starts in January
  2020.
Checks, or the build stops (rounding tolerance only, as in ember_yearly.py): for every month the nine shares add up
to 100, Clean is Renewables plus Nuclear, Renewables is the five renewable sources and the Clean share is Clean over
Total generation (ember_yearly.check_definitions); and for Fossil, "Generation YoY change (TWh)" equals this month's
generation minus the same month's a year earlier in the file, and the percentage equals that change over the earlier
month's generation. Generation is gross where Ember has it, net imports excluded.

Status. The World monthly total is Ember's estimate built from the countries it has monthly data for, and recent
months cover fewer of them. Every month carries a note with the number of countries and economies that have Total
generation in the file for that month. A month is preliminary when a country with Total generation in an earlier
month has none in that month (the same rule as ember_yearly.py applies to years). In the file of 18 September 2026
Ukraine stops in September 2022, so every month from October 2022 is preliminary.

Publisher check: none. Ember's monthly statements (Insights pages) are not tied to a file date we hold.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.energy import ember_yearly as ey
from envdash.transforms.energy.ember_yearly import (
    COUNTRY,
    GEN,
    PERCENT,
    SHARE,
    SOURCES,
    WORLD,
    EmberFormatError,
    WorldYear,
    _dec,
    _half_unit,
    check_definitions,
    vintage_of,
)

SOURCE = "ember-monthly"
MONTHLY = Input(SOURCE, "generation-monthly-global")
COLUMNS = [
    "Area",
    "ISO 3 code",
    "Date",
    "Area type",
    "Electricity source",
    "Is aggregated source",
    "Generation (TWh)",
    "Generation YoY change (TWh)",
    "Generation YoY change (%)",
    "Share of generation (%)",
    "Share of generation YoY change (% points)",
    "Emissions (MtCO2e)",
    "Emissions YoY change (MtCO2e)",
    "Emissions YoY change (%)",
    "Share of emissions (%)",
    "Emissions intensity (gCO2e/kWh)",
    "Continent",
    "Ember region",
    "EU member",
    "OECD member",
    "G20 member",
    "G7 member",
    "ASEAN member",
]
YOY_TWH = "Generation YoY change (TWh)"
YOY_PCT = "Generation YoY change (%)"


def read_table(raw: bytes) -> pl.DataFrame:
    df = pl.read_csv(raw, infer_schema=False)
    if df.columns != COLUMNS:
        raise EmberFormatError(f"columns {df.columns} != expected {COLUMNS}")
    bad = df.filter(~pl.col("Date").str.contains(r"^\d{4}-\d{2}-01$"))
    if bad.height:
        raise EmberFormatError(f"Date {bad['Date'][0]!r} is not the first day of a month")
    return df


def _month(date: str) -> str:
    return date[:7]


def _year_before(month: str) -> str:
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


@dataclass(frozen=True)
class WorldMonth:
    month: str
    """YYYY-MM."""
    rows: dict[str, dict]


def world_months(df: pl.DataFrame) -> list[WorldMonth]:
    w = df.filter((pl.col("Area") == WORLD) & (pl.col("Area type") == "Region"))
    if w.height == 0:
        raise EmberFormatError("no rows for Area 'World'")
    by: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in w.iter_rows(named=True):
        m = _month(r["Date"])
        if r["Electricity source"] in by[m]:
            raise EmberFormatError(f"World {m} has two rows for {r['Electricity source']!r}")
        by[m][r["Electricity source"]] = r
    out = []
    for m in sorted(by):
        rows = by[m]
        base = {s for s, r in rows.items() if r["Is aggregated source"] == "False"}
        if base != set(SOURCES):
            raise EmberFormatError(f"World {m}: non-aggregated sources {sorted(base)} != {sorted(SOURCES)}")
        for agg in ("Renewables", "Clean", "Fossil", "Total generation"):
            if agg not in rows or rows[agg]["Is aggregated source"] != "True":
                raise EmberFormatError(f"World {m}: no aggregated row {agg!r}")
        check_definitions(
            WorldYear(
                year=m,
                share={s: _dec(r[SHARE]) for s, r in rows.items()},
                generation={s: _dec(r[GEN]) for s, r in rows.items()},
            )
        )
        out.append(WorldMonth(m, rows))
    return out


def country_coverage(df: pl.DataFrame) -> dict[str, tuple[int, int, list[str]]]:
    """month -> (countries with Total generation in that month, countries with it in an earlier month, those of
    them without it in this month)."""
    t = df.filter(
        (pl.col("Area type") == COUNTRY)
        & (pl.col("Electricity source") == "Total generation")
        & pl.col(GEN).is_not_null()
    )
    months_of: dict[str, set[str]] = defaultdict(set)
    for area, date in t.select("Area", "Date").iter_rows():
        months_of[area].add(_month(date))
    out: dict[str, tuple[int, int, list[str]]] = {}
    for m in sorted({_month(d) for d in df["Date"].unique()}):
        have = sum(1 for ms in months_of.values() if m in ms)
        earlier = [a for a, ms in months_of.items() if min(ms) < m]
        missing = sorted(a for a in earlier if m not in months_of[a])
        out[m] = (have, len(earlier), missing)
    return out


def _status(month: str, cov: dict[str, tuple[int, int, list[str]]]) -> tuple[str, str]:
    have, earlier, missing = cov[month]
    note = f"Ember's World estimate for this month; the file has Total generation for {have} countries and economies."
    if missing:
        return "preliminary", (
            f"{note} {len(missing)} of the {earlier} with generation for an earlier month have none for this month, "
            "so their part of the World total is estimated."
        )
    return "final", note


def check_fossil_change(months: list[WorldMonth]) -> None:
    gen = {wm.month: _dec(wm.rows["Fossil"][GEN]) for wm in months}
    for wm in months:
        r = wm.rows["Fossil"]
        d_twh, d_pct, now = _dec(r[YOY_TWH]), _dec(r[YOY_PCT]), _dec(r[GEN])
        before = gen.get(_year_before(wm.month))
        if before is None:
            if d_twh is not None or d_pct is not None:
                raise EmberFormatError(f"World {wm.month}: a Fossil change with no month a year earlier in the file")
            continue
        if d_twh is None or d_pct is None or now is None:
            raise EmberFormatError(f"World {wm.month}: no Fossil change although {_year_before(wm.month)} is there")
        if abs(d_twh - (now - before)) > _half_unit(d_twh, now, before):
            raise EmberFormatError(f"World {wm.month}: Fossil change {d_twh} TWh is not {now} - {before}")
        tol = _half_unit(d_pct) + Decimal(100) * (
            _half_unit(d_twh) / before + abs(d_twh) * _half_unit(before) / before**2
        )
        if abs(d_pct - d_twh / before * 100) > tol:
            raise EmberFormatError(f"World {wm.month}: Fossil change {d_pct}% is not {d_twh} / {before}")


# --- observations -------------------------------------------------------------------------------------------------


def mix_observations(df: pl.DataFrame) -> list[Observation]:
    months, cov = world_months(df), country_coverage(df)
    obs = []
    for label, (dim_id, _) in SOURCES.items():
        for wm in months:
            status, note = _status(wm.month, cov)
            v = _dec(wm.rows[label][SHARE])
            obs.append(
                Observation(
                    entity="WLD",
                    period=wm.month,
                    value=None if v is None else float(v),
                    missing_reason=None if v is not None else f"Ember's file has no share for {label} in {wm.month}.",
                    status=status,  # type: ignore[arg-type]
                    note=note,
                    dims={"source": dim_id},
                )
            )
    return obs


def clean_observations(df: pl.DataFrame) -> list[Observation]:
    months, cov = world_months(df), country_coverage(df)
    obs = []
    for wm in months:
        status, note = _status(wm.month, cov)
        v = _dec(wm.rows["Clean"][SHARE])
        assert v is not None  # check_definitions requires it
        obs.append(Observation(entity="WLD", period=wm.month, value=float(v), status=status, note=note))  # type: ignore[arg-type]
    return obs


def fossil_change_observations(df: pl.DataFrame) -> list[Observation]:
    months, cov = world_months(df), country_coverage(df)
    check_fossil_change(months)
    obs = []
    for wm in months:
        v = _dec(wm.rows["Fossil"][YOY_PCT])
        if v is None:
            continue  # no month a year earlier in the file (check_fossil_change allows this case only)
        status, note = _status(wm.month, cov)
        obs.append(Observation(entity="WLD", period=wm.month, value=float(v), status=status, note=note))  # type: ignore[arg-type]
    return obs


# --- transforms ---------------------------------------------------------------------------------------------------


def _runner(compute, last_steps: list[str]):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[MONTHLY.key]
        df = read_table(f.path.read_bytes())
        vintage = vintage_of(f.snapshot.last_modified)
        obs = compute(df)
        cov = country_coverage(df)
        months = sorted({o.period for o in obs})
        prelim = [m for m in months if cov[m][2]]
        return Result(
            observations=obs,
            vintage=vintage,
            date_published=vintage,
            steps=[
                f"Read release_generation_monthly_global.csv, last modified by Ember on {vintage} (Ember gives no "
                "version label, so that date is the vintage), and kept the rows for Area 'World', "
                f"{months[0]} to {months[-1]}.",
                "Checked that every month's shares mean what is published: the nine non-aggregated sources add up to "
                "100%, Clean generation is Renewables plus Nuclear, Renewables is the five renewable sources, and the "
                "Clean share is Clean over Total generation, each to within the rounding of the printed values.",
                "Noted on each month how many countries and economies have Total generation in the file for it "
                f"(from {cov[months[0]][0]} in {months[0]} to {cov[months[-1]][0]} in {months[-1]}), and marked a "
                "month preliminary when a country with generation for an earlier month has none for it, because the "
                "World total then includes Ember's estimate for that country. "
                + (
                    f"Preliminary months in this vintage: {len(prelim)}, the first {prelim[0]} and the last "
                    f"{prelim[-1]}."
                    if prelim
                    else "No month is preliminary in this vintage."
                ),
                *last_steps,
            ],
        )

    return run


BASIS = (
    "Share of electricity generation in the month, not of consumption: net imports are not included. The World "
    "total is Ember's estimate built from the countries with monthly data; values are revised as data arrive."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    keys = (Path(ey.__file__),)
    return [
        Transform(
            spec=Spec(
                id="electricity.ember.monthly-mix-world",
                title="World electricity generation by source, monthly",
                description="Share of the world's electricity generation from each source (solar, wind, hydro, "
                "bioenergy, other renewables, nuclear, coal, gas and other fossil fuels) in each month since "
                "January 2019, as estimated by Ember.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(geography="World", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="source",
                        label="Electricity source",
                        values=[DimensionValue(id=i, label=lab) for i, lab in SOURCES.values()],
                    ),
                ),
                headline_dims=(("source", "solar"),),
            ),
            inputs=(MONTHLY,),
            run=_runner(
                mix_observations,
                ["Published Ember's 'Share of generation (%)' for each of the nine sources as printed."],
            ),
            module_file=here,
            validation=Validation(min_rows=9 * 84, value_range=(0.0, 100.0)),
            key_files=keys,
        ),
        Transform(
            spec=Spec(
                id="electricity.ember.monthly-clean-share-world",
                title="Share of world electricity from clean sources, monthly",
                description="Share of the world's electricity generation from renewables and nuclear power together "
                "in each month since January 2019, as estimated by Ember.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(geography="World", basis=BASIS + " Clean means renewables plus nuclear."),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(MONTHLY,),
            run=_runner(
                clean_observations,
                [
                    "Published Ember's 'Share of generation (%)' of its aggregated source 'Clean' (renewables plus "
                    "nuclear) as printed."
                ],
            ),
            module_file=here,
            validation=Validation(min_rows=84, value_range=(0.0, 100.0)),
            key_files=keys,
        ),
        Transform(
            spec=Spec(
                id="electricity.ember.monthly-fossil-change-world",
                title="Change in world fossil-fuel electricity from a year earlier, monthly",
                description="How much more or less electricity the world generated from coal, gas and other fossil "
                "fuels in each month than in the same month a year earlier, in percent, since January 2020, as "
                "estimated by Ember.",
                kind="series",
                unit=Unit(
                    code="percent-change",
                    label="percent change from the same month a year earlier",
                    short="%",
                ),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    basis="Ember's aggregated source 'Fossil' (coal, gas and other fossil fuels), generation in the "
                    "month compared with the same month of the previous year. The World total is Ember's estimate "
                    "built from the countries with monthly data; values are revised as data arrive.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(MONTHLY,),
            run=_runner(
                fossil_change_observations,
                [
                    "Checked that the Fossil row's 'Generation YoY change (TWh)' is this month's generation minus the "
                    "same month's a year earlier in the file, and that 'Generation YoY change (%)' is that change over "
                    "the earlier month, to within the rounding of the printed values.",
                    "Published Ember's 'Generation YoY change (%)' of its aggregated source 'Fossil' as printed.",
                ],
            ),
            module_file=here,
            validation=Validation(min_rows=72, value_range=(-30.0, 30.0)),
            key_files=keys,
        ),
    ]

"""Ember yearly electricity data by country: generation mix, clean share and lifecycle carbon intensity.

Input: release_generation_yearly_global.csv and Ember's data methodology PDF (registry entry ember-yearly), the same
two files as ember_yearly.py, whose reading and checking functions this module reuses (that file is part of the build
key of every indicator here, through key_files).

Entities. The World (Area "World", Area type "Region") and every row of Area type "Country or economy", by its
"ISO 3 code" resolved with envdash.geo (column iso3). Ember's other regions (continents, EU, OECD, G20 and so on) are
not published. ISO_ALIASES and NOT_IN_CROSSWALK below are the only exceptions, each declared from the file of
22 September 2026; any other code that is not in pipeline/geo/entities.csv stops the build.

Years. Ember's methodology says "We provide data for 215 countries from 2000" (checked in the PDF at every build).
The file also has rows from 1985 to 1999 for some countries, and they are partial: Germany 1985-1989 has only a
Gas row, so its "share" of gas is 100%. Only years from 2000 are published, which is also where the World series
starts.

Values, each published as printed, never recomputed:
- mix: "Share of generation (%)" of each of the nine non-aggregated sources (Solar, Wind, Hydro, Bioenergy, Other
  renewables, Nuclear, Coal, Gas, Other fossil). A source with no row for a country and year has no observation
  (nothing is filled in; the shares of the rows that are there must add up to 100, see below). Net imports is not a
  source of generation and is not published.
- clean share: "Share of generation (%)" of the aggregated source "Clean".
- carbon intensity: "Emissions intensity (gCO2e/kWh)" of the aggregated source "Total generation". Ember labels its
  emissions lifecycle CO2-equivalent; the methodology sentences that say what that means are checked at every build.

Checks (each to within the rounding of the printed values, as in ember_yearly.py), for every country-year published,
or the build stops:
- the shares of the non-aggregated generating sources present add up to 100;
- Clean generation equals Renewables plus Nuclear (when a Nuclear row exists), and the Clean share equals Clean over
  Total generation;
- the intensity equals Emissions (MtCO2e) over Generation (TWh) of Total generation, times 1,000.

Negative generation. In the file of 22 September 2026 Ember gives negative generation for a source in a few
country-years of 2025 (Costa Rica, Other fossil, -1.15 TWh, which makes its Clean share 109.863% and its intensity
-37.907 gCO2e/kWh). The methodology says the latest year is projected "by applying absolute changes by fuel from
available annualised monthly data to historical annual values", which is how a negative value can arise. Shares of a
mix with a negative member, and an intensity built on it, do not describe a generation mix, so for such a
country-year no share, clean share or intensity is published: each is a null value whose missing_reason quotes the
negative row. Nothing is substituted.

Status. The World follows ember_yearly.py exactly (a year is preliminary when the file has no Total generation for a
country that has it for an earlier year), so the World values here equal electricity.ember.mix-world and
clean-share-world. A country's values for the file's latest year are preliminary: the file has no estimate flag, and
the methodology says that "for the most recent years" Ember estimates annual generation from monthly data. Earlier
years are final.

Publisher check. None for this vintage (see ember_yearly.py: Ember's statements on 2025 were made for earlier files).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash import geo, textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import InputFile, Result, Spec, Transform, Validation
from envdash.transforms.energy import ember_yearly as ey
from envdash.transforms.energy.ember_yearly import (
    COUNTRY,
    GEN,
    GENERATION,
    METHODOLOGY,
    PERCENT,
    SHARE,
    SOURCES,
    WORLD,
    EmberFormatError,
    _dec,
    _half_unit,
    read_table,
    vintage_of,
)

EMISSIONS = "Emissions (MtCO2e)"
INTENSITY = "Emissions intensity (gCO2e/kWh)"
FIRST_YEAR = 2000

# Ember's "ISO 3 code" -> our entity code, where the two differ (file of 22 September 2026).
ISO_ALIASES = {"XKX": "KOS"}  # Kosovo: Ember uses the user-assigned code XKX; entities.csv uses Natural Earth's KOS.
# Areas with no row in pipeline/geo/entities.csv (Natural Earth's 1:50m layers draw them as part of France). They are
# not published until the crosswalk has them (envdash/geo.py EXTRA_TERRITORIES).
NOT_IN_CROSSWALK = {"GUF": "French Guiana", "REU": "Reunion"}

# Each must be found in the methodology PDF before anything is published.
METHODOLOGY_REQUIRED = (
    *ey.METHODOLOGY_REQUIRED,
    "We provide data for 215 countries from 2000",
    "“% share” values refer to the share of generation (this does not include net imports) and not the share of "
    "consumption unless otherwise specified.",
    "we project latest generation data by applying absolute changes by fuel from available annualised monthly data "
    "to historical annual values.",
    "These figures aim to include full lifecycle emissions including upstream methane, supply chain and "
    "manufacturing emissions, and include all gases, converted into CO2 equivalent over a 100-year timescale.",
    "Upstream methane emissions for gas and coal generation are calculated on a long-term basis assuming methane is "
    "21 times as potent as CO2.",
)

GCO2E_KWH = Unit(
    code="gCO2e/kWh",
    label="grams of carbon dioxide equivalent per kilowatt-hour (lifecycle)",
    short="g CO₂e/kWh",
)


def require_methodology(pdf: bytes) -> dict[str, int]:
    """Each required statement -> the 1-based PDF page it is on. Stops if Ember no longer says it."""
    pages = textmatch.pdf_pages_text(pdf)
    found: dict[str, int] = {}
    for q in METHODOLOGY_REQUIRED:
        hit = [i + 1 for i, p in enumerate(pages) if textmatch.contains(p, q)]
        if not hit:
            raise EmberFormatError(f"the methodology no longer says {q!r}; re-read it before trusting these rules")
        found[q] = hit[0]
    return found


# --- reading ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaYear:
    entity: str
    area: str
    year: str
    rows: dict[str, dict]
    """Ember source label -> the row."""


def entity_of(iso3: str | None, area: str) -> str | None:
    """Our entity code for a country row, None for a declared NOT_IN_CROSSWALK area; anything else unknown raises."""
    if iso3 is None:
        raise EmberFormatError(f"country row {area!r} has no ISO 3 code")
    if iso3 in NOT_IN_CROSSWALK:
        if NOT_IN_CROSSWALK[iso3] != area:
            raise EmberFormatError(f"{iso3} is {area!r} in the file, not {NOT_IN_CROSSWALK[iso3]!r}")
        return None
    return geo.resolve(ISO_ALIASES.get(iso3, iso3), "iso3")


def area_years(df: pl.DataFrame) -> tuple[list[AreaYear], list[str]]:
    """World and country rows from FIRST_YEAR, grouped by area and year, sorted by entity then year; plus the
    names of the areas left out because they are not in the crosswalk."""
    keep = df.filter(
        (((pl.col("Area") == WORLD) & (pl.col("Area type") == "Region")) | (pl.col("Area type") == COUNTRY))
        & (pl.col("Year").cast(pl.Int32) >= FIRST_YEAR)
    )
    groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    names: dict[str, str] = {}
    skipped: set[str] = set()
    for r in keep.iter_rows(named=True):
        if r["Area type"] == COUNTRY:
            ent = entity_of(r["ISO 3 code"], r["Area"])
            if ent is None:
                skipped.add(r["Area"])
                continue
        else:
            ent = "WLD"
        if names.setdefault(ent, r["Area"]) != r["Area"]:
            raise EmberFormatError(f"{ent} is both {names[ent]!r} and {r['Area']!r}")
        g = groups[(ent, r["Year"])]
        if r["Electricity source"] in g:
            raise EmberFormatError(f"{r['Area']} {r['Year']} has two rows for {r['Electricity source']!r}")
        g[r["Electricity source"]] = r
    out = [AreaYear(e, names[e], y, rows) for (e, y), rows in groups.items()]
    return sorted(out, key=lambda a: (a.entity, int(a.year))), sorted(skipped)


def negative_rows(ay: AreaYear) -> list[str]:
    """'Other fossil -1.15 TWh' for each non-aggregated generating source with negative generation."""
    out = []
    for label in SOURCES:
        r = ay.rows.get(label)
        g = _dec(r[GEN]) if r else None
        if g is not None and g < 0:
            out.append(f"{label} {r[GEN]} TWh")  # type: ignore[index]
    return out


def check_area_year(ay: AreaYear) -> None:
    """Stop unless the shares, Clean and intensity of this area and year mean what is published."""
    where = f"{ay.area} {ay.year}"
    total = ay.rows.get("Total generation")
    if total is None:
        raise EmberFormatError(f"{where}: no Total generation row")
    tot = _dec(total[GEN])
    if tot is None or tot == 0:
        return  # nothing to check: no shares or intensity can be published (see _null_reason)
    shares = [_dec(ay.rows[s][SHARE]) for s in SOURCES if s in ay.rows]
    if any(s is None for s in shares):
        raise EmberFormatError(f"{where}: a source share is empty while Total generation is {total[GEN]} TWh")
    s_sum = sum(shares, Decimal(0))  # type: ignore[arg-type]
    if abs(s_sum - 100) > _half_unit(*shares):  # type: ignore[arg-type]
        raise EmberFormatError(f"{where}: the source shares add up to {s_sum}, not 100")
    clean = ay.rows.get("Clean")
    if clean is not None:
        cg, cs, ren = _dec(clean[GEN]), _dec(clean[SHARE]), _dec(ay.rows["Renewables"][GEN])
        parts = [ren] + ([_dec(ay.rows["Nuclear"][GEN])] if "Nuclear" in ay.rows else [])
        if cg is None or cs is None or any(p is None for p in parts):
            raise EmberFormatError(f"{where}: Clean, Renewables or Nuclear generation is empty")
        if abs(cg - sum(parts, Decimal(0))) > _half_unit(cg, *parts):  # type: ignore[arg-type]
            raise EmberFormatError(f"{where}: Clean {cg} TWh is not Renewables plus Nuclear")
        if abs(cs - cg / tot * 100) > _half_unit(cs) + Decimal(100) * _half_unit(cg, tot) / abs(tot):
            raise EmberFormatError(f"{where}: Clean share {cs}% is not Clean over Total generation")
    em, it = _dec(total[EMISSIONS]), _dec(total[INTENSITY])
    if it is not None:
        if em is None:
            raise EmberFormatError(f"{where}: an intensity without emissions")
        tol = _half_unit(it) + Decimal(1000) * (_half_unit(em) / abs(tot) + abs(em) * _half_unit(tot) / (tot * tot))
        if abs(it - em / tot * 1000) > tol:
            raise EmberFormatError(f"{where}: intensity {it} is not Emissions {em} / Generation {tot} x 1000")


# --- observations -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Status:
    world_gaps: dict[str, tuple[int, list[str]]]
    latest_year: str


def status_of(ay: AreaYear, st: Status) -> tuple[str, str | None]:
    if ay.entity == "WLD":
        return ey._status_note(ay.year, st.world_gaps)
    if ay.year == st.latest_year:
        return "preliminary", (
            f"{ay.year} is the latest year in Ember's file, which has no estimate flag; Ember's methodology says "
            "that for the most recent years it estimates annual generation from monthly data."
        )
    return "final", None


def _null_reason(ay: AreaYear, what: str) -> str | None:
    """Why `what` is not published for this area and year, or None if it may be."""
    neg = negative_rows(ay)
    if neg:
        return (
            f"Not published: Ember's file gives negative generation for {ay.area} in {ay.year} ({'; '.join(neg)}), "
            f"so its {what} does not describe a generation mix."
        )
    tot = ay.rows["Total generation"][GEN]
    if _dec(tot) in (None, Decimal(0)):
        return (
            f"Ember's file gives Total generation of {tot or 'nothing'} TWh for {ay.area} in {ay.year}, and no {what}."
        )
    return None


def _obs(ay: AreaYear, st: Status, value: Decimal | None, what: str, dims: dict[str, str] | None = None) -> Observation:
    status, note = status_of(ay, st)
    reason = _null_reason(ay, what)
    if reason is None and value is None:
        reason = f"Ember's file has no {what} for {ay.area} in {ay.year}."
    return Observation(
        entity=ay.entity,
        period=ay.year,
        value=None if reason else float(value),  # type: ignore[arg-type]
        missing_reason=reason,
        status=status,  # type: ignore[arg-type]
        note=note,
        dims=dims or {},
    )


@dataclass(frozen=True)
class Read:
    groups: list[AreaYear]
    skipped: list[str]
    status: Status


def read(df: pl.DataFrame) -> Read:
    groups, skipped = area_years(df)
    for ay in groups:
        check_area_year(ay)
    latest = max(int(y) for y in df["Year"].unique())
    return Read(groups, skipped, Status(ey.country_gaps(df), str(latest)))


def mix_observations(r: Read) -> list[Observation]:
    by_series: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for ay in r.groups:
        for label, (dim_id, _) in SOURCES.items():
            if label in ay.rows:
                v = _dec(ay.rows[label][SHARE])
                by_series[(ay.entity, dim_id)].append(_obs(ay, r.status, v, f"share for {label}", {"source": dim_id}))
    order = [d for d, _ in SOURCES.values()]
    return [o for k in sorted(by_series, key=lambda k: (k[0], order.index(k[1]))) for o in by_series[k]]


def clean_observations(r: Read) -> list[Observation]:
    return [_obs(ay, r.status, _dec(ay.rows["Clean"][SHARE]), "Clean share") for ay in r.groups if "Clean" in ay.rows]


def intensity_observations(r: Read) -> list[Observation]:
    return [_obs(ay, r.status, _dec(ay.rows["Total generation"][INTENSITY]), "emissions intensity") for ay in r.groups]


# --- transforms ---------------------------------------------------------------------------------------------------


def _withheld(r: Read) -> list[str]:
    return [f"{ay.area} {ay.year} ({'; '.join(negative_rows(ay))})" for ay in r.groups if negative_rows(ay)]


def _steps(files: dict[str, InputFile], r: Read, pages: dict[str, int], vintage: str) -> list[str]:
    m = files[METHODOLOGY.key].snapshot
    prelim_world = [y for y, (_, missing) in sorted(r.status.world_gaps.items()) if missing and int(y) >= FIRST_YEAR]
    page_list = ", ".join(str(p) for p in sorted(set(pages.values())))
    withheld = _withheld(r)
    countries = len({ay.entity for ay in r.groups} - {"WLD"})
    return [
        f"Read release_generation_yearly_global.csv, last modified by Ember on {vintage} (Ember gives no version "
        "label, so that date is the vintage), and Ember's data methodology (PDF last modified "
        f"{vintage_of(m.last_modified)}, sha256 {m.sha256[:12]}…). Every methodology statement this transform relies "
        f"on was found in the PDF (pages {page_list}) before publishing.",
        f"Kept the World and the {countries} countries and economies in pipeline/geo/entities.csv, from {FIRST_YEAR}, "
        "the first year of Ember's stated coverage (earlier rows exist for some countries and are partial). Each "
        "country is matched by Ember's ISO 3 code; Ember's XKX is Kosovo (KOS). Not published because they have no "
        f"entity in the crosswalk: {', '.join(r.skipped) if r.skipped else 'none'}.",
        "Checked, for every country and year, that the shares of the generating sources in the file add up to 100%, "
        "that Clean generation is Renewables plus Nuclear and the Clean share is Clean over Total generation, and "
        "that the emissions intensity is emissions over generation, each to within the rounding of the printed "
        "values.",
        "Left as null, with the reason, every share and intensity of a country-year in which the file gives a "
        "negative generation for a source, because those shares do not describe a generation mix. Ember projects "
        "the latest year by applying absolute changes from monthly data to annual values, which can go below zero. "
        f"In this vintage: {'; '.join(withheld) if withheld else 'none'}.",
        "Status: a World year is preliminary when the file has no Total generation for a country that has it for an "
        "earlier year (Ember estimates missing country years from historical trends), as in "
        f"electricity.ember.mix-world: {', '.join(prelim_world) if prelim_world else 'none'}. Each country's "
        f"values for {r.status.latest_year}, the latest year in the file, are preliminary, because Ember estimates "
        "the most recent year from monthly data and the file does not say for which countries.",
    ]


def _runner(compute, last_step: str):
    def run(files: dict[str, InputFile]) -> Result:
        g = files[GENERATION.key]
        df = read_table(g.path.read_bytes())
        pages = require_methodology(files[METHODOLOGY.key].path.read_bytes())
        vintage = vintage_of(g.snapshot.last_modified)
        r = read(df)
        return Result(
            observations=compute(r),
            vintage=vintage,
            date_published=vintage,
            steps=[*_steps(files, r, pages, vintage), last_step],
        )

    return run


SHARE_BASIS = (
    "Share of electricity generation, not of consumption: net imports are not included. Ember reports annual "
    "generation as gross generation where it can. The latest year is partly estimated from monthly data."
)
INTENSITY_BASIS = (
    "Lifecycle emissions per unit of electricity generated, as Ember labels them: upstream methane, supply chain and "
    "manufacturing emissions of each fuel and technology, all gases, in CO₂-equivalent over 100 years with methane "
    "counted at 21 times CO₂ (a factor from the IPCC Second Assessment Report, so none of the AR5 or AR6 options "
    "applies). Not combustion CO₂, and never comparable with or added to Global Carbon Project emissions. Per unit "
    "of generation, net imports excluded."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (GENERATION, METHODOLOGY)
    keys = (Path(ey.__file__),)
    return [
        Transform(
            spec=Spec(
                id="electricity.ember.mix-by-country",
                title="Electricity generation by source, by country",
                description="Share of each country's electricity generation from each source (solar, wind, hydro, "
                "bioenergy, other renewables, nuclear, coal, gas and other fossil fuels), each year since 2000, as "
                "published by Ember, with the world for comparison.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(geography="Countries and economies, and the world", basis=SHARE_BASIS),
                geo_coverage="country",
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
            inputs=inputs,
            run=_runner(
                mix_observations,
                "Published Ember's 'Share of generation (%)' of each of the nine sources as printed, for each "
                "country and year that has a row for that source.",
            ),
            module_file=here,
            validation=Validation(min_rows=150 * 26 * 6, value_range=(0.0, 100.0)),
            key_files=keys,
        ),
        Transform(
            spec=Spec(
                id="electricity.ember.clean-share-by-country",
                title="Share of electricity from clean sources, by country",
                description="Share of each country's electricity generation from renewables (solar, wind, hydro, "
                "bioenergy and other renewables) and nuclear power together, each year since 2000, as published by "
                "Ember, with the world for comparison.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(
                    geography="Countries and economies, and the world",
                    basis=SHARE_BASIS + " Clean means renewables plus nuclear.",
                ),
                geo_coverage="country",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(
                clean_observations,
                "Published Ember's 'Share of generation (%)' of its aggregated source 'Clean' (renewables plus "
                "nuclear) as printed.",
            ),
            module_file=here,
            validation=Validation(min_rows=150 * 26, value_range=(0.0, 100.0)),
            key_files=keys,
        ),
        Transform(
            spec=Spec(
                id="electricity.ember.lifecycle-intensity-by-country",
                title="Carbon intensity of electricity (lifecycle), by country",
                description="Greenhouse gas emissions per kilowatt-hour of electricity generated in each country, "
                "counting the whole lifecycle of each power source (fuel extraction, methane leaks, building the "
                "plants), each year since 2000, as estimated by Ember, with the world for comparison.",
                kind="series",
                unit=GCO2E_KWH,
                display=Display(decimals=0),
                scope=Scope(geography="Countries and economies, and the world", basis=INTENSITY_BASIS),
                geo_coverage="country",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(
                intensity_observations,
                "Published Ember's 'Emissions intensity (gCO2e/kWh)' of 'Total generation' as printed.",
            ),
            module_file=here,
            validation=Validation(min_rows=150 * 26, value_range=(0.0, 1500.0)),
            key_files=keys,
        ),
    ]

"""Ember yearly electricity data: the world's electricity generation mix and its clean share.

Input: release_generation_yearly_global.csv (one row per area, year and electricity source; generation, share and
other metrics as columns) and Ember's data methodology PDF, both from the ember-yearly registry entry.

Vintage. Ember prints no version label on the file or the landing page, so the vintage is the date of the file's HTTP
Last-Modified header (the registry's {version}), e.g. "2026-09-22". A snapshot without that header stops the build.

Values. Both indicators publish Ember's own "Share of generation (%)" column for Area "World" as printed: the nine
non-aggregated sources for the mix, and Ember's aggregated "Clean" row for the clean share. Nothing is recomputed.
The build stops unless the file still means what we say it means (each tolerance is half the last printed digit of
every value involved, i.e. rounding only):
- the nine non-aggregated sources are exactly Solar, Wind, Hydro, Bioenergy, Other renewables, Nuclear, Coal, Gas
  and Other fossil, and their shares add up to 100;
- Clean generation equals Renewables plus Nuclear, Renewables equals the five renewable sources, and the Clean
  share equals Clean over Total generation.

Partly estimated years. The file has no estimate flag, and its country rows thin out in the latest years: in the file
of 22 September 2026, Total generation has values for 209 countries and economies in 2022, 208 in 2023 (no Ukraine),
194 in 2024 and 93 in 2025. Ember's methodology says how the gaps enter the totals (both sentences are checked in the
methodology PDF at every build): "For the most recent years, data is often not available. In these cases we use
monthly data, which is reported on a shorter lag, to estimate the latest annual generation." and "Values for missing
years for a given country are estimated based on historical trends of demand and generation from individual sources
by country." So a World year is published with status preliminary, and a note giving the count, whenever the file has
no Total generation for that year for a country that has it for an earlier year. (Countries whose series starts
later are not gaps.) The methodology's "Regional and world estimates" paragraph still names 2024 as the estimated
year in the file of 22 September 2026, so it is not quoted.

Publisher check. None applies to this vintage. Ember's statements on 2025 shares (Global Electricity Review 2026,
21 April 2026, and the World page updated 27 May 2026: "Solar reached 8.7% of global generation in 2025, almost
matching nuclear's share (8.9%)" and "low-carbon sources generated 43%") come from earlier files whose
Last-Modified dates we do not have; the September file has nuclear at 8.829% and clean at 42.309%, so those numbers
were revised and cannot check this vintage. Searched 2026-10-04 for an Ember statement on the September file; none
found.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

import polars as pl

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "ember-yearly"
GENERATION = Input(SOURCE, "generation-yearly-global")
METHODOLOGY = Input(SOURCE, "methodology-pdf")

COLUMNS = [
    "Area",
    "ISO 3 code",
    "Year",
    "Area type",
    "Electricity source",
    "Is aggregated source",
    "Generation (TWh)",
    "Generation YoY change (TWh)",
    "Generation YoY change (%)",
    "Share of generation (%)",
    "Share of generation YoY change (% points)",
    "Capacity (GW)",
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
GEN = "Generation (TWh)"
SHARE = "Share of generation (%)"
WORLD = "World"
COUNTRY = "Country or economy"

# Ember's label -> (our dimension value id, label). Order is the published order of the dimension.
RENEWABLES = ("Solar", "Wind", "Hydro", "Bioenergy", "Other renewables")
SOURCES: dict[str, tuple[str, str]] = {
    "Solar": ("solar", "Solar"),
    "Wind": ("wind", "Wind"),
    "Hydro": ("hydro", "Hydro"),
    "Bioenergy": ("bioenergy", "Bioenergy"),
    "Other renewables": ("other-renewables", "Other renewables"),
    "Nuclear": ("nuclear", "Nuclear"),
    "Coal": ("coal", "Coal"),
    "Gas": ("gas", "Gas"),
    "Other fossil": ("other-fossil", "Other fossil"),
}

METHODOLOGY_REQUIRED = (
    "For the most recent years, data is often not available. In these cases we use monthly data, which is reported "
    "on a shorter lag, to estimate the latest annual generation.",
    "Values for missing years for a given country are estimated based on historical trends of demand and generation "
    "from individual sources by country.",
)

PERCENT = Unit(code="percent", label="percent of electricity generation", short="%")


class EmberFormatError(ValueError):
    pass


# --- reading ------------------------------------------------------------------------------------------------------


def vintage_of(last_modified: str | None) -> str:
    """The file's HTTP Last-Modified date, ISO (Ember's files carry no version label)."""
    if not last_modified:
        raise EmberFormatError("the snapshot has no Last-Modified header, which is the only vintage Ember gives")
    return parsedate_to_datetime(last_modified).date().isoformat()


def read_table(raw: bytes) -> pl.DataFrame:
    df = pl.read_csv(raw, infer_schema=False)
    if df.columns != COLUMNS:
        raise EmberFormatError(f"columns {df.columns} != expected {COLUMNS}")
    return df


def _dec(v: str | None) -> Decimal | None:
    return None if v is None or v == "" else Decimal(v)


def _half_unit(*values: Decimal) -> Decimal:
    """Largest possible rounding error of a sum or difference of printed values: half the last digit of each."""
    total = Decimal(0)
    for v in values:
        exp = v.as_tuple().exponent
        assert isinstance(exp, int)
        total += Decimal(5) * Decimal(10) ** (exp - 1)
    return total


@dataclass(frozen=True)
class WorldYear:
    year: str
    share: dict[str, Decimal | None]
    """Ember source label -> Share of generation (%), for the nine sources and the aggregates."""
    generation: dict[str, Decimal | None]


def world_years(df: pl.DataFrame) -> list[WorldYear]:
    """World rows by year, checked against the definitions this module relies on."""
    w = df.filter((pl.col("Area") == WORLD) & (pl.col("Area type") == "Region"))
    if w.height == 0:
        raise EmberFormatError("no rows for Area 'World'")
    by_year: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in w.iter_rows(named=True):
        src = r["Electricity source"]
        if src in by_year[r["Year"]]:
            raise EmberFormatError(f"World {r['Year']} has two rows for {src!r}")
        by_year[r["Year"]][src] = r
    out: list[WorldYear] = []
    for year in sorted(by_year, key=int):
        rows = by_year[year]
        base = {s for s, r in rows.items() if r["Is aggregated source"] == "False"}
        if base != set(SOURCES):
            raise EmberFormatError(f"World {year}: non-aggregated sources {sorted(base)} != {sorted(SOURCES)}")
        for agg in ("Renewables", "Clean", "Total generation"):
            if agg not in rows or rows[agg]["Is aggregated source"] != "True":
                raise EmberFormatError(f"World {year}: no aggregated row {agg!r}")
        wy = WorldYear(
            year=year,
            share={s: _dec(r[SHARE]) for s, r in rows.items()},
            generation={s: _dec(r[GEN]) for s, r in rows.items()},
        )
        check_definitions(wy)
        out.append(wy)
    return out


def check_definitions(wy: WorldYear) -> None:
    """Stop unless shares and the Clean aggregate mean what the indicators say (rounding tolerance only)."""
    y, g, s = wy.year, wy.generation, wy.share
    shares = [s[k] for k in SOURCES]
    if all(v is not None for v in shares):
        total = sum(shares, Decimal(0))  # type: ignore[arg-type]
        if abs(total - 100) > _half_unit(*shares):  # type: ignore[arg-type]
            raise EmberFormatError(f"World {y}: the nine source shares add up to {total}, not 100")
    needed = ("Clean", "Renewables", "Nuclear", "Total generation", *RENEWABLES)
    if any(g[k] is None for k in needed) or s["Clean"] is None:
        raise EmberFormatError(f"World {y}: generation missing for one of {needed}")
    clean, ren, nuc, tot = g["Clean"], g["Renewables"], g["Nuclear"], g["Total generation"]
    assert clean is not None and ren is not None and nuc is not None and tot is not None
    if abs(clean - (ren + nuc)) > _half_unit(clean, ren, nuc):
        raise EmberFormatError(f"World {y}: Clean {clean} TWh is not Renewables {ren} + Nuclear {nuc}")
    parts = [g[k] for k in RENEWABLES]
    if abs(ren - sum(parts, Decimal(0))) > _half_unit(ren, *parts):  # type: ignore[arg-type]
        raise EmberFormatError(f"World {y}: Renewables {ren} TWh is not the sum of {RENEWABLES}")
    clean_share = s["Clean"]
    # Share printed to its last digit; generation values rounded too, so allow both rounding errors.
    tol = _half_unit(clean_share) + Decimal(100) * _half_unit(clean, tot) / tot
    if abs(clean_share - clean / tot * 100) > tol:
        raise EmberFormatError(f"World {y}: Clean share {clean_share}% is not Clean / Total generation")


def country_gaps(df: pl.DataFrame) -> dict[str, tuple[int, list[str]]]:
    """year -> (countries with Total generation in an earlier year, those of them without it in this year)."""
    t = df.filter(
        (pl.col("Area type") == COUNTRY)
        & (pl.col("Electricity source") == "Total generation")
        & pl.col(GEN).is_not_null()
    )
    years_of: dict[str, set[int]] = defaultdict(set)
    for area, year in t.select("Area", "Year").iter_rows():
        years_of[area].add(int(year))
    # Every year in the file, not only years some country has: a year with World rows and no country rows at all is
    # the most estimated of all.
    all_years = sorted({int(y) for y in df["Year"].unique()})
    out: dict[str, tuple[int, list[str]]] = {}
    for y in all_years:
        earlier = [a for a, ys in years_of.items() if min(ys) < y]
        missing = sorted(a for a in earlier if y not in years_of[a])
        out[str(y)] = (len(earlier), missing)
    return out


def _estimate_note(year: str, earlier: int, missing: list[str]) -> str:
    return (
        f"Partly Ember's estimate: the file has no {year} generation for {len(missing)} of the {earlier} countries and "
        "economies with generation for an earlier year, and Ember's methodology says it estimates a country's missing "
        "years from its historical trends of demand and generation by source."
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


# --- observations -------------------------------------------------------------------------------------------------


def _status_note(year: str, gaps: dict[str, tuple[int, list[str]]]) -> tuple[str, str | None]:
    earlier, missing = gaps[year]
    if missing:
        return "preliminary", _estimate_note(year, earlier, missing)
    return "final", None


def mix_observations(df: pl.DataFrame) -> list[Observation]:
    years = world_years(df)
    gaps = country_gaps(df)
    obs: list[Observation] = []
    for label, (dim_id, _) in SOURCES.items():
        for wy in years:
            status, note = _status_note(wy.year, gaps)
            v = wy.share[label]
            obs.append(
                Observation(
                    entity="WLD",
                    period=wy.year,
                    value=None if v is None else float(v),
                    missing_reason=None if v is not None else f"Ember's file has no share for {label} in {wy.year}.",
                    status=status,  # type: ignore[arg-type]
                    note=note,
                    dims={"source": dim_id},
                )
            )
    return obs


def clean_observations(df: pl.DataFrame) -> list[Observation]:
    gaps = country_gaps(df)
    obs: list[Observation] = []
    for wy in world_years(df):
        status, note = _status_note(wy.year, gaps)
        v = wy.share["Clean"]
        assert v is not None  # check_definitions requires it
        obs.append(Observation(entity="WLD", period=wy.year, value=float(v), status=status, note=note))  # type: ignore[arg-type]
    return obs


# --- transforms ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Read:
    df: pl.DataFrame
    vintage: str
    pages: dict[str, int]
    methodology_date: str
    methodology_sha256: str


def _read(files: dict[str, InputFile]) -> _Read:
    g, m = files[GENERATION.key], files[METHODOLOGY.key]
    return _Read(
        df=read_table(g.path.read_bytes()),
        vintage=vintage_of(g.snapshot.last_modified),
        pages=require_methodology(m.path.read_bytes()),
        methodology_date=vintage_of(m.snapshot.last_modified),
        methodology_sha256=m.snapshot.sha256,
    )


def _common_steps(r: _Read, years: list[str]) -> list[str]:
    gaps = country_gaps(r.df)
    prelim = [y for y in years if gaps[y][1]]
    pages = ", ".join(str(p) for p in sorted(set(r.pages.values())))
    return [
        f"Read release_generation_yearly_global.csv, last modified by Ember on {r.vintage} (Ember gives no version "
        "label, so that date is the vintage), and kept the rows for Area 'World'.",
        "Checked that the shares mean what is published: the nine non-aggregated sources (Solar, Wind, Hydro, "
        "Bioenergy, Other renewables, Nuclear, Coal, Gas, Other fossil) add up to 100%, Clean generation is "
        "Renewables plus Nuclear, Renewables is the five renewable sources, and the Clean share is Clean over Total "
        "generation, each to within the rounding of the printed values.",
        "Marked a year preliminary, with a note giving the count, when the file has no Total generation for that "
        "year for a country or economy that has it for an earlier year. Ember's data methodology (PDF last modified "
        f"{r.methodology_date}, sha256 {r.methodology_sha256[:12]}…; both sentences were found on pages {pages} "
        "before publishing) says it estimates the latest annual generation from monthly data and a country's "
        "missing years from historical trends, so the World value for such a year is partly Ember's estimate. "
        f"Preliminary years in this vintage: {', '.join(prelim) if prelim else 'none'}.",
    ]


def _run_mix(files: dict[str, InputFile]) -> Result:
    r = _read(files)
    obs = mix_observations(r.df)
    return Result(
        observations=obs,
        vintage=r.vintage,
        date_published=r.vintage,
        steps=[
            *_common_steps(r, sorted({o.period for o in obs})),
            "Published Ember's 'Share of generation (%)' for each of the nine sources as printed, one series per "
            "source.",
        ],
    )


def _run_clean(files: dict[str, InputFile]) -> Result:
    r = _read(files)
    obs = clean_observations(r.df)
    return Result(
        observations=obs,
        vintage=r.vintage,
        date_published=r.vintage,
        steps=[
            *_common_steps(r, [o.period for o in obs]),
            "Published Ember's 'Share of generation (%)' of its aggregated source 'Clean' (renewables plus nuclear) "
            "as printed.",
        ],
    )


SCOPE_BASIS = (
    "Share of electricity generation, not of consumption: net imports are not included. Ember reports annual "
    "generation as gross generation where it can."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (GENERATION, METHODOLOGY)
    return [
        Transform(
            spec=Spec(
                id="electricity.ember.mix-world",
                title="World electricity generation by source",
                description="Share of the world's electricity generation from each source (solar, wind, hydro, "
                "bioenergy, other renewables, nuclear, coal, gas and other fossil fuels), each year since 2000, as "
                "published by Ember.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(geography="World", basis=SCOPE_BASIS),
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
            inputs=inputs,
            run=_run_mix,
            module_file=here,
            validation=Validation(min_rows=26 * len(SOURCES), value_range=(0.0, 100.0)),
        ),
        Transform(
            spec=Spec(
                id="electricity.ember.clean-share-world",
                title="Share of world electricity from clean sources",
                description="Share of the world's electricity generation from renewables (solar, wind, hydro, "
                "bioenergy and other renewables) and nuclear power together, each year since 2000, as published by "
                "Ember.",
                kind="series",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(geography="World", basis=SCOPE_BASIS + " Clean means renewables plus nuclear."),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_run_clean,
            module_file=here,
            validation=Validation(min_rows=26, value_range=(0.0, 100.0)),
        ),
    ]

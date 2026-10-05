"""SEI Emissions Inequality Dashboard: the share of the world's consumption carbon dioxide emitted by the richest 10%,
the richest 1% and the poorest 50% of people, each year 1990-2022.

Input: the Historical Global Shares API (artifact global-percentile-shares, CC BY 4.0), one JSON object
{"records": [...]}. Each record is one slice of the world's population ranked by income for one year: Year,
PercentileLabel ("p{lower}p{upper}", in percent of people), PercentileValue (the slice's width as a fraction),
IncomeShare, EmissionShare and PopulationShare (fractions of the world total), and Elasticity. All values are strings.
The slices are whole percentiles up to p98p99, then the top 1% split into tenths, hundredths and thousandths of a
percent (127 slices a year).

Checks on every build, so that the sums below mean what their names say: every record has exactly these fields; for
each year the slices run from p0 to p100 with no gap or overlap; each slice's PercentileValue equals its upper minus
lower bound, divided by 100; no slice straddles 50, 90 or 99; the year's EmissionShare values add up to 1 within
1e-9; every record gives Elasticity "1"; and the years run without a gap. Anything else stops the transform.

Groups. SEI publishes slices, not these groups, so each group's share is the sum of its slices' EmissionShare, with
exact decimal arithmetic on the strings as served, times 100 for percent: bottom 50% is every slice whose upper bound is
at most 50, top 10% every slice whose lower bound is at least 90, top 1% every slice whose lower bound is at least 99.
The top 1% is part of the top 10%. The dashboard's own "Emission Summary by Global Income Group" table, which this API
backs, groups the same slices (bottom 50%, middle 40%, next 9%, next 0.9%, top 0.1%).

Scope, from SEI's FAQ (https://emissions-inequality.org/faq/, read 2026-10-05): national consumption emissions are
territorial emissions plus net emissions embodied in trade, of fossil carbon dioxide only ("We do not consider non-CO2
emissions and emissions from land-use change"), shared among each country's people by income and then ranked across
the world. The split rests on SEI's assumptions (an emissions floor and ceiling and an elasticity of 1 between them;
every record of the file gives Elasticity "1").

The series ends in 2022. SEI's national inputs switch basis in 2023, from consumption-based to territorial carbon
dioxide: the API's own national values (historicalDataByCountry, artifacts national-history-che, -usa and -gbr, read
from their snapshots at every build and quoted in a processing step) give Switzerland NatEmisions 121,979,300 t in 2022
and 32,737,300 t in 2023, the United States 5,642,856,100 t and 4,911,391,000 t, and the United Kingdom 488,532,000 t
and 305,146,300 t (rounded to the tonne; as served, for example, 32737299.999999996). The research of 2026-10-05
(docs/research/sources-ghg-food-personal-2026-10-05.json) matched the 2023 values to territorial emissions (Global
Carbon Budget 2025: Switzerland consumption 118.3 Mt, territorial 32.0 Mt; United States 5,432 Mt and 4,918 Mt). The
world top-10% share drops from 48.99% in 2022 to 47.08% in 2023 at that break. So 2023 is not comparable with
1990-2022 and is not published. The global shares response carries no basis field, so the cut is a declared year
(LAST_CONSUMPTION_YEAR), not a test of the data; the transform stops if the response no longer reaches that year, or
if a national series no longer gives NatEmisions for that year and the next.

Vintage. The API has no version or release date. The series is labelled by the years it covers and the date the
bytes were first fetched (the snapshot's date_accessed).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "sei-emissions-inequality"
SHARES = Input(SOURCE, "global-percentile-shares")
# The national series quoted in the processing step on the 2023 cut: (input, ISO code, name in the step).
NATIONAL: tuple[tuple[Input, str, str], ...] = (
    (Input(SOURCE, "national-history-che"), "CHE", "Switzerland"),
    (Input(SOURCE, "national-history-usa"), "USA", "the United States"),
    (Input(SOURCE, "national-history-gbr"), "GBR", "the United Kingdom"),
)
NATIONAL_FIELDS = (
    "CountryName",
    "CountryISOCode",
    "Year",
    "EmissionsPerCap",
    "GDPPerCap",
    "Population",
    "NatEmisions",
    "NatGDP",
)
FIELDS = ("Year", "PercentileLabel", "PercentileValue", "IncomeShare", "EmissionShare", "PopulationShare", "Elasticity")
LABEL = re.compile(r"p(?P<lo>\d+(?:\.\d+)?)p(?P<hi>\d+(?:\.\d+)?)")
SUM_TOLERANCE = Decimal("1e-9")
HUNDRED = Decimal(100)

# (dimension value id, label); in_group says which slices each one adds up.
GROUPS: tuple[tuple[str, str], ...] = (
    ("top-10", "Richest 10%"),
    ("top-1", "Richest 1%"),
    ("bottom-50", "Poorest 50%"),
)
BOUNDARIES = (Decimal(50), Decimal(90), Decimal(99))
LAST_CONSUMPTION_YEAR = 2022
"""The last year whose national inputs are consumption-based (see the module docstring); later years are left out."""

PERCENT = Unit(code="percent", label="percent of world consumption carbon dioxide emissions", short="%")


class SeiFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Slice:
    year: int
    lower: Decimal
    upper: Decimal
    emission_share: Decimal


def _decimal(v: object, where: str) -> Decimal:
    if not isinstance(v, str):
        raise SeiFormatError(f"{where}: {v!r} is not a string")
    try:
        d = Decimal(v)
    except ArithmeticError:
        raise SeiFormatError(f"{where}: {v!r} is not a number") from None
    if not d.is_finite():
        raise SeiFormatError(f"{where}: {v!r} is not a finite number")
    return d


def read_slices(raw: bytes) -> dict[int, list[Slice]]:
    """The slices of each year, sorted by lower bound, after checking that they partition 0-100%."""
    doc = json.loads(raw)
    if not isinstance(doc, dict) or set(doc) != {"records"} or not isinstance(doc["records"], list):
        raise SeiFormatError("expected one object with a 'records' list")
    by_year: dict[int, list[Slice]] = {}
    elasticities: set[str] = set()
    for n, rec in enumerate(doc["records"]):
        if not isinstance(rec, dict) or tuple(rec) != FIELDS:
            raise SeiFormatError(f"record {n}: fields {list(rec) if isinstance(rec, dict) else rec!r} != {FIELDS}")
        where = f"record {n} ({rec['Year']} {rec['PercentileLabel']})"
        if not re.fullmatch(r"\d{4}", str(rec["Year"])):
            raise SeiFormatError(f"{where}: Year is not a four-digit year")
        m = LABEL.fullmatch(str(rec["PercentileLabel"]))
        if m is None:
            raise SeiFormatError(f"{where}: PercentileLabel is not p<lower>p<upper>")
        lo, hi = Decimal(m["lo"]), Decimal(m["hi"])
        if _decimal(rec["PercentileValue"], where) * HUNDRED != hi - lo:
            raise SeiFormatError(f"{where}: PercentileValue {rec['PercentileValue']} is not ({hi} - {lo}) / 100")
        elasticities.add(rec["Elasticity"])
        by_year.setdefault(int(rec["Year"]), []).append(
            Slice(int(rec["Year"]), lo, hi, _decimal(rec["EmissionShare"], where))
        )
    if not by_year:
        raise SeiFormatError("no records")
    if elasticities != {"1"}:
        raise SeiFormatError(f"Elasticity values {sorted(elasticities)}: the scope note says every record has 1")
    for year in sorted(by_year):
        slices = sorted(by_year[year], key=lambda s: s.lower)
        edge = Decimal(0)
        for s in slices:
            if s.lower != edge:
                raise SeiFormatError(f"{year}: slice p{s.lower}p{s.upper} does not start where the last ended ({edge})")
            if any(s.lower < b < s.upper for b in BOUNDARIES):
                raise SeiFormatError(f"{year}: slice p{s.lower}p{s.upper} straddles a group boundary")
            edge = s.upper
        if edge != HUNDRED:
            raise SeiFormatError(f"{year}: slices end at {edge}, not 100")
        total = sum((s.emission_share for s in slices), Decimal(0))
        if abs(total - 1) > SUM_TOLERANCE:
            raise SeiFormatError(f"{year}: emission shares add up to {total}, not 1")
        by_year[year] = slices
    return by_year


def check_years(by_year: dict[int, list[Slice]]) -> None:
    """The API serves every year of the series: a gap means a changed or truncated response."""
    years = sorted(by_year)
    if years != list(range(years[0], years[-1] + 1)):
        raise SeiFormatError(f"years {years[0]}-{years[-1]} have gaps")


def consumption_years(by_year: dict[int, list[Slice]]) -> dict[int, list[Slice]]:
    """The years up to LAST_CONSUMPTION_YEAR, the last year SEI built on consumption-based national emissions."""
    if LAST_CONSUMPTION_YEAR not in by_year:
        raise SeiFormatError(f"the response has no {LAST_CONSUMPTION_YEAR}, the last consumption-based year")
    return {y: v for y, v in by_year.items() if y <= LAST_CONSUMPTION_YEAR}


def national_emissions(raw: bytes, iso: str, years: tuple[int, ...]) -> dict[int, Decimal]:
    """{year: NatEmisions in tonnes as served} for the given years of one historicalDataByCountry response."""
    doc = json.loads(raw)
    if not isinstance(doc, dict) or set(doc) != {"records"} or not isinstance(doc["records"], list):
        raise SeiFormatError(f"{iso}: expected one object with a 'records' list")
    out: dict[int, Decimal] = {}
    for n, rec in enumerate(doc["records"]):
        if not isinstance(rec, dict) or tuple(rec) != NATIONAL_FIELDS:
            raise SeiFormatError(f"{iso} record {n}: fields {list(rec) if isinstance(rec, dict) else rec!r}")
        if rec["CountryISOCode"] != iso:
            raise SeiFormatError(f"{iso} record {n}: CountryISOCode {rec['CountryISOCode']!r}")
        year = int(rec["Year"])
        if year in years:
            if year in out:
                raise SeiFormatError(f"{iso}: {year} twice")
            out[year] = _decimal(rec["NatEmisions"], f"{iso} {year} NatEmisions")
    missing = sorted(set(years) - set(out))
    if missing:
        raise SeiFormatError(f"{iso}: no NatEmisions for {missing}")
    return out


def basis_break_step(files: dict[str, InputFile]) -> str:
    """The step explaining the cut after LAST_CONSUMPTION_YEAR with the national values of NATIONAL, from snapshots."""
    years = (LAST_CONSUMPTION_YEAR, LAST_CONSUMPTION_YEAR + 1)
    parts = []
    for inp, iso, name in NATIONAL:
        f = files[inp.key]
        nat = national_emissions(f.path.read_bytes(), iso, years)
        a, b = (f"{nat[y].quantize(Decimal(1)):,} t" for y in years)
        parts.append(f"{name} {a} in {years[0]} and {b} in {years[1]} (sha256 {f.snapshot.sha256[:12]}…)")
    accessed = max(files[inp.key].snapshot.date_accessed for inp, _, _ in NATIONAL).isoformat()
    return (
        f"SEI's national inputs are consumption-based up to {LAST_CONSUMPTION_YEAR} and territorial (where emissions "
        f"happen) from {years[1]}, so later shares are not comparable. The API's own national values show the break "
        f"(historicalDataByCountry, NatEmisions as served, rounded here to the tonne; snapshots retrieved {accessed}): "
        + "; ".join(parts)
        + f". The {years[1]} values match Global Carbon Budget 2025 territorial emissions, not consumption (research "
        "of 2026-10-05, docs/research/sources-ghg-food-personal-2026-10-05.json)."
    )


def in_group(group: str, s: Slice) -> bool:
    if group == "top-10":
        return s.lower >= 90
    if group == "top-1":
        return s.lower >= 99
    if group == "bottom-50":
        return s.upper <= 50
    raise KeyError(group)


def group_shares(by_year: dict[int, list[Slice]]) -> list[Observation]:
    obs: list[Observation] = []
    for gid, _ in GROUPS:
        for year in sorted(by_year):
            share = sum((s.emission_share for s in by_year[year] if in_group(gid, s)), Decimal(0))
            obs.append(
                Observation(entity="WLD", period=f"{year:04d}", value=float(share * HUNDRED), dims={"group": gid})
            )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[SHARES.key]
    served = read_slices(f.path.read_bytes())
    check_years(served)
    by_year = consumption_years(served)
    first, last = min(by_year), max(by_year)
    slices = {len(v) for v in served.values()}
    accessed = f.snapshot.date_accessed.isoformat()
    dropped = sorted(set(served) - set(by_year))
    return Result(
        observations=group_shares(by_year),
        vintage=f"{first}-{last} consumption-based years of the {min(served)}-{max(served)} historical series, "
        f"retrieved {accessed}",
        steps=[
            f"Read the Historical Global Shares API response (sha256 {f.snapshot.sha256[:12]}…, retrieved {accessed}): "
            f"{sum(len(v) for v in served.values())} records, {min(served)}–{max(served)}, "
            f"{' or '.join(str(n) for n in sorted(slices))} income slices a year. Checked for every year that the "
            "slices run from 0 to 100% of people with no gap or overlap, that each slice's width matches its label, "
            "and that the emission shares add up to 1 (within one billionth).",
            f"Kept {first}–{last} and left out {', '.join(map(str, dropped)) or 'no year'}. " + basis_break_step(files),
            "For each year, added up the EmissionShare of the slices in each group with exact decimal arithmetic on "
            "the values as served: the poorest 50% (slices up to the 50th percentile), the richest 10% (from the 90th) "
            "and the richest 1% (from the 99th, which SEI splits into finer slices). The richest 1% are part of the "
            "richest 10%.",
            "Multiplied by 100 to give percent.",
        ],
        changes="emission shares of income slices added up into three groups (poorest 50%, richest 10%, richest 1%) "
        "and converted from fractions to percent.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="co2-share.sei-inequality.income-groups-global",
                title="Share of world consumption carbon dioxide by income group (SEI)",
                description="The share of the world's consumption-based carbon dioxide emissions caused by the "
                "richest 10%, the richest 1% and the poorest 50% of people, ranked by income across the world, each "
                "year from 1990 to 2022. Consumption emissions count what a country's people buy, including imports, "
                "and exclude what it makes for export. The split between people depends on the Stockholm Environment "
                "Institute's assumptions about how emissions rise with income. These are shares of the world total, "
                "not tonnes per person. SEI also serves 2023, but builds it on territorial national emissions "
                "(where emissions happen) instead of consumption, so 2023 is not comparable and is not shown.",
                kind="derived",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=Scope(
                    geography="World: everyone in the world, ranked by income per person (2021 US dollars at "
                    "purchasing power parity)",
                    lulucf="excluded",
                    basis="Fossil carbon dioxide only, consumption-based (territorial emissions plus net emissions "
                    "embodied in trade); other greenhouse gases and land-use change are not included. Each country's "
                    "emissions are shared among its people in proportion to income between a floor and a ceiling "
                    "(SEI's elasticity of 1). SEI's pages do not say how international aviation and shipping are "
                    "allocated.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="group",
                        label="Income group",
                        values=[DimensionValue(id=i, label=label) for i, label in GROUPS],
                    ),
                ),
                headline_dims=(("group", "top-10"),),
            ),
            inputs=(SHARES, *(inp for inp, _, _ in NATIONAL)),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=3 * 33, value_range=(0.0, 100.0)),
        )
    ]

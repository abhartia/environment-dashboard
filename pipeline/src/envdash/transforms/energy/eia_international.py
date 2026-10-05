"""EIA international energy data: total primary energy consumption by fuel, for the world and each country, and the
share of it from fossil fuels.

Input: INTL.zip (registry entry eia-international, artifact intl-bulk), whose one member INTL.txt holds one JSON object
per line: a series (series_id, name, units, geography, last_updated, data as [period, value] pairs) or a category.
The bulk manifest (artifact bulk-manifest) gives the release: its INTL entry must name the zip's URL as accessURL,
and its last_updated date is the vintage, written as EIA's citation form asks ("Sep 2026").

Series used, annual (.A) in quadrillion Btu (QBTU), activity 2 (consumption), one per geography:
  44-2 total energy consumption; 4411-2 coal; 4413-2 natural gas; 4415-2 petroleum and other liquids; 4417-2
  nuclear; 4418-2 renewables and other.
Every series name is checked against EIA_NAMES, and units must be "quadrillion Btu". Values are published as EIA
gives them (full precision); a period whose value is one of EIA's codes ('--', 'NA', 'ie') is a null value whose
missing_reason quotes the code. EIA's file does not define these codes.

Entities. EIA's geography for a country is its ISO 3166 alpha-3 code, resolved with envdash.geo; an aggregate's is
the '+'-joined list of its members and is not published (regions, OECD, OPEC...), except the World (WLD). EIA's XKS
is Kosovo (KOS). Geographies that are not in pipeline/geo/entities.csv are declared in NOT_IN_CROSSWALK (former
states, territories Natural Earth draws inside another country, EIA's own trade zones) and are not published; any
other unknown code stops the build.

Accounting method. EIA counts primary energy with the captured-energy approach for non-combustible renewables: the
electricity from hydro, wind, solar, geothermal and tide and wave power enters at its own energy content, 3,412 Btu
per kilowatt-hour, while fossil fuels enter at their heat content and nuclear at the heat input of the plants. The
transform checks this on every build from EIA's own generation series (activity 12, in billion kWh and in quad Btu):
for every country except the United States and every year, the quad Btu of hydro (33), wind (37), solar (116),
geothermal (35) and tide and wave (117) electricity must be 3,412.14 Btu per kWh times the billion kWh (to within
0.5 Btu per kWh, for generation of at least 0.01 billion kWh). The United States does not follow it in this file
(solar 3,622 Btu per kWh in 2024), so the transform also records, per vintage, which entities' totals differ from the
sum of their five fuel series: in the file of 3 October 2026 only the United States and therefore the World (by the
same amount: the total is 1.442 quad Btu below the sum in 2024). Nuclear's heat rate is stated in the steps.
Because of this method, EIA's totals and shares differ from the Energy Institute's and the IEA's, and series from
different producers are never joined.

Fossil share (derived): coal + natural gas + petroleum and other liquids, divided by total energy consumption, times
100, for each entity and year with all four values. It can exceed 100% where EIA's total is smaller than those three
together, because EIA's "renewables and other" is negative in that country-year (244 country-years in the file of
3 October 2026, up to 109.6% for Estonia in 1992; Laos, a large exporter of hydropower, has 106.1% in 2017). Such
values are published with a note giving both numbers.

Publisher check: none. EIA states no world primary energy share in the INTL release.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "eia-international"
BULK = Input(SOURCE, "intl-bulk")
MANIFEST = Input(SOURCE, "bulk-manifest")
MEMBER = "INTL.txt"
QBTU = "quadrillion Btu"
BKWH = "billion kilowatthours"
CODES = ("--", "NA", "ie")

TOTAL = "44"
FUELS: dict[str, tuple[str, str]] = {
    # EIA product code -> (our dimension value id, label)
    "4411": ("coal", "Coal"),
    "4413": ("natural-gas", "Natural gas"),
    "4415": ("petroleum", "Petroleum and other liquids"),
    "4417": ("nuclear", "Nuclear"),
    "4418": ("renewables-and-other", "Renewables and other"),
}
FOSSIL = ("4411", "4413", "4415")
EIA_NAMES = {
    "44": "Total energy consumption",
    "4411": "Total energy consumption from coal",
    "4413": "Total energy consumption from natural gas",
    "4415": "Total energy consumption from petroleum and other liquids",
    "4417": "Total energy consumption from nuclear",
    "4418": "Total energy consumption from renewables and other",
}
# Non-combustible renewable electricity (activity 12, net generation) whose quad Btu must be 3,412 Btu per kWh.
CAPTURED = {
    "33": "Hydroelectricity net generation",
    "37": "Wind electricity net generation",
    "116": "Solar electricity net generation",
    "35": "Geothermal electricity net generation",
    "117": "Tide and wave electricity net generation",
}
NUCLEAR_GEN = ("27", "Nuclear electricity net generation")
BTU_PER_KWH = Decimal("3412.14")
BTU_TOLERANCE = Decimal("0.5")
MIN_BKWH = Decimal("0.01")
CAPTURED_EXCEPTIONS = {"USA"}

ISO_ALIASES = {"XKS": "KOS"}
# EIA geography -> EIA's name for it (file of 3 October 2026). Not in pipeline/geo/entities.csv, so not published.
NOT_IN_CROSSWALK = {
    "CSK": "Former Czechoslovakia",
    "DDR": "Germany, East",
    "DEUW": "Germany, West",
    "GUF": "French Guiana",
    "HITZ": "Hawaiian Trade Zone",
    "NLDA": "Netherlands Antilles",
    "REU": "Reunion",
    "SCG": "Former Serbia and Montenegro",
    "SUN": "Former U.S.S.R.",
    "USIQ": "U.S. Pacific Islands",
    "USOH": "U.S. Territories",
    "WAK": "Wake Island",
    "YUG": "Former Yugoslavia",
}


class EiaFormatError(ValueError):
    pass


# --- reading ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Series:
    product: str
    geography: str
    name: str
    units: str
    data: dict[str, Decimal | str]
    """period -> value (exact decimal of the JSON number) or one of EIA's codes."""


def _parse_value(v: object, sid: str, period: str) -> Decimal | str:
    if isinstance(v, str):
        if v not in CODES:
            raise EiaFormatError(f"{sid} {period}: unknown code {v!r}")
        return v
    if isinstance(v, bool) or not isinstance(v, int | float | Decimal):
        raise EiaFormatError(f"{sid} {period}: value {v!r} is not a number")
    return Decimal(str(v)) if not isinstance(v, Decimal) else v


def _wanted(sid: str) -> tuple[str, str] | None:
    """(product, activity) for the annual series this module reads, else None."""
    if not sid.startswith("INTL.") or not sid.endswith(".A"):
        return None
    parts = sid[5:].split("-")
    if len(parts) != 4:
        return None
    product, activity, _, unit = parts
    if activity == "2" and unit == "QBTU.A" and (product == TOTAL or product in FUELS):
        return product, activity
    if activity == "12" and unit in ("QBTU.A", "BKWH.A") and (product in CAPTURED or product == NUCLEAR_GEN[0]):
        return product, activity
    return None


def read_series(text_bytes: bytes) -> dict[tuple[str, str, str], Series]:
    """(product, activity-unit, geography) -> Series, for the series this module reads whose region code (the third
    part of series_id) is their geography, or WORL for the World (WLD). Aggregates and EIA's one-country regions are
    skipped. Activity-unit is "2" for consumption in quad Btu, "12-QBTU" / "12-BKWH" for
    generation."""
    out: dict[tuple[str, str, str], Series] = {}
    for line in io.BytesIO(text_bytes):
        d = json.loads(line, parse_float=Decimal)
        sid = d.get("series_id")
        if sid is None:
            continue
        w = _wanted(sid)
        if w is None:
            continue
        product, activity = w
        unit = sid.rsplit("-", 1)[1]
        kind = "2" if activity == "2" else f"12-{unit.split('.')[0]}"
        g = d["geography"]
        region = sid.split("-")[2]
        if region != g and not (region == "WORL" and g == "WLD"):
            continue  # an aggregate ('+'-joined members), or an IEO region holding one country (WP18 is Mexico)
        data = {}
        for period, v in d["data"]:
            if period in data:
                raise EiaFormatError(f"{sid}: period {period} twice")
            data[period] = _parse_value(v, sid, period)
        key = (product, kind, g)
        if key in out:
            raise EiaFormatError(f"two series for {key}")
        out[key] = Series(product, g, d["name"], d["units"], data)
    return out


def bulk_text(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        if z.namelist() != [MEMBER]:
            raise EiaFormatError(f"INTL.zip members {z.namelist()} != [{MEMBER!r}]")
        return z.read(MEMBER)


def release_of(manifest: bytes, url: str) -> datetime:
    """The INTL entry's last_updated, after checking that it describes the zip at `url`."""
    d = json.loads(manifest)
    e = d["dataset"]["INTL"]
    if e["accessURL"] != url:
        raise EiaFormatError(f"the bulk manifest gives INTL at {e['accessURL']!r}, not {url!r}")
    return datetime.fromisoformat(e["last_updated"])


def vintage_of(release: datetime) -> str:
    """EIA's citation form, e.g. 'Sep 2026'."""
    return f"{release:%b %Y}"


# --- entities -----------------------------------------------------------------------------------------------------


def entity_of(s: Series) -> str | None:
    """Our entity code, or None for a declared NOT_IN_CROSSWALK geography."""
    g = s.geography
    if g == "WLD":
        if not s.name.endswith(", World, Annual"):
            raise EiaFormatError(f"geography WLD is {s.name!r}")
        return "WLD"
    if g in NOT_IN_CROSSWALK:
        if f", {NOT_IN_CROSSWALK[g]}, Annual" not in s.name:
            raise EiaFormatError(f"geography {g} is {s.name!r}, expected {NOT_IN_CROSSWALK[g]!r}")
        return None
    return geo.resolve(ISO_ALIASES.get(g, g), "iso3")


@dataclass(frozen=True)
class Table:
    """Consumption by entity: product -> period -> value or code."""

    by_entity: dict[str, dict[str, dict[str, Decimal | str]]]
    geography: dict[str, str]
    """our entity -> EIA geography"""


def consumption(series: dict[tuple[str, str, str], Series]) -> Table:
    by: dict[str, dict[str, dict[str, Decimal | str]]] = defaultdict(dict)
    geos: dict[str, str] = {}
    for (product, kind, _), s in series.items():
        if kind != "2":
            continue
        if not s.name.startswith(EIA_NAMES[product] + ", "):
            raise EiaFormatError(f"product {product} is named {s.name!r}, expected {EIA_NAMES[product]!r}")
        if s.units != QBTU:
            raise EiaFormatError(f"{s.name}: units {s.units!r}, not {QBTU!r}")
        ent = entity_of(s)
        if ent is None:
            continue
        if geos.setdefault(ent, s.geography) != s.geography:
            raise EiaFormatError(f"{ent} is both {geos[ent]} and {s.geography}")
        by[ent][product] = s.data
    for ent, prods in by.items():
        if set(prods) != {TOTAL, *FUELS}:
            raise EiaFormatError(f"{ent}: products {sorted(prods)} != {sorted({TOTAL, *FUELS})}")
    return Table(dict(by), geos)


# --- checks -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MethodCheck:
    checked: int
    """(country, source, year) values found at 3,412 Btu per kWh."""
    nuclear_world: dict[str, Decimal]
    """year -> World nuclear consumption per kWh of nuclear generation, Btu."""
    exceptions: dict[str, str]
    """entity -> a sentence on how it departs, for CAPTURED_EXCEPTIONS."""


def check_captured_energy(series: dict[tuple[str, str, str], Series]) -> MethodCheck:
    n = 0
    exceptions: dict[str, list[str]] = defaultdict(list)
    for (product, kind, g), q in series.items():
        if kind != "12-QBTU" or product not in CAPTURED:
            continue
        if not q.name.startswith(CAPTURED[product] + ", "):
            raise EiaFormatError(f"product {product} is {q.name!r}, expected {CAPTURED[product]!r}")
        b = series.get((product, "12-BKWH", g))
        if b is None or q.units != QBTU or b.units != BKWH:
            raise EiaFormatError(f"{q.name}: no matching billion kWh series, or unexpected units")
        for period, qv in q.data.items():
            bv = b.data.get(period)
            if not isinstance(qv, Decimal) or not isinstance(bv, Decimal) or bv < MIN_BKWH:
                continue
            rate = qv * Decimal(1_000_000) / bv
            if abs(rate - BTU_PER_KWH) <= BTU_TOLERANCE:
                n += 1
            elif g in CAPTURED_EXCEPTIONS:
                exceptions[g].append(f"{CAPTURED[product].split(' electricity')[0].lower()} {period} {rate:.0f}")
            elif g != "WLD":
                raise EiaFormatError(
                    f"{q.name} {period}: {rate:.2f} Btu per kWh, not {BTU_PER_KWH}; EIA may have changed its "
                    "accounting method, so re-read it before publishing"
                )
    nuc, gen = series[("4417", "2", "WLD")], series[(NUCLEAR_GEN[0], "12-BKWH", "WLD")]
    rates = {
        p: v * Decimal(1_000_000) / gen.data[p]  # type: ignore[operator]
        for p, v in nuc.data.items()
        if isinstance(v, Decimal) and isinstance(gen.data.get(p), Decimal) and gen.data[p]
    }
    if any(abs(r - BTU_PER_KWH) <= BTU_TOLERANCE for r in rates.values()):
        raise EiaFormatError("World nuclear consumption is at 3,412 Btu per kWh in some year: re-read EIA's method")
    say = {g: f"{len(v)} values, e.g. {', '.join(sorted(v)[-2:])} Btu per kWh" for g, v in exceptions.items()}
    return MethodCheck(n, rates, say)


def sum_gaps(t: Table) -> dict[str, dict[str, Decimal]]:
    """entity -> {period: total minus the sum of the five fuels} where that is more than 1e-9 quad Btu."""
    out: dict[str, dict[str, Decimal]] = {}
    for ent, prods in t.by_entity.items():
        for p, total in prods[TOTAL].items():
            parts = [prods[f].get(p) for f in FUELS]
            if isinstance(total, Decimal) and all(isinstance(x, Decimal) for x in parts):
                gap = total - sum(parts, Decimal(0))  # type: ignore[arg-type]
                if abs(gap) > Decimal("1e-9"):
                    out.setdefault(ent, {})[p] = gap
    return out


# --- observations -------------------------------------------------------------------------------------------------


def _code_reason(code: str) -> str:
    return f"EIA's file gives the code {code!r} instead of a value."


def fuel_observations(t: Table) -> list[Observation]:
    obs = []
    for ent in sorted(t.by_entity):
        for product, (dim_id, _) in FUELS.items():
            for p, v in sorted(t.by_entity[ent][product].items()):
                obs.append(
                    Observation(
                        entity=ent,
                        period=p,
                        value=float(v) if isinstance(v, Decimal) else None,
                        missing_reason=None if isinstance(v, Decimal) else _code_reason(v),
                        dims={"fuel": dim_id},
                    )
                )
    return obs


def total_observations(t: Table) -> list[Observation]:
    return [
        Observation(
            entity=ent,
            period=p,
            value=float(v) if isinstance(v, Decimal) else None,
            missing_reason=None if isinstance(v, Decimal) else _code_reason(v),
        )
        for ent in sorted(t.by_entity)
        for p, v in sorted(t.by_entity[ent][TOTAL].items())
    ]


def fossil_share_observations(t: Table) -> list[Observation]:
    obs = []
    for ent in sorted(t.by_entity):
        prods = t.by_entity[ent]
        for p, total in sorted(prods[TOTAL].items()):
            parts = {f: prods[f].get(p) for f in FOSSIL}
            codes = [f"{FUELS[f][1].lower()} {v!r}" for f, v in parts.items() if not isinstance(v, Decimal)]
            if not isinstance(total, Decimal):
                codes.insert(0, f"total {total!r}")
            if codes:
                reason = f"EIA's file gives a code instead of a value for {', '.join(codes)}."
                obs.append(Observation(entity=ent, period=p, value=None, missing_reason=reason))
                continue
            assert isinstance(total, Decimal)
            if total <= 0:
                reason = f"EIA's total energy consumption is {total} quad Btu, so no share can be calculated."
                obs.append(Observation(entity=ent, period=p, value=None, missing_reason=reason))
                continue
            fossil = sum(parts.values(), Decimal(0))  # type: ignore[arg-type]
            share = fossil / total * 100
            note = None
            if share > 100:
                note = (
                    f"Above 100% because EIA's total energy consumption ({total:.4f} quad Btu) is smaller than its "
                    f"coal, natural gas and petroleum consumption together ({fossil:.4f} quad Btu) in this year."
                )
            obs.append(Observation(entity=ent, period=p, value=float(share), note=note))
    return obs


# --- transforms ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Read:
    table: Table
    method: MethodCheck
    gaps: dict[str, dict[str, Decimal]]
    release: datetime
    zip_modified: str | None


@lru_cache(maxsize=1)
def _read_cached(zip_path: Path, manifest_path: Path, url: str, zip_modified: str | None) -> _Read:
    # Paths are content-addressed (pipeline/.snapshots/<sha256>), so the three indicators parse INTL.txt once.
    release = release_of(manifest_path.read_bytes(), url)
    series = read_series(bulk_text(zip_path.read_bytes()))
    t = consumption(series)
    return _Read(t, check_captured_energy(series), sum_gaps(t), release, zip_modified)


def _read(files: dict[str, InputFile]) -> _Read:
    z, m = files[BULK.key], files[MANIFEST.key]
    return _read_cached(z.path, m.path, str(z.snapshot.url), z.snapshot.last_modified)


def _steps(r: _Read) -> list[str]:
    t = r.table
    latest = max(p for prods in t.by_entity.values() for p, v in prods[TOTAL].items() if isinstance(v, Decimal))
    nuc = r.method.nuclear_world.get(latest)
    world_gap = r.gaps.get("WLD", {}).get(latest)
    gap_list = ", ".join(sorted(r.gaps)) if r.gaps else "none"
    exc = "; ".join(f"{g}: {s}" for g, s in sorted(r.method.exceptions.items())) or "none"
    modified = f" The zip was last modified on the server on {r.zip_modified}." if r.zip_modified else ""
    return [
        f"Read INTL.txt from EIA's bulk file INTL.zip. EIA's bulk manifest gives the INTL release as last updated "
        f"{r.release:%-d %B %Y} and names this zip as its file, so the vintage is '{vintage_of(r.release)}'.{modified}",
        "Kept the annual consumption series in quadrillion Btu: total energy consumption and its five fuels (coal, "
        "natural gas, petroleum and other liquids, nuclear, renewables and other), checking each series' name and "
        f"units. Kept the World and the {len(t.by_entity) - 1} countries and territories in "
        "pipeline/geo/entities.csv, matched by EIA's ISO 3 code (EIA's XKS is Kosovo, KOS); EIA's regional "
        "aggregates are left out, and so are these geographies, which have no entity in the crosswalk: "
        f"{'; '.join(sorted(NOT_IN_CROSSWALK.values()))}.",
        "Checked EIA's accounting method against its own generation series: for every country other than the "
        "United States, the energy content of hydro, wind, solar, geothermal and tide and wave electricity is "
        f"3,412 Btu per kilowatt-hour, the captured-energy approach ({r.method.checked:,} country-years checked). "
        f"Not on that basis in this file: {exc}. World nuclear consumption is {nuc:,.0f} Btu per kilowatt-hour of "
        f"nuclear generation in {latest}, the heat input of the plants."
        if nuc is not None
        else "Checked EIA's accounting method against its own generation series.",
        "Where EIA's total differs from the sum of its five fuel series, both are published as given. Entities "
        f"where they differ in this vintage: {gap_list}"
        + (f" (World {latest}: total minus the sum is {world_gap:.3f} quad Btu)." if world_gap is not None else "."),
        "EIA's codes '--', 'NA' and 'ie' (which the file does not define) are null values whose reason quotes the "
        "code.",
    ]


def _runner(compute, extra: list[str], changes: str | None = None):
    def run(files: dict[str, InputFile]) -> Result:
        r = _read(files)
        return Result(
            observations=compute(r.table),
            vintage=vintage_of(r.release),
            date_published=r.release.date().isoformat(),
            steps=[*_steps(r), *extra],
            changes=changes,
        )

    return run


QUAD_BTU = Unit(code="quad-Btu", label="quadrillion British thermal units", short="quad Btu")
BASIS = (
    "Primary energy consumption as EIA accounts for it: fossil fuels at their heat content; electricity from hydro, "
    "wind, solar, geothermal and tide and wave power at its own energy content, 3,412 Btu per kilowatt-hour (the "
    "captured-energy approach; EIA's United States series depart from it for solar and geothermal); nuclear at the "
    "heat input of the plants. Not comparable with totals from the Energy Institute or the IEA, which count "
    "non-combustible electricity differently. 'Renewables and other' is EIA's own category and can be negative."
)
GEOGRAPHY = "Countries and territories, and the world"


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (BULK, MANIFEST)
    return [
        Transform(
            spec=Spec(
                id="energy.eia.primary-by-fuel",
                title="Primary energy consumption by fuel",
                description="Energy each country and the world use each year since 1980, by fuel: coal, natural gas, "
                "oil and other liquids, nuclear, and renewables and other sources, as accounted for by the US Energy "
                "Information Administration.",
                kind="series",
                unit=QUAD_BTU,
                display=Display(decimals=2),
                scope=Scope(geography=GEOGRAPHY, basis=BASIS),
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="fuel",
                        label="Fuel",
                        values=[DimensionValue(id=i, label=lab) for i, lab in FUELS.values()],
                    ),
                ),
                headline_dims=(("fuel", "coal"),),
            ),
            inputs=inputs,
            run=_runner(fuel_observations, ["Published EIA's values for the five fuels as given."]),
            module_file=here,
            validation=Validation(min_rows=200 * 45 * 5, value_range=(-5.0, 400.0)),
        ),
        Transform(
            spec=Spec(
                id="energy.eia.primary-total",
                title="Total primary energy consumption",
                description="Total energy each country and the world use each year since 1980, counting every fuel, "
                "as accounted for by the US Energy Information Administration.",
                kind="series",
                unit=QUAD_BTU,
                display=Display(decimals=2),
                scope=Scope(geography=GEOGRAPHY, basis=BASIS),
                geo_coverage="country",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(total_observations, ["Published EIA's total energy consumption as given."]),
            module_file=here,
            validation=Validation(min_rows=200 * 45, value_range=(-1.0, 1000.0)),
        ),
        Transform(
            spec=Spec(
                id="energy.eia.fossil-share",
                title="Share of primary energy from fossil fuels",
                description="The part of each country's and the world's total energy use that comes from coal, oil "
                "and natural gas, each year since 1980, calculated from US Energy Information Administration data.",
                kind="derived",
                unit=Unit(code="percent", label="percent of total primary energy consumption", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=GEOGRAPHY,
                    basis=BASIS + " Fossil fuels are EIA's coal, natural gas, and petroleum and other liquids; the "
                    "denominator is EIA's total energy consumption.",
                ),
                geo_coverage="country",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(
                fossil_share_observations,
                [
                    "Fossil share = (coal + natural gas + petroleum and other liquids) / total energy consumption x "
                    "100, for each entity and year with all four values (exact decimal arithmetic on EIA's values). "
                    "A share above 100% carries a note with both numbers."
                ],
                changes="fossil-fuel share calculated as coal, natural gas and petroleum consumption over total energy "
                "consumption.",
            ),
            module_file=here,
            validation=Validation(min_rows=200 * 45, value_range=(0.0, 120.0)),
        ),
    ]

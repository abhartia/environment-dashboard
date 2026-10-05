"""National contributions to warming (Jones et al., version 2025.1): the change in global mean surface temperature
caused by each country's emissions of carbon dioxide, methane and nitrous oxide since 1850.

Input: GMST_response_1851-2024.csv (Zenodo record 16640595), long format with columns CNTR_NAME, ISO3, Gas, Component,
Year, Data, Unit. Gas is CO[2], CH[4], N[2]*O or 3-GHG (the three-gas total); Component is Fossil, LULUCF or Total;
Year runs 1851-2024; Unit is always "°C". Only the 3-GHG Total rows are published: warming from all three gases, from
fossil sources and land use together. The record describes the method: methane and nitrous oxide are converted to
cumulative CO2-equivalent emissions with GWP* and IPCC AR6 coefficients, and warming is the IPCC AR6 best-estimate
transient climate response to cumulative emissions (TCRE) times those cumulative emissions, relative to 1850.

Checks (the transform stops if any fails): every series covers 1851-2024 in order; each entity's 3-GHG Total equals its
3-GHG Fossil plus 3-GHG LULUCF and equals the sum of its CO2, CH4 and N2O Totals; EU27 equals the sum of the 27 member
states (envdash.geo.EU27_MEMBERS); GLOBAL equals the sum of every country row. The file has no rows for international
aviation and shipping, so with that last identity the world value here excludes international transport.

Entities. ISO3 codes through geo.resolve with the source's alias table in envdash/geo.py (KSV Kosovo, GLOBAL the
world, XKW, XPC and XRY the three historical rows). The producer's other groups (GROUPS) are not entities here and are
not published. Some entities have no rows for some gases or sources (seventeen territories and historical rows have
fossil carbon dioxide only; Palestine has land-use carbon dioxide only); their observations say which rows the file
lacks, so that their three-gas value is read as covering what the file has.

Licence. The deposit is labelled CC BY 4.0, but its methane and nitrous oxide come from PRIMAP-hist v2.7 (CC BY-NC-SA
4.0), so these values are shared under CC BY-NC-SA 4.0 (see pipeline/sources/jones-2025-national-contributions.yaml).

Version. PINNED maps the file's Zenodo URL to the record's version and publication date.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "jones-2025-national-contributions"
GMST = Input(SOURCE, "gmst-response-1851")
HEADER = ("CNTR_NAME", "ISO3", "Gas", "Component", "Year", "Data", "Unit")
UNIT = "°C"
YEARS = range(1851, 2025)
TOTAL_GAS = "3-GHG"
GASES = ("CO[2]", "CH[4]", "N[2]*O")
SOURCES = ("Fossil", "LULUCF")
COMPONENTS = (*SOURCES, "Total")
GAS_WORDS = {"CO[2]": "carbon dioxide", "CH[4]": "methane", "N[2]*O": "nitrous oxide"}
SOURCE_WORDS = {"Fossil": "fossil", "LULUCF": "land-use"}
WORLD = "GLOBAL"
EU27 = "EU27"
# The producer's country groups (COUNTRY_GROUPINGS.xlsx): not entities here. EU27 is published (checked above).
GROUPS = frozenset({"ANNEXI", "ANNEXII", "BASIC", "EIT", "LDC", "LMDC", "NONANNEX", "OECD"})
TOLERANCE = Decimal("1e-12")

PINNED: dict[str, tuple[str, date]] = {
    # zenodo.org/api/records/16640595 (read 2026-10-05): version 2025.1, publication_date 2025-11-13.
    "https://zenodo.org/api/records/16640595/files/GMST_response_1851-2024.csv/content": ("2025.1", date(2025, 11, 13)),
}

DEG_C = Unit(code="degC", label="degrees Celsius", short="°C")


class JonesFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Gmst:
    values: dict[tuple[str, str, str], dict[int, Decimal]]
    """(producer ISO3, gas, component) -> year -> °C."""
    order: tuple[str, ...]
    """Producer codes in file order."""


def read_gmst(raw: bytes) -> Gmst:
    reader = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""))
    header = tuple(next(reader))
    if header != HEADER:
        raise JonesFormatError(f"header {header} != {HEADER}")
    values: dict[tuple[str, str, str], dict[int, Decimal]] = {}
    names: dict[str, str] = {}
    order: list[str] = []
    for n, r in enumerate(reader, start=2):
        if len(r) != len(HEADER):
            raise JonesFormatError(f"line {n}: {len(r)} fields")
        name, iso, gas, comp, year, data, unit = r
        if unit != UNIT:
            raise JonesFormatError(f"line {n}: unit {unit!r}, not {UNIT!r}")
        if gas not in (*GASES, TOTAL_GAS) or comp not in COMPONENTS:
            raise JonesFormatError(f"line {n}: unknown gas or component {gas!r} {comp!r}")
        if names.setdefault(iso, name) != name:
            raise JonesFormatError(f"line {n}: {iso} is named both {names[iso]!r} and {name!r}")
        if iso not in order:
            order.append(iso)
        series = values.setdefault((iso, gas, comp), {})
        y = int(year)
        if series and y != max(series) + 1:
            raise JonesFormatError(f"line {n}: {iso} {gas} {comp} year {y} does not follow {max(series)}")
        try:
            series[y] = Decimal(data)
        except ArithmeticError:
            raise JonesFormatError(f"line {n}: {data!r} is not a number") from None
    for key, series in values.items():
        if list(series) != list(YEARS):
            raise JonesFormatError(f"{key}: years {min(series)}-{max(series)} are not {YEARS[0]}-{YEARS[-1]}")
    return Gmst(values, tuple(order))


def _residual(a: Decimal, parts: list[Decimal], what: str) -> Decimal:
    r = abs(a - sum(parts, Decimal(0)))
    if r > TOLERANCE:
        raise JonesFormatError(f"{what}: {a} != sum {sum(parts, Decimal(0))}; the file no longer adds up")
    return r


def check_identities(g: Gmst, *, entities: geo.EntityTable | None = None) -> Decimal:
    """The additive identities in the module text; returns the largest residual."""
    v = g.values
    worst = Decimal(0)
    countries = [c for c in g.order if c not in GROUPS and c not in (WORLD, EU27)]
    for iso in g.order:
        total = v.get((iso, TOTAL_GAS, "Total"))
        if total is None:
            raise JonesFormatError(f"{iso} has no {TOTAL_GAS} Total rows")
        for y in YEARS:
            by_source = [v[(iso, TOTAL_GAS, s)][y] for s in SOURCES if (iso, TOTAL_GAS, s) in v]
            by_gas = [v[(iso, gas, "Total")][y] for gas in GASES if (iso, gas, "Total") in v]
            worst = max(worst, _residual(total[y], by_source, f"{iso} {y} total vs sources"))
            worst = max(worst, _residual(total[y], by_gas, f"{iso} {y} total vs gases"))
    members = [c for c in countries if geo.resolve(c, SOURCE, entities=entities) in geo.EU27_MEMBERS]
    if len(members) != len(geo.EU27_MEMBERS):
        raise JonesFormatError(f"the file has {len(members)} of the 27 EU member states")
    for y in YEARS:
        world = v[(WORLD, TOTAL_GAS, "Total")][y]
        worst = max(worst, _residual(world, [v[(c, TOTAL_GAS, "Total")][y] for c in countries], f"{WORLD} {y}"))
        eu = v[(EU27, TOTAL_GAS, "Total")][y]
        worst = max(worst, _residual(eu, [v[(c, TOTAL_GAS, "Total")][y] for c in members], f"{EU27} {y}"))
    return worst


def missing_rows_note(g: Gmst, iso: str) -> str | None:
    missing = [f"{SOURCE_WORDS[s]} {GAS_WORDS[gas]}" for gas in GASES for s in SOURCES if (iso, gas, s) not in g.values]
    if not missing:
        return None
    listed = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " or " + missing[-1]
    return f"The file has no {listed} rows for this entity; its three-gas value covers the rest."


def observations(g: Gmst, *, entities: geo.EntityTable | None = None) -> list[Observation]:
    obs: list[Observation] = []
    for iso in g.order:
        if iso in GROUPS:
            continue
        code = geo.resolve(iso, SOURCE, entities=entities)
        note = missing_rows_note(g, iso)
        for y, v in g.values[(iso, TOTAL_GAS, "Total")].items():
            obs.append(Observation(entity=code, period=f"{y:04d}", value=float(v), note=note))
    return obs


def _pinned(f: InputFile) -> tuple[str, date]:
    url = str(f.snapshot.url) if f.snapshot.url else None
    if url not in PINNED:
        raise JonesFormatError(f"{url!r} is not a pinned version of the national contributions; add it to PINNED")
    return PINNED[url]


def _run(files: dict[str, InputFile]) -> Result:
    f = files[GMST.key]
    version, published = _pinned(f)
    g = read_gmst(f.path.read_bytes())
    residual = check_identities(g)
    return Result(
        observations=observations(g),
        vintage=version,
        date_published=published.isoformat(),
        steps=[
            f"Read GMST_response_1851-2024.csv (version {version}) and kept the rows for the three-gas total (3-GHG) "
            "from fossil sources and land use together (Total), 1851–2024, in degrees Celsius relative to 1850.",
            "Checked that every entity's three-gas total equals its fossil plus land-use parts and the sum of its "
            "carbon dioxide, methane and nitrous oxide totals; that EU27 equals the sum of its 27 member states; and "
            "that GLOBAL equals the sum of all country rows, so international aviation and shipping, which have no "
            f"rows, are not in the world value (largest difference {float(residual):.1e} °C).",
            "Mapped the producer's ISO3 codes to entity codes through an explicit alias table (KSV Kosovo, GLOBAL the "
            "world, XKW the Kuwaiti oil fires, XPC the Pacific Islands (Palau), XRY the Ryukyu Islands); left out the "
            "producer's groups Annex I, Annex II, BASIC, EIT, LDC, LMDC, non-Annex I and OECD. Values are published "
            "as stated.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="warming.jones-2025.national-contribution",
                title="Contribution to global warming by country",
                description="How much each country's emissions of carbon dioxide, methane and nitrous oxide since "
                "1850, from fossil fuels and from land use, have raised the global mean surface temperature, up to "
                "each year from 1851. Aerosols and fluorinated gases are not included, so the world value is larger "
                "than the observed human-induced warming.",
                kind="series",
                unit=DEG_C,
                display=Display(decimals=3),
                scope=Scope(
                    geography="Countries and territories, three historical entities, the European Union (27) and the "
                    "world (the sum of the countries)",
                    baseline="Change since 1850 (the reference year)",
                    gwp="GWP*",
                    lulucf="included",
                    bunkers="excluded",
                    basis="Carbon dioxide, methane and nitrous oxide from fossil sources and land use. Methane and "
                    "nitrous oxide are converted to cumulative CO2-equivalent emissions with GWP* (IPCC AR6 "
                    "coefficients); warming is the IPCC AR6 best-estimate transient climate response to cumulative "
                    "emissions times those emissions. International aviation and shipping are not included.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=(GMST,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=38_000, value_range=(-0.1, 2.5)),
        )
    ]

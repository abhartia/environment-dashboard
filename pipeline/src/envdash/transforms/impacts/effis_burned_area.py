"""EFFIS burnt-area estimates for Europe: the EU27 and the countries EFFIS groups under the Union Civil Protection
Mechanism (UCPM), every year from 2006, the current year to date included.

Inputs: three JSON responses of source effis. estimates-eu and estimates-ucpm (statistics/v2/effis/
estimatesbycountry?country=EU and ?country=UCPM) are lists of {year, ba, nf}: hectares burnt and number of fires,
for fires mapped at about 30 hectares or larger. areas-of-interest (statistics/utils/countriesbyaoi?aoi=effis) is
EFFIS's own list of which countries make up each total.

What "Europe" means here. Two areas, each exactly as EFFIS defines it in areas-of-interest:
- EU27: the 27 EU member states (published as entity EU27). The list must equal envdash.geo.EU27_MEMBERS.
- UCPM: 43 entries, which must equal UCPM_MEMBERS below: the EU27; Albania, Bosnia and Herzegovina, Iceland, Moldova,
  Montenegro, North Macedonia, Norway, Serbia, Türkiye and Ukraine (the other states taking part in the Union Civil
  Protection Mechanism); and six areas listed separately: Guadeloupe, Martinique, Mayotte, Réunion, Saint-Martin and
  one EFFIS names "Guyana" (iso3 GUY; the EU's outermost region in South America is French Guiana, GUF). Switzerland,
  the United Kingdom, Andorra and Kosovo are not in it. Published as entity UCPM, which needs a row in
  envdash/geo.py AGGREGATES (and so in pipeline/geo/entities.csv, which tests/test_geo.py checks for every published
  entity); that core change is made with the geo module, not here.
A changed membership list stops the build until a person re-reads it and updates this definition.

Year to date. EFFIS serves the current year's running total as its last row. The row for the year in which the
bytes were first fetched (the snapshot's date_accessed) is published with status preliminary and a note naming that
date; EFFIS gives no cut-off date in the file. A row for a later year stops the build.

Checks rather than assumptions. Years run from 2006 without gaps, once each; ba is a whole number of hectares, never
null or negative, in both files; and since every EU27 member is in UCPM, UCPM is never smaller than EU27 in any year.

Values are hectares as served, with no conversion. Number of fires (nf) is not published here.
Publisher check: none. EFFIS's Advance report on 2025 (doi:10.2760/3859043) gives 1 079 538 ha for the EU27 in 2025
(Table 2, printed p. 9), but says on printed p. 8 that "When only 2025 burnt area figures are reported, the fires
and burnt area from all mapped fires is reported", while series compared across years keep only fires larger than
30 ha. This series is the 30 ha one, so the report's single-year figure is not a check of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from envdash import geo
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "effis"
FIRST_YEAR = 2006
EU = Input(SOURCE, "estimates-eu")
UCPM = Input(SOURCE, "estimates-ucpm")
AREAS = Input(SOURCE, "areas-of-interest")

UCPM_NON_EU = frozenset({"ALB", "BIH", "ISL", "MDA", "MKD", "MNE", "NOR", "SRB", "TUR", "UKR"})
UCPM_LISTED_AREAS = frozenset({"GLP", "GUY", "MAF", "MTQ", "MYT", "REU"})
UCPM_MEMBERS = geo.EU27_MEMBERS | UCPM_NON_EU | UCPM_LISTED_AREAS

# (input, EFFIS aoi_code, our entity code, expected members)
SERIES: tuple[tuple[Input, str, str, frozenset[str]], ...] = (
    (EU, "EU", "EU27", geo.EU27_MEMBERS),
    (UCPM, "UCPM", "UCPM", UCPM_MEMBERS),
)


class EffisFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    year: int
    ba: int


def parse_areas(raw: bytes) -> dict[str, frozenset[str]]:
    """aoi_code -> the iso3 codes EFFIS lists for it."""
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise EffisFormatError(f"areas-of-interest: not JSON ({e})") from None
    if not isinstance(doc, list):
        raise EffisFormatError("areas-of-interest: expected a list")
    out: dict[str, set[str]] = {}
    for r in doc:
        if not isinstance(r, dict) or not isinstance(r.get("aoi_code"), str) or not isinstance(r.get("iso3"), str):
            raise EffisFormatError(f"areas-of-interest: row {r!r} has no aoi_code and iso3")
        members = out.setdefault(r["aoi_code"], set())
        if r["iso3"] in members:
            raise EffisFormatError(f"areas-of-interest: {r['iso3']} listed twice under {r['aoi_code']}")
        members.add(r["iso3"])
    return {k: frozenset(v) for k, v in out.items()}


def check_membership(areas: dict[str, frozenset[str]]) -> None:
    for _inp, aoi, _entity, expected in SERIES:
        got = areas.get(aoi)
        if got is None:
            raise EffisFormatError(f"areas-of-interest has no {aoi!r} area")
        if got != expected:
            raise EffisFormatError(
                f"EFFIS changed the membership of {aoi}: added {sorted(got - expected)}, removed "
                f"{sorted(expected - got)}. Re-read areas-of-interest and update the definition in this module."
            )


def parse_estimates(raw: bytes, accessed: date, name: str) -> list[Row]:
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise EffisFormatError(f"{name}: not JSON ({e})") from None
    if not isinstance(doc, list) or not doc:
        raise EffisFormatError(f"{name}: expected a non-empty list")
    rows: list[Row] = []
    for i, r in enumerate(doc):
        year = r.get("year") if isinstance(r, dict) else None
        if year != FIRST_YEAR + i:
            raise EffisFormatError(f"{name}: row {i} is year {year!r}; expected {FIRST_YEAR + i}")
        ba = r.get("ba")
        if isinstance(ba, bool) or not isinstance(ba, int) or ba < 0:
            raise EffisFormatError(f"{name} {year}: ba is {ba!r}, not a whole number of hectares")
        if year > accessed.year:
            raise EffisFormatError(f"{name} {year}: year is after the fetch date {accessed}")
        rows.append(Row(year=year, ba=ba))
    return rows


def observations(entity: str, rows: list[Row], accessed: date) -> list[Observation]:
    out = []
    for r in rows:
        ytd = r.year == accessed.year
        out.append(
            Observation(
                entity=entity,
                period=f"{r.year:04d}",
                value=float(r.ba),
                status="preliminary" if ytd else "final",
                note=(
                    f"Year to date: EFFIS's running total for {r.year} as served on {accessed.isoformat()}, the "
                    "day these bytes were first fetched; not a full year."
                    if ytd
                    else None
                ),
            )
        )
    return out


def _run(files: dict[str, InputFile]) -> Result:
    check_membership(parse_areas(files[AREAS.key].path.read_bytes()))
    parsed: dict[str, list[Row]] = {}
    obs: list[Observation] = []
    ytd: list[str] = []
    for inp, aoi, entity, _members in SERIES:
        f = files[inp.key]
        accessed = f.snapshot.date_accessed
        rows = parse_estimates(f.path.read_bytes(), accessed, inp.artifact_id)
        parsed[aoi] = rows
        obs.extend(observations(entity, rows, accessed))
        ytd += [f"{entity} {r.year} (as served on {accessed.isoformat()})" for r in rows if r.year == accessed.year]
    eu = {r.year: r.ba for r in parsed["EU"]}
    for r in parsed["UCPM"]:
        if r.year in eu and r.ba < eu[r.year]:
            raise EffisFormatError(f"UCPM {r.year} ({r.ba} ha) is smaller than EU27 ({eu[r.year]} ha)")
    last = max(r.year for rows in parsed.values() for r in rows)
    steps = [
        "Read EFFIS's estimatesbycountry responses for the areas EU and UCPM: hectares burnt (ba) each year "
        f"{FIRST_YEAR}–{last}, published as served. Number of fires (nf) is not published.",
        "Checked EFFIS's own membership list (countriesbyaoi): EU has the 27 member states; UCPM has the 27, the ten "
        "other states in the Union Civil Protection Mechanism (ALB, BIH, ISL, MDA, MKD, MNE, NOR, SRB, TUR, UKR) and "
        "six separately listed areas (GLP, GUY, MAF, MTQ, MYT, REU). Checked that UCPM is never below EU27.",
        "Year to date, status preliminary: " + ("; ".join(ytd) if ytd else "none") + ".",
    ]
    return Result(observations=obs, vintage=f"EFFIS estimates {FIRST_YEAR}–{last}", steps=steps)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="burned-area.effis.europe-annual",
                title="Area burnt each year in the EU and in UCPM countries",
                description="Hectares burnt each year since 2006 by fires of about 30 hectares or larger, mapped from "
                "satellite imagery by the European Forest Fire Information System (EFFIS), for the 27 EU member "
                "states and for the wider group EFFIS lists under the EU's Union Civil Protection Mechanism (UCPM). "
                "The current year is a running total to date.",
                kind="series",
                unit=Unit(code="ha", label="hectares", short="ha"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="Europe as EFFIS defines two areas. EU27: the 27 EU member states. UCPM: the 27, plus "
                    "Albania, Bosnia and Herzegovina, Iceland, Moldova, Montenegro, North Macedonia, Norway, Serbia, "
                    "Türkiye and Ukraine, plus Guadeloupe, Martinique, Mayotte, Réunion, Saint-Martin and an area "
                    "EFFIS lists as Guyana. Not included: Switzerland, the United Kingdom, Andorra, Kosovo, Belarus "
                    "and Russia.",
                    basis="Fires of about 30 hectares or larger mapped by EFFIS's Rapid Damage Assessment from "
                    "satellite imagery (MODIS at 250 metres; Sentinel-2 at 20 metres since 2018), by calendar year. "
                    "Fires burning natural land are counted, including prescribed burns. Figures differ from national "
                    "statistics, from single-year report totals (which count all mapped fires, also those under 30 "
                    "hectares) and from GWIS's MODIS-based Europe.",
                ),
                geo_coverage="global-only",
                headline_entity="EU27",
            ),
            inputs=(EU, UCPM, AREAS),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=2 * 20, value_range=(0.0, 1.0e8)),
        )
    ]

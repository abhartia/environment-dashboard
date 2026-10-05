"""GWIS Country Profile: area burned each year, 2002 onwards, for the world and the five UN continents, by land cover.

Inputs: the six JSON responses of source gwis-burned-area (banf-world, banf-africa, banf-americas, banf-asia,
banf-europe, banf-oceania), one per area of interest of the GWIS Country Profile app. Each response's `banfyear` list
holds one object per year with lc1..lc5 and lc_tot (hectares burned, from NASA MODIS MCD64A1 Collection 6.1), and
its `banfmonth` list one object per year and month with the same fields.

Entities. The area is the AOI code in the snapshot's own URL (value=WORLD, UN_AFR, ...), never the artifact name
alone: a URL with another AOI stops the build. WORLD is published as WLD; the continents keep GWIS's codes (UN_AFR,
UN_AME, UN_ASI, UN_EUR, UN_OCE), which GWIS's /api/v3/aoi list names Africa, Americas, Asia, Europe and Oceania and
flags as continents. Those five codes need rows in envdash/geo.py AGGREGATES (and so in pipeline/geo/entities.csv,
which tests/test_geo.py checks for every published entity); that core change is made with the geo module, not here.

Land cover. GWIS's app labels the five classes Forest (lc1), Savannas (lc2), Shrublands/Grasslands (lc3),
Croplands (lc4) and Other (lc5); the JSON carries only the field names, so the labels are this module's mapping of
the app's legend. The percentage fields (lc1p..lc5p), `unmapped`, and the GlobFire fields (ba_area_ha, ba_count,
firesize: 0.0 in 2025 because that product has not been processed for 2025, not because nothing burned) are not
read.

Checks rather than assumptions. In every year the five classes add up to lc_tot, and the twelve months add up to
the year, each to within 0.01 hectare (the files' sums differ by at most about 0.00001 hectare, floating-point
rounding). Every year from 2002 is present once, in order.

Year to date. The year in which these bytes were first fetched (the snapshot's date_accessed) is not over, so it
would be published with status preliminary and a note saying so; a later year, or an earlier year without all twelve
months, stops the build. The registered URLs end at 2025 (yearTo=2025), so on 5 October 2026 every year is complete
and final. The app itself showed 2002-2024 on 4 October 2026 while its API already served all twelve months of
2025.

Values are hectares as stored in the files (the shortest decimal form of each double), with no conversion.
Publisher check: none. GWIS publishes no statement of a yearly total; Our World in Data republishes the world series
(332,928,197.5 ha for 2025) but is an aggregator, not the producer (docs/sources.md, Rejected).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "gwis-burned-area"
FIRST_YEAR = 2002
TOLERANCE_HA = Decimal("0.01")

# (artifact, AOI code in the URL, our entity code, GWIS's own name for the area)
AREAS: tuple[tuple[str, str, str, str], ...] = (
    ("banf-world", "WORLD", "WLD", "World"),
    ("banf-africa", "UN_AFR", "UN_AFR", "Africa"),
    ("banf-americas", "UN_AME", "UN_AME", "Americas"),
    ("banf-asia", "UN_ASI", "UN_ASI", "Asia"),
    ("banf-europe", "UN_EUR", "UN_EUR", "Europe"),
    ("banf-oceania", "UN_OCE", "UN_OCE", "Oceania"),
)
INPUTS = tuple(Input(SOURCE, a) for a, *_ in AREAS)

# (dimension value, label, field in the file)
LAND_COVER: tuple[tuple[str, str, str], ...] = (
    ("total", "All land cover", "lc_tot"),
    ("forest", "Forest", "lc1"),
    ("savannas", "Savannas", "lc2"),
    ("shrublands-grasslands", "Shrublands and grasslands", "lc3"),
    ("croplands", "Croplands", "lc4"),
    ("other", "Other", "lc5"),
)
CLASSES = tuple(f for _, _, f in LAND_COVER if f != "lc_tot")


class GwisFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Year:
    year: int
    values: dict[str, Decimal]
    """Field (lc_tot, lc1..lc5) -> hectares, exactly as stored."""
    months: int
    partial: bool


def aoi_of(url: str | None) -> str:
    """The `value` query parameter of a banf URL: the area of interest the response is for."""
    if url is None:
        raise GwisFormatError("snapshot has no URL, so its area of interest is unknown")
    q = parse_qs(urlsplit(url).query)
    if q.get("level") != ["AOI"] or len(q.get("value", [])) != 1:
        raise GwisFormatError(f"{url}: expected level=AOI and one value=<area>")
    return q["value"][0]


def _number(row: dict, field: str, where: str) -> Decimal:
    v = row.get(field)
    if isinstance(v, bool) or not isinstance(v, Decimal | int):
        raise GwisFormatError(f"{where}: {field} is {v!r}, not a number")
    d = Decimal(v)
    if d < 0:
        raise GwisFormatError(f"{where}: {field} is negative ({d})")
    return d


def parse_banf(raw: bytes, accessed: date, name: str) -> list[Year]:
    """Read banfyear (and banfmonth, for the checks) from one GWIS response."""
    try:
        doc = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise GwisFormatError(f"{name}: not JSON ({e})") from None
    if (
        not isinstance(doc, dict)
        or not isinstance(doc.get("banfyear"), list)
        or not isinstance(doc.get("banfmonth"), list)
    ):
        raise GwisFormatError(f"{name}: expected an object with banfyear and banfmonth lists")
    months: dict[int, list[dict]] = {}
    for m in doc["banfmonth"]:
        if not isinstance(m.get("year"), int) or m.get("month") not in range(1, 13):
            raise GwisFormatError(f"{name}: banfmonth row {m!r} has no valid year and month")
        months.setdefault(m["year"], []).append(m)
    out: list[Year] = []
    for i, row in enumerate(doc["banfyear"]):
        year = row.get("year")
        if year != FIRST_YEAR + i:
            raise GwisFormatError(f"{name}: banfyear row {i} is year {year!r}; expected {FIRST_YEAR + i}")
        where = f"{name} {year}"
        values = {f: _number(row, f, where) for _, _, f in LAND_COVER}
        total = sum((values[f] for f in CLASSES), Decimal(0))
        if abs(total - values["lc_tot"]) > TOLERANCE_HA:
            raise GwisFormatError(f"{where}: lc1..lc5 add up to {total}, not lc_tot {values['lc_tot']}")
        ms = months.get(year, [])
        if len({m["month"] for m in ms}) != len(ms):
            raise GwisFormatError(f"{where}: a month appears more than once in banfmonth")
        if year > accessed.year:
            raise GwisFormatError(f"{where}: year is after the fetch date {accessed}")
        partial = year == accessed.year
        if not partial and len(ms) != 12:
            raise GwisFormatError(f"{where}: a past year with {len(ms)} months in banfmonth, not 12")
        if not partial:
            month_sum = sum((_number(m, "lc_tot", f"{where}-{m['month']:02d}") for m in ms), Decimal(0))
            if abs(month_sum - values["lc_tot"]) > TOLERANCE_HA:
                raise GwisFormatError(f"{where}: the twelve months add up to {month_sum}, not {values['lc_tot']}")
        out.append(Year(year=year, values=values, months=len(ms), partial=partial))
    if not out:
        raise GwisFormatError(f"{name}: banfyear is empty")
    return out


def observations(entity: str, years: list[Year], accessed: date) -> list[Observation]:
    obs: list[Observation] = []
    for dim, _label, field in LAND_COVER:
        for y in years:
            note = None
            if y.partial:
                note = (
                    f"Year to date: {y.year} was not over when this file was first fetched, on "
                    f"{accessed.isoformat()}; not a full year."
                )
            obs.append(
                Observation(
                    entity=entity,
                    period=f"{y.year:04d}",
                    value=float(y.values[field]),
                    status="preliminary" if y.partial else "final",
                    note=note,
                    dims={"land_cover": dim},
                )
            )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    obs: list[Observation] = []
    spans: list[str] = []
    partial_years: set[int] = set()
    for (artifact, aoi, entity, area_name), inp in zip(AREAS, INPUTS, strict=True):
        f = files[inp.key]
        got = aoi_of(str(f.snapshot.url) if f.snapshot.url else None)
        if got != aoi:
            raise GwisFormatError(f"{artifact}: snapshot URL is for area {got!r}, expected {aoi!r}")
        accessed = f.snapshot.date_accessed
        years = parse_banf(f.path.read_bytes(), accessed, artifact)
        partial_years |= {y.year for y in years if y.partial}
        spans.append(f"{area_name} ({aoi}) {years[0].year}–{years[-1].year}")
        obs.extend(observations(entity, years, accessed))
    last = max(int(o.period) for o in obs if o.period)
    steps = [
        "Read the banfyear list of each GWIS Country Profile response (level=AOI): " + "; ".join(spans) + ". "
        "Published per year: lc_tot (all land cover) and lc1–lc5, labelled Forest, Savannas, Shrublands and "
        "grasslands, Croplands and Other as in the GWIS app's legend. Values are hectares as stored, not converted.",
        "Checked in every year that the five land-cover classes add up to lc_tot, and that the twelve months of "
        "banfmonth add up to the year, each to within 0.01 hectare. The GlobFire fields (ba_area_ha, ba_count, "
        "firesize) are not read: they are 0.0 for years GlobFire has not yet processed.",
    ]
    if partial_years:
        steps.append(
            "Year to date: " + ", ".join(str(y) for y in sorted(partial_years)) + " published with status "
            "preliminary, because the year was not over when the file was fetched."
        )
    else:
        steps.append(f"Every year to {last} has twelve months in the file and ended before the fetch: all final.")
    return Result(observations=obs, vintage=f"MCD64A1 C6.1 via GWIS, 2002–{last}", steps=steps)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="burned-area.gwis.annual-by-land-cover",
                title="Area burned each year, world and continents, by land cover",
                description="Hectares burned each year since 2002 worldwide and in Africa, the Americas, Asia, Europe "
                "and Oceania, split into forest, savannas, shrublands and grasslands, croplands and other land, as "
                "mapped by NASA's MODIS satellites and compiled by the EU's Global Wildfire Information System "
                "(GWIS). The 500 metre resolution misses many small fires and much cropland burning, so the totals "
                "are lower than finer-resolution estimates.",
                kind="series",
                unit=Unit(code="ha", label="hectares", short="ha"),
                display=Display(decimals=0),
                dimensions=(
                    Dimension(
                        id="land_cover",
                        label="Land cover",
                        values=[DimensionValue(id=d, label=label) for d, label, _ in LAND_COVER],
                    ),
                ),
                scope=Scope(
                    geography="World, and the five continents of GWIS's Country Profile (Africa, Americas, Asia, "
                    "Europe, Oceania; codes UN_AFR, UN_AME, UN_ASI, UN_EUR, UN_OCE), each read from its own GWIS "
                    "response.",
                    basis="Burned area mapped by NASA MODIS MCD64A1 Collection 6.1 (500 m, monthly), by calendar "
                    "year, January to December, unlike the March–February fire seasons of State of Wildfires. "
                    "GWIS Europe is MODIS-based and differs from EFFIS's estimates for Europe.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                headline_dims=(("land_cover", "total"),),
            ),
            inputs=INPUTS,
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(AREAS) * len(LAND_COVER) * 24, value_range=(0.0, 1.0e9)),
        )
    ]

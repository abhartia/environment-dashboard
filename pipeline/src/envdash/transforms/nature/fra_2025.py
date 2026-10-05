"""FAO Global Forest Resources Assessment 2025 (FRA 2025): forest area by country and for the world, and its annual
net change, from the FRA platform's bulk download.

Input. The bulk zip (fao-fra-2025/bulk-download-world) is generated per request and every member name carries the
download date. The member used is FRA_Years_<yyyy>-<mm>-<dd>.csv at the zip's root (UTF-8 with a byte-order mark, LF;
one row per country or area and reporting year 1990, 2000, 2010, 2015, 2020, 2025), columns iso3, name, year,
1a_forestArea (thousand hectares, two decimals) and 1a_forestArea_flag. Its last column, "Flag", holds the flag
legend in its first rows ("A = Normal value, official data reported by country/area", "I = Imputed value, desk study,
data compiled by FAO", ...); every flag used must be in that legend. Exactly one such member must exist, every
country must have all six years, and no forest area may be empty, or the transform stops.

FRA "forest" is a land-use definition (land over 0.5 ha with trees over 5 m and canopy cover over 10 percent, not
mainly under agricultural or urban use), reported by countries; it is not satellite tree cover.

Entities. Countries are matched by their ISO 3166-1 alpha-3 code through geo.resolve(…, "iso3"). Four areas FRA
reports have no entity in pipeline/geo/entities.csv because Natural Earth's 1:50m layers draw them inside France or
Norway: French Guiana (GUF), Mayotte (MYT), Réunion (REU) and Svalbard and Jan Mayen Islands (SJM). They are declared
in NO_ENTITY, not published on their own, and included in the world total. Any other unknown code stops the transform.

World. FAO's world forest area is built from the country data for the reporting years "for all 236 countries and
areas" (report, chapter 2, printed p. 12). The world value here is the sum over every row of the file, exact decimal
arithmetic. The platform data can include country revisions made after the report, so its sums can differ slightly
from the report's Table 5 (21 October 2025): for 2025 the report gives 4 140 217 thousand ha, the platform data of
2026-10-05 sum to 4 140 443.71 (the Caribbean, Europe and South America differ). The report's WORLD rows of Table 5 and
Table 6 are read from the report PDF (fao-fra-2025/report-2025, quote checked on its page) and set beside ours in a
processing step; they are not publisher checks, because they describe the report's data, not the platform's.

Net change. Annual net change for each interval between reporting years (1990–2000, 2000–2010, 2010–2015, 2015–2020,
2020–2025) = (forest area at the end − forest area at the start) / number of years, in thousand hectares per year,
which is how the report defines forest area net change ("calculated as the difference in forest area between two
points in time"). Negative means net loss.

Vintage. The platform has no version label: the vintage is "FRA 2025 platform, downloaded <date>", the date in the
member names. The zip's content fingerprint (member names without the date, and bytes) decides whether a new download
is a new snapshot (Artifact.content_key zip-members). {year} in FAO's citation is the year of that download.
"""

from __future__ import annotations

import csv
import functools
import io
import itertools
import logging
import re
import zipfile
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from envdash import geo, textmatch
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "fao-fra-2025"
BULK = Input(SOURCE, "bulk-download-world")
REPORT = Input(SOURCE, "report-2025")
MEMBER = re.compile(r"FRA_Years_(\d{4}-\d{2}-\d{2})\.csv")
YEARS = (1990, 2000, 2010, 2015, 2020, 2025)
INTERVALS = tuple(itertools.pairwise(YEARS))
AREA_COL, FLAG_COL, LEGEND_COL = "1a_forestArea", "1a_forestArea_flag", "Flag"
LEGEND = re.compile(r"([A-Z]) = (.+)")
REPORT_PUBLISHED = "2025-10-21"

# FRA iso3 -> FRA's name, for areas with no entity here (counted in the world total, not published on their own).
NO_ENTITY: dict[str, str] = {
    "GUF": "French Guiana",
    "MYT": "Mayotte",
    "REU": "Réunion",
    "SJM": "Svalbard and Jan Mayen Islands",
}

# The report's WORLD rows, verbatim (PDF page, text). Table 5: forest area (1 000 ha) in 1990, 2000, 2010, 2015, 2020,
# 2025. Table 6: annual net change (1 000 ha/year, and %) for 1990–2000, 2000–2015, 2015–2025.
REPORT_TABLE_5 = (35, "WORLD 4 343 534 4 236 587 4 201 001 4 181 435 4 165 241 4 140 217")
REPORT_TABLE_6 = (36, "WORLD −10 695 −0.25 −3 677 −0.09 −4 122 −0.10")


class FraFormatError(ValueError):
    pass


def member_name(names: list[str]) -> tuple[str, date]:
    found = [(n, m.group(1)) for n in names if (m := MEMBER.fullmatch(n))]
    if len(found) != 1:
        raise FraFormatError(f"expected one FRA_Years_<date>.csv at the zip's root, found {[n for n, _ in found]}")
    return found[0][0], date.fromisoformat(found[0][1])


def read_rows(raw: bytes) -> tuple[list[dict[str, str]], dict[str, str]]:
    """The rows (iso3, name, year, area, flag) and the flag legend {"A": "Normal value, ..."}."""
    if not raw.startswith(b"\xef\xbb\xbf"):
        raise FraFormatError("FRA_Years file does not start with a UTF-8 byte-order mark")
    rows = list(csv.reader(io.StringIO(raw[3:].decode("utf-8"))))
    header = rows[0]
    need = ["iso3", "name", "year", AREA_COL, FLAG_COL, LEGEND_COL]
    missing = [c for c in need if c not in header]
    if missing:
        raise FraFormatError(f"FRA_Years file has no column(s) {missing}")
    if header[-1] != LEGEND_COL:
        raise FraFormatError(f"the last column is {header[-1]!r}, not the flag legend {LEGEND_COL!r}")
    ix = {c: header.index(c) for c in need}
    legend: dict[str, str] = {}
    out: list[dict[str, str]] = []
    for n, r in enumerate(rows[1:], start=2):
        if len(r) < ix[FLAG_COL] + 1:
            raise FraFormatError(f"line {n} has {len(r)} fields")
        if len(r) == len(header) and (m := LEGEND.fullmatch(r[ix[LEGEND_COL]])):
            legend[m.group(1)] = m.group(2)
        out.append({c: r[ix[c]] for c in ("iso3", "name", "year", AREA_COL, FLAG_COL)})
    if not legend:
        raise FraFormatError("no flag legend found in the Flag column")
    return out, legend


def forest_area(rows: list[dict[str, str]], legend: dict[str, str]):
    """{iso3: {year: (area, flag)}}, every country with all six years, every area present and flagged."""
    by: dict[str, dict[int, tuple[Decimal, str]]] = defaultdict(dict)
    names: dict[str, str] = {}
    for r in rows:
        code, year = r["iso3"], r["year"]
        if not year.isdigit() or int(year) not in YEARS:
            raise FraFormatError(f"{code}: year {year!r} is not an FRA reporting year")
        if r[AREA_COL] == "":
            raise FraFormatError(f"{code} {year}: forest area is empty")
        if r[FLAG_COL] not in legend:
            raise FraFormatError(f"{code} {year}: flag {r[FLAG_COL]!r} is not in the file's legend {sorted(legend)}")
        if int(year) in by[code]:
            raise FraFormatError(f"{code} {year}: more than one row")
        by[code][int(year)] = (Decimal(r[AREA_COL]), r[FLAG_COL])
        names[code] = r["name"]
    for code, years in by.items():
        if tuple(sorted(years)) != YEARS:
            raise FraFormatError(f"{code}: years {sorted(years)} are not {list(YEARS)}")
    for code, name in NO_ENTITY.items():
        if code in names and names[code] != name:
            raise FraFormatError(f"{code} is named {names[code]!r}, but {name!r} is declared in NO_ENTITY")
    return by


def entity_of(code: str) -> str | None:
    if code in NO_ENTITY:
        return None
    return geo.resolve(code, "iso3")


def _flag_note(flags: set[str], legend: dict[str, str]) -> str:
    return " ".join(f"FRA flag {f}: {legend[f]}." for f in sorted(flags))


def area_observations(by, legend) -> list[Observation]:
    obs: list[Observation] = []
    world = {y: sum(by[c][y][0] for c in by) for y in YEARS}
    for y in YEARS:
        obs.append(Observation(entity="WLD", period=str(y), value=float(world[y])))
    for code in sorted(by):
        entity = entity_of(code)
        if entity is None:
            continue
        for y in YEARS:
            area, flag = by[code][y]
            obs.append(Observation(entity=entity, period=str(y), value=float(area), note=_flag_note({flag}, legend)))
    return sorted(obs, key=lambda o: (o.entity, o.period))


def net_change_observations(by, legend) -> list[Observation]:
    obs: list[Observation] = []
    world = {y: sum(by[c][y][0] for c in by) for y in YEARS}
    for a, b in INTERVALS:
        obs.append(Observation(entity="WLD", period=f"{a}/{b}", value=float((world[b] - world[a]) / (b - a))))
    for code in sorted(by):
        entity = entity_of(code)
        if entity is None:
            continue
        for a, b in INTERVALS:
            (va, fa), (vb, fb) = by[code][a], by[code][b]
            obs.append(
                Observation(
                    entity=entity,
                    period=f"{a}/{b}",
                    value=float((vb - va) / (b - a)),
                    note=_flag_note({fa, fb}, legend),
                )
            )
    return sorted(obs, key=lambda o: (o.entity, o.period))


@functools.lru_cache(maxsize=1)
def report_rows(path: Path) -> None:
    """The report's WORLD rows must be on their pages, as declared. Pages are extracted as textmatch.pdf_pages_text
    does (pypdf), only the two needed. Cached by the content-addressed snapshot path."""
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(path)
    for page, text in (REPORT_TABLE_5, REPORT_TABLE_6):
        if len(reader.pages) < page or not textmatch.contains(reader.pages[page - 1].extract_text() or "", text):
            raise FraFormatError(f"report page {page} does not contain {text!r}")


def _report_numbers(text: str) -> list[Decimal]:
    # "4 343 534" -> 4343534; "−10 695" -> -10695: digits grouped by single spaces, minus sign U+2212.
    t = text.removeprefix("WORLD ").replace("−", "-")
    return [Decimal(n.replace(" ", "")) for n in re.findall(r"-?\d{1,3}(?: \d{3})*(?:\.\d+)?", t)]


def _fmt(d: Decimal, places: int | None = None) -> str:
    """Thousands grouped by spaces, as the report prints them; `places` rounds (for display in a step only)."""
    if places is not None:
        d = d.quantize(Decimal(1).scaleb(-places))
    return f"{d:,}".replace(",", " ").replace("-", "−")


def _common(files: dict[str, InputFile]):
    with zipfile.ZipFile(files[BULK.key].path) as z:
        name, downloaded = member_name(z.namelist())
        raw = z.read(name)
    rows, legend = read_rows(raw)
    by = forest_area(rows, legend)
    report_rows(files[REPORT.key].path)
    flags = {f for years in by.values() for _, f in years.values()}
    n_flag = {f: sum(1 for years in by.values() if any(fl == f for _, fl in years.values())) for f in sorted(flags)}
    steps = [
        f"Read {name} from the FRA 2025 platform's bulk download (all countries and areas). The vintage is the "
        f"download date in the member names, {downloaded.isoformat()}; the platform has no other version label.",
        f"Kept {AREA_COL} (forest area, thousand hectares, as printed) and its flag for {len(by)} countries and areas "
        f"and the six reporting years {', '.join(map(str, YEARS))}. Flags: "
        + "; ".join(f'{f} "{legend[f]}" ({n} countries and areas)' for f, n in n_flag.items())
        + "; each country's values name their flag in a note.",
        "French Guiana, Mayotte, Réunion and Svalbard and Jan Mayen Islands are reported by FRA but have no entity "
        "here (Natural Earth draws them inside France or Norway): they are not published on their own and are "
        "counted in the world total.",
        f"World = the sum of the forest area of all {len(by)} countries and areas in the file for each year (exact "
        "decimal arithmetic), as FAO computes its global figure.",
    ]
    return by, legend, downloaded, steps


def _area_run(files: dict[str, InputFile]) -> Result:
    by, legend, downloaded, steps = _common(files)
    obs = area_observations(by, legend)
    world = {o.period: Decimal(str(o.value)) for o in obs if o.entity == "WLD"}
    report = _report_numbers(REPORT_TABLE_5[1])
    compare = "; ".join(f"{y}: report {_fmt(report[i])}, here {_fmt(world[str(y)], 2)}" for i, y in enumerate(YEARS))
    steps.append(
        f"For comparison only, the WORLD row of the report's Table 5 (PDF page {REPORT_TABLE_5[0]}, published "
        f"{REPORT_PUBLISHED}), in thousand ha: {compare}. The two differ slightly; the platform data can include "
        "country revisions made after the report was published."
    )
    return Result(
        observations=obs,
        vintage=f"FRA 2025 platform, downloaded {downloaded.isoformat()}",
        year=str(downloaded.year),
        date_published=REPORT_PUBLISHED,
        steps=steps,
        changes="world total calculated as the sum of all countries and areas.",
    )


def _net_change_run(files: dict[str, InputFile]) -> Result:
    by, legend, downloaded, steps = _common(files)
    obs = net_change_observations(by, legend)
    world = {o.period: Decimal(str(o.value)) for o in obs if o.entity == "WLD"}
    area_world = {y: sum(by[c][y][0] for c in by) for y in YEARS}
    report = _report_numbers(REPORT_TABLE_6[1])
    ours_2015_2025 = (area_world[2025] - area_world[2015]) / 10
    steps += [
        "Annual net change for each interval between reporting years = (forest area at the end − forest area at the "
        "start) / the number of years, in thousand hectares per year (exact decimal arithmetic); negative values are "
        "net loss. The report defines forest area net change the same way, as the difference in forest area between "
        "two points in time.",
        f"For comparison only, the WORLD row of the report's Table 6 (PDF page {REPORT_TABLE_6[0]}) gives the annual "
        f"net change as {_fmt(report[0])} thousand ha a year for 1990–2000 (here {_fmt(world['1990/2000'], 2)}) and "
        f"{_fmt(report[4])} for 2015–2025 (from the platform data used here, {_fmt(ours_2015_2025, 2)}; that 10-year "
        "interval is published here as 2015–2020 and 2020–2025). The platform data can include country revisions "
        "made after the report was published.",
    ]
    return Result(
        observations=obs,
        vintage=f"FRA 2025 platform, downloaded {downloaded.isoformat()}",
        year=str(downloaded.year),
        date_published=REPORT_PUBLISHED,
        steps=steps,
        changes="annual net change calculated from forest area; world total calculated as the sum of all countries "
        "and areas.",
    )


_GEOGRAPHY = "Countries and areas reporting to FRA 2025, and the world (sum of all 236)"
_BASIS = (
    "FRA definition of forest: land spanning more than 0.5 ha with trees higher than 5 m and a canopy cover of more "
    "than 10 percent, or trees able to reach these thresholds in situ, not predominantly under agricultural or urban "
    "land use. A land-use definition reported by countries (official data, or FAO desk studies where a country did "
    "not report), not satellite tree cover."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="forest.fao-fra-2025.area",
                title="Forest area",
                description="The area of forest in each country and in the world in 1990, 2000, 2010, 2015, 2020 "
                "and 2025, in thousands of hectares, as reported to FAO's Global Forest Resources Assessment 2025.",
                kind="series",
                unit=Unit(code="kha", label="thousand hectares", short="thousand ha"),
                display=Display(decimals=0),
                scope=Scope(geography=_GEOGRAPHY, basis=_BASIS),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=(BULK, REPORT),
            run=_area_run,
            module_file=here,
            validation=Validation(min_rows=1_300, value_range=(0.0, 5_000_000.0)),
        ),
        Transform(
            spec=Spec(
                id="forest.fao-fra-2025.net-change",
                title="Annual net change in forest area",
                description="How much the area of forest grew or shrank each year, on average, in each country and "
                "in the world over 1990–2000, 2000–2010, 2010–2015, 2015–2020 and 2020–2025: new forest from planting "
                "and natural expansion minus forest lost to deforestation, in thousands of hectares a year, from "
                "FAO's Global Forest Resources Assessment 2025. Negative values are net loss.",
                kind="derived",
                unit=Unit(code="kha-per-year", label="thousand hectares per year", short="thousand ha/yr"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis=_BASIS + " Net change = (forest area at the end of the interval − at its start) / years "
                    "in the interval. Net change is not deforestation: gains elsewhere offset part of the "
                    "forest lost.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=(BULK, REPORT),
            run=_net_change_run,
            module_file=here,
            validation=Validation(min_rows=1_100, value_range=(-15_000.0, 15_000.0)),
        ),
    ]

"""IRENA Renewable capacity statistics 2026: the world's installed renewable power capacity, by technology, and the
renewable share of all power capacity.

Input: the publication PDF (registry entry irena-capacity-2026, artifact capacity-statistics-pdf), 69 pages of
trilingual tables, one table per technology with a row per region and country and a column per year, 2016 to 2025,
in megawatts. The highlights PDF (artifact capacity-highlights-pdf) is read only to find the publisher's own
statements used as cross-checks below.

Reading. pypdf's layout mode keeps each table row on one line with the columns separated by two or more spaces, while
IRENA's thousands separator is a single space ("5 149 280"). A table starts on the page whose first line is its
English title; the "CAP (MW)" header line must list exactly the years 2016 to 2025, and the World row is the first
row after it. Each World cell must be an integer with single-space thousands groups (or, in the share table, a number
with one decimal); a cell with IRENA's source flag (o, u, e), a missing cell or anything else stops the build. World
cells carry no flag in this edition. Each title must start exactly one table.

Edition. The PDF's own metadata title must be "Renewable capacity statistics 2026" and page 2 must carry IRENA's
citation for it; the vintage is the PDF's creation date (2026-03-31), as the file has no version label and the server
sends no Last-Modified date.

Checks, or the build stops (each value is rounded to the nearest megawatt, so a sum of n values may be off by n/2):
- Total renewable energy equals the sum of renewable hydropower, marine, onshore wind, offshore wind, solar PV,
  concentrated solar power, bioenergy and geothermal, every year. That is what "by technology" adds up to, and it
  shows that pure pumped storage is not counted in IRENA's total (the highlights say so too);
- Wind energy equals onshore plus offshore; Solar energy equals solar PV plus concentrated solar power; Hydropower
  equals renewable hydropower plus pumped hydro.

Published: megawatts divided by 1,000, so gigawatts (exact decimal arithmetic); the share table as printed, in
percent. Capacity is maximum net generating capacity at the end of each year, not generation.

Publisher checks: the highlights PDF of the same edition (dated 31 March 2026, "Updated July 2026"): 5 149 GW in
total, 1 296 GW renewable hydropower, 154 GW bioenergy, 16 GW geothermal and 0.5 GW marine at the end of 2025, and
the renewable share of 46.3% in 2024 and 49.4% in 2025. Each quote must also be found in the highlights PDF's text.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pypdf

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "irena-capacity-2026"
PDF = Input(SOURCE, "capacity-statistics-pdf")
HIGHLIGHTS = Input(SOURCE, "capacity-highlights-pdf")
HIGHLIGHTS_URL = (
    "https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Mar/IRENA_DAT_RE_capacity_highlights_2026.pdf"
)
EDITION = "Renewable capacity statistics 2026"
CITATION = "IRENA (2026), Renewable capacity statistics 2026, International Renewable Energy Agency, Abu Dhabi."
YEARS = [str(y) for y in range(2016, 2026)]
VINTAGE = "2026-03-31"

TOTAL = "Total renewable energy"
SHARE = "Renewable energy share of electricity capacity"
# IRENA's English table title -> (our dimension value id, label). The order is the published order of the dimension.
TECHNOLOGIES: dict[str, tuple[str, str]] = {
    "Renewable hydropower": ("hydropower", "Hydropower (renewable, excluding pure pumped storage)"),
    "Marine energy": ("marine", "Marine energy"),
    "Onshore wind energy": ("onshore-wind", "Onshore wind"),
    "Offshore wind energy": ("offshore-wind", "Offshore wind"),
    "Solar photovoltaic": ("solar-pv", "Solar photovoltaic"),
    "Concentrated solar power": ("csp", "Concentrated solar power"),
    "Bioenergy": ("bioenergy", "Bioenergy"),
    "Geothermal energy": ("geothermal", "Geothermal energy"),
}
# Subtotals checked, never published: title -> its parts.
SUBTOTALS = {
    "Wind energy": ("Onshore wind energy", "Offshore wind energy"),
    "Solar energy": ("Solar photovoltaic", "Concentrated solar power"),
    "Hydropower": ("Renewable hydropower", "Pumped hydro"),
}
TITLES = (TOTAL, SHARE, *TECHNOLOGIES, *SUBTOTALS, "Pumped hydro")

_MW = re.compile(r"^\d{1,3}( \d{3})*$")
_PCT = re.compile(r"^\d{1,3}\.\d$")
_COLUMNS = re.compile(r"\s{2,}")


class IrenaFormatError(ValueError):
    pass


# --- reading ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WorldRow:
    title: str
    page: int
    """1-based PDF page."""
    values: dict[str, Decimal]
    """year -> megawatts (percent for the share table), as printed."""


def _cells(line: str) -> list[str]:
    return [c for c in _COLUMNS.split(line.strip()) if c]


def world_rows(pages: list[str]) -> dict[str, WorldRow]:
    """English table title -> its World row, for every title in TITLES, from layout-mode page texts."""
    found: dict[str, WorldRow] = {}
    for i, text in enumerate(pages):
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0].strip()
        if title not in TITLES:
            continue
        header = next((j for j, ln in enumerate(lines) if ln.strip().startswith("CAP (")), None)
        if header is None:
            raise IrenaFormatError(f"page {i + 1} ({title}): no CAP header line")
        head = _cells(lines[header])
        unit = "CAP (%MW)" if title == SHARE else "CAP (MW)"
        if head != [unit, *YEARS]:
            raise IrenaFormatError(f"page {i + 1} ({title}): header {head} != {[unit, *YEARS]}")
        row = _cells(lines[header + 1])
        if row[0] != "World":
            continue  # a continuation page of a table already started: its World row is on the first page
        if title in found:
            raise IrenaFormatError(f"{title!r} has a World row on pages {found[title].page} and {i + 1}")
        cells = row[1:]
        pattern = _PCT if title == SHARE else _MW
        if len(cells) != len(YEARS) or not all(pattern.fullmatch(c) for c in cells):
            raise IrenaFormatError(f"page {i + 1} ({title}): World row {row} is not {len(YEARS)} plain values")
        found[title] = WorldRow(
            title, i + 1, {y: Decimal(c.replace(" ", "")) for y, c in zip(YEARS, cells, strict=True)}
        )
    missing = [t for t in TITLES if t not in found]
    if missing:
        raise IrenaFormatError(f"no World row found for {missing}")
    return found


def check_sums(rows: dict[str, WorldRow]) -> None:
    def check(total: str, parts: tuple[str, ...]) -> None:
        for y in YEARS:
            s = sum((rows[p].values[y] for p in parts), Decimal(0))
            # Each printed value is rounded to the nearest megawatt.
            if abs(rows[total].values[y] - s) > Decimal(len(parts) + 1) / 2:
                raise IrenaFormatError(f"{total} {y}: {rows[total].values[y]} MW is not the sum of {parts} ({s})")

    check(TOTAL, tuple(TECHNOLOGIES))
    for total, parts in SUBTOTALS.items():
        check(total, parts)


def edition_of(pdf: bytes) -> datetime:
    """The PDF's creation date, after checking that it is this edition."""
    r = pypdf.PdfReader(io.BytesIO(pdf))
    meta = r.metadata or {}
    if meta.get("/Title") != EDITION:
        raise IrenaFormatError(f"PDF title {meta.get('/Title')!r} is not {EDITION!r}")
    if not textmatch.contains(r.pages[1].extract_text(), CITATION):
        raise IrenaFormatError("page 2 no longer carries the citation of this edition")
    raw = str(meta.get("/CreationDate", ""))
    m = re.match(r"^D:(\d{8})", raw)
    if not m:
        raise IrenaFormatError(f"PDF creation date {raw!r} is not readable")
    return datetime.strptime(m.group(1), "%Y%m%d")


@lru_cache(maxsize=1)
def _layout_pages(path: Path) -> tuple[str, ...]:
    # Content-addressed path (pipeline/.snapshots/<sha256>): the three indicators read the PDF once.
    r = pypdf.PdfReader(io.BytesIO(path.read_bytes()))
    return tuple(p.extract_text(extraction_mode="layout") for p in r.pages)


# --- observations -------------------------------------------------------------------------------------------------


GW_PER_MW = Decimal(1000)


def total_observations(rows: dict[str, WorldRow]) -> list[Observation]:
    return [Observation(entity="WLD", period=y, value=float(v / GW_PER_MW)) for y, v in rows[TOTAL].values.items()]


def technology_observations(rows: dict[str, WorldRow]) -> list[Observation]:
    return [
        Observation(entity="WLD", period=y, value=float(v / GW_PER_MW), dims={"technology": dim_id})
        for title, (dim_id, _) in TECHNOLOGIES.items()
        for y, v in rows[title].values.items()
    ]


def share_observations(rows: dict[str, WorldRow]) -> list[Observation]:
    return [Observation(entity="WLD", period=y, value=float(v)) for y, v in rows[SHARE].values.items()]


# --- publisher checks ---------------------------------------------------------------------------------------------


def _check(period: str, stated: str, quote: str, dims: tuple[tuple[str, str], ...] = ()) -> PublisherCheck:
    return PublisherCheck(
        source_id=SOURCE,
        vintage=VINTAGE,
        entity="WLD",
        period=period,
        stated=stated,
        quote=quote,
        url=HIGHLIGHTS_URL,
        dims=dims,
    )


Q_TOTAL = "At the end of 2025, global renewable power capacity amounted to 5 149 GW."
Q_HYDRO = "with total capacities of 1 296 GW and 1 291 GW, respectively."
Q_OTHER = "Other renewable capacities were: 154 GW of bioenergy; 16 GW of geothermal; and 0.5 GW of marine energy."
Q_SHARE = (
    "the renewable share of total installed power capacity rose by more than three percentage points from 46.3% in "
    "2024 to 49.4% in 2025."
)
CHECKS_TOTAL = (_check("2025", "5149", Q_TOTAL),)
CHECKS_TECH = (
    _check("2025", "1296", Q_HYDRO, (("technology", "hydropower"),)),
    _check("2025", "154", Q_OTHER, (("technology", "bioenergy"),)),
    _check("2025", "16", Q_OTHER, (("technology", "geothermal"),)),
    _check("2025", "0.5", Q_OTHER, (("technology", "marine"),)),
)
CHECKS_SHARE = (_check("2024", "46.3", Q_SHARE), _check("2025", "49.4", Q_SHARE))


def require_quotes(highlights: bytes) -> list[int]:
    """The 1-based highlights page of each publisher-check quote; stops if one is not there."""
    pages = textmatch.pdf_pages_text(highlights)
    out = []
    for q in (Q_TOTAL, Q_HYDRO, Q_OTHER, Q_SHARE):
        hit = [i + 1 for i, p in enumerate(pages) if textmatch.contains(p, q)]
        if not hit:
            raise IrenaFormatError(f"the highlights PDF no longer says {q!r}")
        out.append(hit[0])
    return out


# --- transforms ---------------------------------------------------------------------------------------------------


def _runner(compute, last: str, changes: str | None):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[PDF.key]
        created = edition_of(f.path.read_bytes())
        if created.date().isoformat() != VINTAGE:
            raise IrenaFormatError(f"PDF created {created.date()}, not {VINTAGE}: a new edition needs new checks")
        rows = world_rows(list(_layout_pages(f.path)))
        check_sums(rows)
        hl_pages = require_quotes(files[HIGHLIGHTS.key].path.read_bytes())
        used = sorted({rows[t].page for t in (TOTAL, SHARE, *TECHNOLOGIES, *SUBTOTALS)})
        return Result(
            observations=compute(rows),
            vintage=VINTAGE,
            date_published=VINTAGE,
            steps=[
                f"Read IRENA's {EDITION} (PDF created {created:%-d %B %Y}, sha256 {f.snapshot.sha256[:12]}…; its "
                "metadata title and the citation on page 2 name this edition) and took the World row of each table "
                f"from the text of pages {', '.join(str(p) for p in used)}, read with the columns kept apart, for "
                f"{YEARS[0]} to {YEARS[-1]}.",
                "Checked that Total renewable energy is the sum of renewable hydropower, marine, onshore and offshore "
                "wind, solar photovoltaic, concentrated solar power, bioenergy and geothermal in every year, and that "
                "the wind, solar and hydropower tables add up from their parts, each to within the rounding of the "
                "megawatt values. Pure pumped storage is not part of IRENA's renewable total.",
                f"Found the quotes used as publisher checks in the highlights PDF (pages "
                f"{', '.join(str(p) for p in sorted(set(hl_pages)))}).",
                last,
            ],
            changes=changes,
        )

    return run


GW = Unit(code="GW", label="gigawatts", short="GW")
BASIS = (
    "Maximum net generating capacity of renewable power plants installed and connected at the end of each year, as "
    "compiled by IRENA from official and unofficial sources and its own estimates. Capacity is not generation. "
    "Pure pumped storage hydropower and stationary batteries are not included. Values are revised in later editions."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (PDF, HIGHLIGHTS)
    convert = "converted from megawatts to gigawatts."
    return [
        Transform(
            spec=Spec(
                id="capacity.irena.renewables-world",
                title="World renewable power capacity",
                description="Total capacity of the world's renewable power plants (hydropower, wind, solar, "
                "bioenergy, geothermal and marine) at the end of each year since 2016, as compiled by IRENA.",
                kind="series",
                unit=GW,
                display=Display(decimals=0),
                scope=Scope(geography="World", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(total_observations, "Published Total renewable energy in gigawatts.", convert),
            module_file=here,
            validation=Validation(min_rows=10, value_range=(1000.0, 20000.0)),
            checks=CHECKS_TOTAL,
        ),
        Transform(
            spec=Spec(
                id="capacity.irena.renewables-by-technology-world",
                title="World renewable power capacity by technology",
                description="Capacity of the world's renewable power plants by technology (hydropower, marine, "
                "onshore and offshore wind, solar photovoltaic, concentrated solar power, bioenergy and geothermal) "
                "at the end of each year since 2016, as compiled by IRENA.",
                kind="series",
                unit=GW,
                display=Display(decimals=1),
                scope=Scope(geography="World", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="technology",
                        label="Technology",
                        values=[DimensionValue(id=i, label=lab) for i, lab in TECHNOLOGIES.values()],
                    ),
                ),
                headline_dims=(("technology", "solar-pv"),),
            ),
            inputs=inputs,
            run=_runner(
                technology_observations,
                "Published the eight technologies that make up IRENA's total, in gigawatts.",
                convert,
            ),
            module_file=here,
            validation=Validation(min_rows=80, value_range=(0.0, 10000.0)),
            checks=CHECKS_TECH,
        ),
        Transform(
            spec=Spec(
                id="capacity.irena.renewable-share-world",
                title="Renewables' share of world power capacity",
                description="The part of the world's installed electricity generating capacity that is renewable, "
                "at the end of each year since 2016, as published by IRENA.",
                kind="series",
                unit=Unit(code="percent", label="percent of total electricity generating capacity", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    basis="IRENA's 'Renewable energy share of electricity capacity': renewable capacity over the "
                    "capacity of all power plants at the end of the year. A share of capacity, not of generation.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=inputs,
            run=_runner(share_observations, "Published IRENA's share as printed (one decimal).", None),
            module_file=here,
            validation=Validation(min_rows=10, value_range=(0.0, 100.0)),
            checks=CHECKS_SHARE,
        ),
    ]

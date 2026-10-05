"""IRENA Renewable power generation costs in 2025: the global weighted-average levelised cost of electricity (LCOE) of
new renewable power projects, by technology, 2010 to 2025.

Input: the report's data file IRENA_TEC_RPGC_in_2025_data_file_2026.xlsx (registry entry irena-costs-2025, artifact
data-file), one sheet per figure or table of the report, and the executive summary PDF (artifact
executive-summary-pdf), read only for the publisher's own statements used as cross-checks.

Sheet read: "Fig S.2" (Figure S.2 "LCOE of renewable power technologies, 2010-2025"), whose unit cell reads
"LCOE (2025 USD/MWh)": a "Technology" header row with the years 2010 to 2025, then one row per technology. The title,
unit, header and the seven technology names below must be exactly where this edition has them, or the build stops.
Values are published as stored in the workbook (the figure shows them rounded); an empty cell is a null value (in
this edition only geothermal 2011).

Third-party data. The workbook's sheets "Fig. 9.5" and "Fig. 9.7" are labelled "Based on BNEF data", and IRENA's
terms say material attributed to third parties may be under separate terms. On every build the transform lists every
sheet whose first rows carry a "Based on ..." label and stops if the sheet it reads is one of them; no other sheet is
read.

Cross-checks inside the file, or the build stops: the "LCOE 2025 (USD/MWh)" row of sheet "Fig S.1" (whole dollars)
must equal each technology's 2025 value in "Fig S.2" rounded half up to a whole dollar. The workbook's Contents sheet
must cite this edition.

Vintage: the data file's HTTP Last-Modified date (2026-07-02); the workbook carries no version label.

Publisher checks: the 2025 values stated on page 5 of the executive summary, each quote also found in that PDF's text
at every build.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path

import openpyxl

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "irena-costs-2025"
DATA = Input(SOURCE, "data-file")
SUMMARY = Input(SOURCE, "executive-summary-pdf")
SUMMARY_URL = "https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Jul/IRENA_TEC_RPGC_2025_Executive_summary_2026.pdf"
VINTAGE = "2026-07-02"
CITATION = (
    "This data should be cited as: IRENA (2026), Renewable power generation costs in 2025, International Renewable "
    "Energy Agency, Abu Dhabi."
)

SHEET = "Fig S.2"
SHEET_TITLE = "Figure S.2 LCOE of renewable power technologies, 2010-2025"
UNIT_CELL = "LCOE (2025 USD/MWh)"
YEARS = list(range(2010, 2026))
SUMMARY_SHEET = "Fig S.1"
SUMMARY_ROW = "LCOE 2025 (USD/MWh)"

# Fig S.2 row label -> (our dimension value id, label, Fig S.1 column label). Order is the published order.
TECHNOLOGIES: dict[str, tuple[str, str, str]] = {
    "Solar photovoltaic": ("solar-pv", "Solar photovoltaic", "Solar Photovoltaic"),
    "Onshore wind": ("onshore-wind", "Onshore wind", "Onshore wind"),
    "Offshore wind": ("offshore-wind", "Offshore wind", "Offshore wind"),
    "Solar thermal": ("csp", "Concentrated solar power", "Concentrated Solar Power"),
    "Hydro": ("hydropower", "Hydropower", "Hydropower"),
    "Geothermal": ("geothermal", "Geothermal", "Geothermal"),
    "Bioenergy": ("bioenergy", "Bioenergy", "Bioenergy"),
}
THIRD_PARTY = re.compile(r"^Based on ")
LABEL_ROWS = 6


class IrenaCostsFormatError(ValueError):
    pass


# --- reading ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Workbook:
    lcoe: dict[str, dict[int, Decimal | None]]
    """Fig S.2 technology label -> year -> value."""
    whole: list[tuple[str, int]]
    """Cells of Fig S.2 stored as whole numbers (the others are stored at full precision)."""
    summary_2025: dict[str, Decimal]
    """Fig S.1 column label -> LCOE 2025 (whole dollars)."""
    third_party: dict[str, str]
    """sheet -> its "Based on ..." label."""
    cited: bool


def _rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _find(rows: list[list], value: object) -> tuple[int, int]:
    hits = [(i, j) for i, r in enumerate(rows) for j, v in enumerate(r) if v == value]
    if len(hits) != 1:
        raise IrenaCostsFormatError(f"{value!r} found {len(hits)} times, expected once")
    return hits[0]


def read_lcoe(rows: list[list]) -> tuple[dict[str, dict[int, Decimal | None]], list[tuple[str, int]]]:
    """Technology -> year -> value, and the (technology, year) cells stored as whole numbers."""
    if rows[0][0] != SHEET_TITLE:
        raise IrenaCostsFormatError(f"{SHEET}: title {rows[0][0]!r} != {SHEET_TITLE!r}")
    _find(rows, UNIT_CELL)
    hi, hj = _find(rows, "Technology")
    if rows[hi][hj + 1 : hj + 1 + len(YEARS)] != YEARS:
        raise IrenaCostsFormatError(f"{SHEET}: header {rows[hi][hj + 1 :]} is not the years {YEARS[0]}-{YEARS[-1]}")
    out: dict[str, dict[int, Decimal | None]] = {}
    whole: list[tuple[str, int]] = []
    for r in rows[hi + 1 :]:
        label = r[hj]
        if label is None:
            if any(v is not None for v in r):
                raise IrenaCostsFormatError(f"{SHEET}: a row with values and no technology: {r}")
            continue
        if label not in TECHNOLOGIES:
            raise IrenaCostsFormatError(f"{SHEET}: unexpected technology {label!r}")
        vals: dict[int, Decimal | None] = {}
        for y, v in zip(YEARS, r[hj + 1 : hj + 1 + len(YEARS)], strict=True):
            if v is not None and (isinstance(v, bool) or not isinstance(v, int | float)):
                raise IrenaCostsFormatError(f"{SHEET} {label} {y}: {v!r} is not a number")
            vals[y] = None if v is None else Decimal(repr(v))
            if isinstance(v, int):
                whole.append((label, y))
        out[label] = vals
    if set(out) != set(TECHNOLOGIES):
        raise IrenaCostsFormatError(f"{SHEET}: technologies {sorted(out)} != {sorted(TECHNOLOGIES)}")
    return out, whole


def read_summary(rows: list[list]) -> dict[str, Decimal]:
    mi, mj = _find(rows, "Metric")
    labels = rows[mi][mj + 1 :]
    ri, rj = _find(rows, SUMMARY_ROW)
    if rj != mj:
        raise IrenaCostsFormatError(f"{SUMMARY_SHEET}: {SUMMARY_ROW!r} is not in the Metric column")
    return {lab: Decimal(repr(v)) for lab, v in zip(labels, rows[ri][rj + 1 :], strict=False) if lab is not None}


def third_party_sheets(wb) -> dict[str, str]:
    out = {}
    for ws in wb.worksheets:
        for r in ws.iter_rows(max_row=LABEL_ROWS, values_only=True):
            for v in r:
                if isinstance(v, str) and THIRD_PARTY.match(v.strip()):
                    out[ws.title] = v.strip()
    return out


@lru_cache(maxsize=1)
def read_workbook(path: Path) -> Workbook:
    # Content-addressed path (pipeline/.snapshots/<sha256>).
    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
    contents = [v for r in wb["Contents"].iter_rows(max_row=10, values_only=True) for v in r if isinstance(v, str)]
    lcoe, whole = read_lcoe(_rows(wb[SHEET]))
    return Workbook(
        lcoe=lcoe,
        whole=whole,
        summary_2025=read_summary(_rows(wb[SUMMARY_SHEET])),
        third_party=third_party_sheets(wb),
        cited=CITATION in contents,
    )


def check_workbook(w: Workbook) -> None:
    if not w.cited:
        raise IrenaCostsFormatError(f"the Contents sheet no longer says {CITATION!r}")
    if SHEET in w.third_party or SUMMARY_SHEET in w.third_party:
        raise IrenaCostsFormatError(f"a sheet this module reads is labelled {w.third_party}")
    for label, (_, _, s1) in TECHNOLOGIES.items():
        v = w.lcoe[label][YEARS[-1]]
        stated = w.summary_2025.get(s1)
        if v is None or stated is None or v.quantize(Decimal(1), ROUND_HALF_UP) != stated:
            raise IrenaCostsFormatError(f"{label}: {SHEET} {YEARS[-1]} = {v}, but {SUMMARY_SHEET} says {stated}")


def vintage_of(last_modified: str | None) -> str:
    if not last_modified:
        raise IrenaCostsFormatError("the data file snapshot has no Last-Modified date, its only vintage")
    return parsedate_to_datetime(last_modified).date().isoformat()


# --- observations and checks --------------------------------------------------------------------------------------


def observations(w: Workbook) -> list[Observation]:
    obs = []
    for label, (dim_id, _, _) in TECHNOLOGIES.items():
        for y, v in w.lcoe[label].items():
            obs.append(
                Observation(
                    entity="WLD",
                    period=str(y),
                    value=None if v is None else float(v),
                    missing_reason=None if v is not None else f"IRENA's data file has no value for {label} in {y}.",
                    note=f"IRENA's workbook stores this value as the whole number {v}."
                    if (label, y) in w.whole
                    else None,
                    dims={"technology": dim_id},
                )
            )
    return obs


Q_PV = (
    "In 2025, the global, weighted-average levelised cost of electricity (LCOE) for solar PV remained unchanged "
    "compared to 2024, at USD 44 per megawatt hour (MWh)."
)
Q_WIND = "the LCOE of onshore wind decreased to USD 33/MWh and offshore wind to USD 78/MWh."
Q_DISPATCH = (
    "Hydropower rose to USD 62/MWh, geothermal to USD 89/MWh and concentrated solar power (CSP) to USD 115/MWh."
)
Q_BIO = "Bioenergy was the exception, with LCOE declining to USD 86/MWh due to increased output."
QUOTES = (Q_PV, Q_WIND, Q_DISPATCH, Q_BIO)
SUMMARY_PAGE = 5


def _check(dim: str, stated: str, quote: str) -> PublisherCheck:
    return PublisherCheck(
        source_id=SOURCE,
        vintage=VINTAGE,
        entity="WLD",
        period="2025",
        stated=stated,
        quote=quote,
        url=SUMMARY_URL,
        dims=(("technology", dim),),
    )


CHECKS = (
    _check("solar-pv", "44", Q_PV),
    _check("onshore-wind", "33", Q_WIND),
    _check("offshore-wind", "78", Q_WIND),
    _check("hydropower", "62", Q_DISPATCH),
    _check("geothermal", "89", Q_DISPATCH),
    _check("csp", "115", Q_DISPATCH),
    _check("bioenergy", "86", Q_BIO),
)


def require_quotes(pdf: bytes) -> None:
    pages = textmatch.pdf_pages_text(pdf)
    for q in QUOTES:
        if not textmatch.contains(pages[SUMMARY_PAGE - 1], q):
            raise IrenaCostsFormatError(f"page {SUMMARY_PAGE} of the executive summary no longer says {q!r}")


# --- transform ----------------------------------------------------------------------------------------------------


def run(files: dict[str, InputFile]) -> Result:
    f = files[DATA.key]
    w = read_workbook(f.path)
    check_workbook(w)
    require_quotes(files[SUMMARY.key].path.read_bytes())
    vintage = vintage_of(f.snapshot.last_modified)
    labelled = "; ".join(f"'{s}' ({lab})" for s, lab in sorted(w.third_party.items())) or "none"
    return Result(
        observations=observations(w),
        vintage=vintage,
        date_published=vintage,
        steps=[
            f"Read sheet '{SHEET}' ({SHEET_TITLE}, unit '{UNIT_CELL}') of IRENA's data file for Renewable power "
            f"generation costs in 2025, last modified on {vintage} (sha256 {f.snapshot.sha256[:12]}…), whose "
            "Contents sheet cites this edition. Values are taken as stored in the workbook, one per technology and "
            f"year, {YEARS[0]}–{YEARS[-1]}; an empty cell is published as a null value.",
            "Sheets labelled as based on third-party data, which are never read: " + labelled + ".",
            f"Checked that sheet '{SUMMARY_SHEET}' row '{SUMMARY_ROW}' equals each technology's {YEARS[-1]} value "
            "rounded to a whole dollar, and found the executive summary's statements of the 2025 values on its page "
            f"{SUMMARY_PAGE}.",
            "Published the global weighted averages as stored. 'Solar thermal' in the sheet is concentrated solar "
            "power (the summary sheet's label).",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="lcoe.irena.by-technology-world",
                title="Cost of electricity from new renewable power plants",
                description="The average lifetime cost of each megawatt-hour of electricity from renewable power "
                "projects that started operating each year since 2010, by technology, worldwide, in 2025 US dollars, "
                "as calculated by IRENA.",
                kind="series",
                unit=Unit(
                    code="USD2025/MWh",
                    label="US dollars per megawatt-hour, at 2025 prices",
                    short="USD/MWh",
                ),
                display=Display(decimals=0),
                scope=Scope(
                    geography="World (projects commissioned in each year)",
                    basis="Global weighted-average levelised cost of electricity (LCOE) of utility-scale projects "
                    "commissioned in the year, in real 2025 US dollars, from IRENA's cost database, with IRENA's "
                    "standard assumptions for the cost of capital and economic life. Excludes the cost of "
                    "integrating variable power into grids. Weighted by capacity; wide differences between countries "
                    "and projects lie behind each average.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="technology",
                        label="Technology",
                        values=[DimensionValue(id=i, label=lab) for i, lab, _ in TECHNOLOGIES.values()],
                    ),
                ),
                headline_dims=(("technology", "solar-pv"),),
            ),
            inputs=(DATA, SUMMARY),
            run=run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(TECHNOLOGIES) * len(YEARS), value_range=(5.0, 1000.0)),
            checks=CHECKS,
        )
    ]

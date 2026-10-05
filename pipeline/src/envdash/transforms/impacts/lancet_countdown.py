"""Lancet Countdown 2025 report: global heat-related deaths (1.1.5), potential work hours lost to heat (1.1.3) and
heatwave days per person observed and attributable to climate change (1.1.1).

Inputs: the indicator workbooks of source lancet-countdown-2025. Each has a DATA GUIDANCE sheet (report, indicator,
the report's key finding, column units, licence and suggested citation) and one sheet per geography; only the
Global sheet is read here.

Vintage. The guidance sheet names the report ("The 2025 report of the Lancet Countdown on health and climate
change"). The vintage is "<year> report". A report year other than REPORT_YEAR stops the build: each report is its
own registry entry (indicator methods change between reports, so vintages are never spliced). The suggested
citation printed in the workbook must equal the registry's citation text, and the report's publication date is
read from it ("published online Oct 29").

Units. Each value column's unit is read from the guidance sheet's column table and must be what this module
assumes: AN "Deaths"; the work-hours-lost columns "Hours in 1000s"; Observed, Counterfactual and
Attributable_to_CC "days". A changed unit or column header stops the build until a person re-reads the workbook.

Values. Deaths and heatwave days are published as in the Global sheet. Work hours lost are divided by one million
(exact decimal arithmetic on the stored digits) to give billions of hours, the unit of the report's own statement.
Two identities of the files are checked rather than assumed: TotalSunAgCon equals the sum of the four sector
columns, and Observed equals Counterfactual plus Attributable_to_CC.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "lancet-countdown-2025"
REPORT_YEAR = 2025
VINTAGE = f"{REPORT_YEAR} report"
MORTALITY = Input(SOURCE, "heat-mortality-1-1-5")
WORK_HOURS = Input(SOURCE, "work-hours-lost-1-1-3")
HEATWAVE = Input(SOURCE, "heatwave-days-attributable-1-1-1")

REPORT = re.compile(r"The (\d{4}) report of the Lancet Countdown on health and climate change")
CITATION = (
    "Romanello M, Walawender M, Hsu S-C, et al. The 2025 report of the Lancet Countdown on health and climate "
    "change. Lancet 2025; published online Oct 29. https://doi.org/10.1016/S0140-6736(25)01919-1."
)
PUBLISHED_ONLINE = re.compile(r"Lancet (\d{4}); published online ([A-Z][a-z]{2} \d{1,2})\.")


class LancetFormatError(ValueError):
    pass


# --- reading the workbooks ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Guidance:
    report_year: int
    indicator: str
    key_finding: str
    citation: str
    published: date
    units: dict[str, str]
    """Column header (as printed in the guidance table, stripped) -> its Units cell."""


def _cells(row: tuple) -> list:
    return [c for c in row if c is not None and not (isinstance(c, str) and not c.strip())]


def _after(rows: list[list], heading: str) -> list:
    for i, r in enumerate(rows):
        if r and isinstance(r[0], str) and r[0].strip() == heading:
            for nxt in rows[i + 1 :]:
                if nxt:
                    return nxt
    raise LancetFormatError(f"DATA GUIDANCE has no {heading!r} section")


def read_guidance(wb: openpyxl.Workbook) -> Guidance:
    if "DATA GUIDANCE" not in wb.sheetnames:
        raise LancetFormatError(f"no DATA GUIDANCE sheet in {wb.sheetnames}")
    rows = [_cells(r) for r in wb["DATA GUIDANCE"].iter_rows(values_only=True)]
    fields = {r[0].strip(): r[1] for r in rows if len(r) == 2 and isinstance(r[0], str)}
    m = REPORT.fullmatch(str(fields.get("Report", "")).strip())
    if not m:
        raise LancetFormatError(f"DATA GUIDANCE Report is {fields.get('Report')!r}; expected {REPORT.pattern!r}")
    key_finding = _after(rows, "1. Report Key Findings")
    citation = _after(rows, "3. Suggested Citation")
    if len(key_finding) != 1 or len(citation) != 1:
        raise LancetFormatError("DATA GUIDANCE key finding and suggested citation should each be one cell")
    cite = str(citation[0]).strip()
    pm = PUBLISHED_ONLINE.search(cite)
    if not pm:
        raise LancetFormatError(f"cannot read the publication date from the suggested citation {cite!r}")
    published = datetime.strptime(f"{pm.group(2)} {pm.group(1)}", "%b %d %Y").date()
    units: dict[str, str] = {}
    for r in rows:
        if len(r) == 4 and isinstance(r[0], str) and re.fullmatch(r"[A-Z]", r[0].strip()):
            units[str(r[1]).strip()] = str(r[2]).strip()
    return Guidance(
        report_year=int(m.group(1)),
        indicator=str(fields.get("Indicator", "")).strip(),
        key_finding=str(key_finding[0]).strip(),
        citation=cite,
        published=published,
        units=units,
    )


def _open(raw: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)


def _check_guidance(g: Guidance, indicator: str, units: dict[str, str], name: str) -> None:
    if g.report_year != REPORT_YEAR:
        raise LancetFormatError(
            f"{name}: workbook is from the {g.report_year} report; {SOURCE} holds the {REPORT_YEAR} report. A new "
            "report is a new registry entry."
        )
    if g.citation != CITATION:
        raise LancetFormatError(f"{name}: suggested citation changed to {g.citation!r}")
    if g.indicator != indicator:
        raise LancetFormatError(f"{name}: workbook is {g.indicator!r}, expected {indicator!r}")
    for col, unit in units.items():
        if g.units.get(col) != unit:
            raise LancetFormatError(f"{name}: guidance gives column {col!r} units {g.units.get(col)!r}, not {unit!r}")


def read_table(wb: openpyxl.Workbook, sheet: str, columns: tuple[str, ...], name: str) -> list[tuple]:
    if sheet not in wb.sheetnames:
        raise LancetFormatError(f"{name}: no sheet {sheet!r} in {wb.sheetnames}")
    rows = list(wb[sheet].iter_rows(values_only=True))
    if not rows or tuple(rows[0]) != columns:
        raise LancetFormatError(f"{name}: {sheet!r} columns {rows[0] if rows else None} != expected {columns}")
    out = []
    for r in rows[1:]:
        if any(c is None for c in r):
            raise LancetFormatError(f"{name}: {sheet!r} row {r} has an empty cell")
        if not isinstance(r[0], int) or isinstance(r[0], bool):
            raise LancetFormatError(f"{name}: {sheet!r} Year {r[0]!r} is not a whole number")
        if any(not isinstance(c, int | float) or isinstance(c, bool) for c in r[1:]):
            raise LancetFormatError(f"{name}: {sheet!r} row {r} has a non-numeric value")
        out.append(tuple(r))
    years = [r[0] for r in out]
    if years != sorted(set(years)):
        raise LancetFormatError(f"{name}: {sheet!r} years are not unique and increasing")
    return out


def dec(x: int | float) -> Decimal:
    """The number as stored in the workbook (shortest repr of the double), as an exact decimal."""
    return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


# --- 1.1.5 heat-related deaths ------------------------------------------------------------------------------------

MORTALITY_SHEET = "2025 Report Data_Global"
MORTALITY_COLUMNS = ("Year", "AF", "AN")


def parse_mortality(raw: bytes) -> tuple[list[Observation], Guidance]:
    wb = _open(raw)
    g = read_guidance(wb)
    _check_guidance(g, "Indicator 1.1.5: Heat Related Mortality", {"AN": "Deaths", "AF": "%"}, "1.1.5")
    rows = read_table(wb, MORTALITY_SHEET, MORTALITY_COLUMNS, "1.1.5")
    obs = []
    for year, _af, an in rows:
        if not isinstance(an, int):
            raise LancetFormatError(f"1.1.5: AN for {year} is {an!r}, not a whole number of deaths")
        obs.append(Observation(entity="WLD", period=f"{year:04d}", value=float(an)))
    return obs, g


def _mortality(files: dict[str, InputFile]) -> Result:
    obs, g = parse_mortality(files[MORTALITY.key].path.read_bytes())
    return Result(
        observations=obs,
        vintage=VINTAGE,
        year=str(g.report_year),
        date_published=g.published.isoformat(),
        steps=[
            f"Read the AN column (number of deaths attributable to heat) of the sheet {MORTALITY_SHEET!r} of the "
            f"indicator 1.1.5 workbook of the Lancet Countdown {g.report_year} report, one value a year "
            f"{obs[0].period}–{obs[-1].period}. Values are published as in the workbook.",
            "The workbook's guidance sheet gives the unit of AN as deaths. The share of all deaths (AF) and the "
            "regional sheets are not published here.",
        ],
    )


# --- 1.1.3 potential work hours lost ------------------------------------------------------------------------------

WORK_SHEET = "2025 Report Data_Global"
WORK_COLUMNS = (
    "Year",
    "EmplPop15+",
    "WHL200Serv",
    "WHL300Manuf",
    "WHL400sunAgr",
    "WHL400sunConstr",
    "TotalSunAgCon",
    "TotalSunWHLpp",
)
# (dimension value, label, Global-sheet column, column header as printed in the guidance table)
SECTORS = (
    ("total", "All four sectors", "TotalSunAgCon", "TotalsunAgCon"),
    ("services", "Services (indoors or in shade)", "WHL200Serv", "WHL200Serv"),
    ("manufacturing", "Manufacturing (indoors or in shade)", "WHL300Manuf", "WHL300Manuf"),
    ("agriculture", "Agriculture (in the sun)", "WHL400sunAgr", "WHL400sunAgr"),
    ("construction", "Construction (in the sun)", "WHL400sunConstr", "WHL400sunConstr"),
)
THOUSANDS_PER_BILLION = Decimal(1_000_000)


def parse_work_hours(raw: bytes) -> tuple[list[Observation], Guidance]:
    wb = _open(raw)
    g = read_guidance(wb)
    _check_guidance(
        g,
        "Indicator 1.1.3: Change in Labour Capacity",
        {guide: "Hours in 1000s" for *_, guide in SECTORS},
        "1.1.3",
    )
    rows = read_table(wb, WORK_SHEET, WORK_COLUMNS, "1.1.3")
    idx = {c: i for i, c in enumerate(WORK_COLUMNS)}
    by_sector: dict[str, list[Observation]] = {s: [] for s, *_ in SECTORS}
    for r in rows:
        thousands = {col: dec(r[idx[col]]) for _, _, col, _ in SECTORS}
        parts = sum((thousands[c] for c in ("WHL200Serv", "WHL300Manuf", "WHL400sunAgr", "WHL400sunConstr")), Decimal())
        if abs(parts - thousands["TotalSunAgCon"]) > thousands["TotalSunAgCon"] * Decimal("1e-9"):
            raise LancetFormatError(
                f"1.1.3: {r[0]} TotalSunAgCon {thousands['TotalSunAgCon']} is not the sum of the four sectors {parts}"
            )
        for sector, _, col, _ in SECTORS:
            by_sector[sector].append(
                Observation(
                    entity="WLD",
                    period=f"{r[0]:04d}",
                    value=float(thousands[col] / THOUSANDS_PER_BILLION),
                    dims={"sector": sector},
                )
            )
    return [o for s, *_ in SECTORS for o in by_sector[s]], g


def _work_hours(files: dict[str, InputFile]) -> Result:
    obs, g = parse_work_hours(files[WORK_HOURS.key].path.read_bytes())
    years = sorted({o.period for o in obs})
    return Result(
        observations=obs,
        vintage=VINTAGE,
        year=str(g.report_year),
        date_published=g.published.isoformat(),
        steps=[
            f"Read the sheet {WORK_SHEET!r} of the indicator 1.1.3 workbook of the Lancet Countdown {g.report_year} "
            f"report, {years[0]}–{years[-1]}: potential work hours lost in services (WHL200Serv), manufacturing "
            "(WHL300Manuf), agriculture (WHL400sunAgr), construction (WHL400sunConstr) and in total (TotalSunAgCon), "
            "in thousands of hours as the guidance sheet states.",
            "Checked that the total equals the sum of the four sectors in every year (to one part in a billion).",
            "Divided every value by one million to give billions of hours (exact decimal arithmetic on the values "
            "as stored in the workbook). Employment and hours lost per worker are not published here.",
        ],
        changes="work hours lost converted from thousands of hours to billions of hours.",
    )


# --- 1.1.1 heatwave days attributable to climate change -----------------------------------------------------------

HEATWAVE_SHEET = "2025_Report _Data_Global"
HEATWAVE_COLUMNS = ("Year", "Observed", "Counterfactual", "Attributable_to_CC")
SCENARIOS = (
    ("observed", "Observed", "Observed"),
    ("counterfactual", "Expected without human-caused climate change", "Counterfactual"),
    ("attributable", "Attributable to climate change", "Attributable_to_CC"),
)


def parse_heatwave(raw: bytes) -> tuple[list[Observation], Guidance]:
    wb = _open(raw)
    g = read_guidance(wb)
    _check_guidance(
        g,
        "Indicator 1.1.1: Exposure of Vulnerable Populations to Heatwaves -- attributable heatwave days",
        {"Observed": "days", "Counterfactual": "days", "Attributable_to_CC": "days"},
        "1.1.1",
    )
    rows = read_table(wb, HEATWAVE_SHEET, HEATWAVE_COLUMNS, "1.1.1")
    by: dict[str, list[Observation]] = {s: [] for s, *_ in SCENARIOS}
    for year, observed, counterfactual, attributable in rows:
        o, c, a = dec(observed), dec(counterfactual), dec(attributable)
        if abs(o - c - a) > Decimal("1e-9"):
            raise LancetFormatError(f"1.1.1: {year} Observed {o} != Counterfactual {c} + Attributable_to_CC {a}")
        for scenario, value in (("observed", o), ("counterfactual", c), ("attributable", a)):
            by[scenario].append(
                Observation(entity="WLD", period=f"{year:04d}", value=float(value), dims={"scenario": scenario})
            )
    return [o for s, *_ in SCENARIOS for o in by[s]], g


def _heatwave(files: dict[str, InputFile]) -> Result:
    obs, g = parse_heatwave(files[HEATWAVE.key].path.read_bytes())
    years = sorted({o.period for o in obs})
    return Result(
        observations=obs,
        vintage=VINTAGE,
        year=str(g.report_year),
        date_published=g.published.isoformat(),
        steps=[
            f"Read the sheet {HEATWAVE_SHEET!r} of the indicator 1.1.1 (attributable heatwave days) workbook of the "
            f"Lancet Countdown {g.report_year} report, {years[0]}–{years[-1]}: heatwave days observed, expected "
            "without climate change (Counterfactual) and attributable to climate change (Attributable_to_CC), "
            "published as in the workbook.",
            "Checked that observed days equal expected days plus attributable days in every year.",
        ],
    )


# --- transforms ---------------------------------------------------------------------------------------------------


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="heat.lancet-2025.deaths-global",
                title="Heat-related deaths, world",
                description="Deaths attributable to heat each year worldwide, 1990–2021, as estimated by the Lancet "
                "Countdown (indicator 1.1.5). The numbers are modelled from temperature–mortality relationships, "
                "not counted.",
                kind="series",
                unit=Unit(code="deaths", label="deaths", short="deaths"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="World",
                    basis="Modelled in three stages (Zhao et al. 2021): the association between temperature and "
                    "mortality estimated in each location, pooled by multilevel meta-regression, and predicted for "
                    "all countries. Inputs include ERA5 temperatures, UN population data, the World Mortality "
                    "Dataset and the Global Burden of Disease Study 2021.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(MORTALITY,),
            run=_mortality,
            module_file=here,
            validation=Validation(min_rows=32, value_range=(1.0, 5_000_000.0)),
        ),
        Transform(
            spec=Spec(
                id="heat.lancet-2025.labour-hours-global",
                title="Potential work hours lost to heat, world",
                description="Working hours that heat stress could have cost each year worldwide, 1990–2024, in "
                "services, manufacturing, agriculture and construction, as estimated by the Lancet Countdown "
                "(indicator 1.1.3).",
                kind="series",
                unit=Unit(code="bn-hours", label="billion hours", short="bn hours"),
                display=Display(decimals=1),
                dimensions=(
                    Dimension(
                        id="sector",
                        label="Sector",
                        values=[DimensionValue(id=s, label=label) for s, label, *_ in SECTORS],
                    ),
                ),
                scope=Scope(
                    geography="World",
                    basis="Potential hours lost: wet bulb globe temperature from ERA5 linked to the metabolic rate "
                    "of typical work (services 200 W and manufacturing 300 W in shade, agriculture and construction "
                    "400 W in the sun), applied to employed people aged 15 and over in each sector. Formal "
                    "employment only. The producer notes that from 2020 grid cells shared between countries are "
                    "handled differently, which may show as a step between 2019 and 2020.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                headline_dims=(("sector", "total"),),
            ),
            inputs=(WORK_HOURS,),
            run=_work_hours,
            module_file=here,
            validation=Validation(min_rows=5 * 35, value_range=(0.0, 5000.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity="WLD",
                    period="2024",
                    stated="640",
                    quote="A record-high 640 billion potential work hours were lost in 2024",
                    url="https://lancetcountdown.org/wp-content/uploads/2025/10/"
                    "Indicator-1.1.3_PWHL_Data-Download_2025-Lancet-Countdown-Report_v2-1.xlsx",
                    dims=(("sector", "total"),),
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id="heat.lancet-2025.heatwave-days-global",
                title="Heatwave days per person, observed and attributable to climate change, world",
                description="Heatwave days that people were exposed to on average each year, 2020–2024, as "
                "observed, as expected in a modelled climate without human-caused warming, and the difference "
                "attributable to climate change, from the Lancet Countdown (indicator 1.1.1).",
                kind="series",
                unit=Unit(code="days", label="days per person", short="days"),
                display=Display(decimals=1),
                dimensions=(
                    Dimension(
                        id="scenario",
                        label="Scenario",
                        values=[DimensionValue(id=s, label=label) for s, label, _ in SCENARIOS],
                    ),
                ),
                scope=Scope(
                    geography="World",
                    basis="A heatwave is at least two consecutive days when both minimum and maximum temperature "
                    "exceed the local 1986–2005 95th percentile. Observed days from ERA5; days expected without "
                    "human-caused warming from 24 paired CMIP6 climate model simulations.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                headline_dims=(("scenario", "observed"),),
            ),
            inputs=(HEATWAVE,),
            run=_heatwave,
            module_file=here,
            validation=Validation(min_rows=3 * 5, value_range=(0.0, 366.0)),
        ),
    ]

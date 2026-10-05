"""IMBIE 2026: cumulative mass change of the Greenland and Antarctic ice sheets, in Gt and as sea-level contribution.

Inputs: imbie3_greenland_{Gt,mm}_partitioned.csv and imbie3_antarctica_{Gt,mm}_partitioned.csv (UK Polar Data Centre,
doi:10.5285/128c5e33-5224-4197-82f0-19dcc95b80a0). Each is a '#' header (CF-style attributes) and one row per month:
rates, cumulative anomalies and their one-sigma uncertainties for total, surface mass balance and ice dynamics.
Greenland runs July 1971 to December 2023, Antarctica January 1979 to December 2023.

Four indicators, one per ice sheet and unit, so each has one start date as its baseline:
- ice-sheet-mass.imbie-2026.{greenland,antarctica}: the "Cumulative mass balance anomaly (Gt)" column as printed,
  with lower/upper = value ∓ "Cumulative mass balance anomaly uncertainty (Gt)" (exact decimals). The header says
  "The respective one sigma uncertainties for each reconciled dataset are provided", so the interval is 1sigma.
  Negative means the ice sheet lost mass.
- sea-level-contribution.imbie-2026.{greenland,antarctica}: the same column of the mm file, with its sign flipped
  so that a positive value is a rise in global mean sea level. The data paper (Otosaka et al. 2026, Scientific Data
  13, 1301) says the mm files assume "that 360 Gt of ice lost is equivalent to 1 mm sea level rise". The build checks
  on every row that the mm value equals the Gt value divided by 360 (to 1e-8 mm, the files' printed precision) for
  both the value and its uncertainty: that is what shows the mm column carries the mass-balance sign (mass loss is
  negative), so negating it gives the contribution to sea level.

Each cumulative value already includes its own month: the first Greenland row (1971-07) is 65.9465 / 12 = 5.4955 Gt,
one month at the first yearly rate. So the baseline is zero just before the first month of each record.

Header checks (the build stops if they change): "# data_type:" must name the ice sheet and unit of the artifact,
"# time_coverage_start/end" must equal the first and last rows, rows must be consecutive months, and the citation line
must carry "(Version 1.0)", which is the vintage.

Publisher check: the paper's "the Antarctic Ice Sheet lost 4,780 ± 513 Gt of ice between 1979 and 2023, raising the
global sea level by 13.3 ± 1.4 mm" (the mm figure; the Gt figure is printed as a loss, without a sign, and the file's
-4779.472 Gt rounds to 4,779, so it is not used as a check). The paper's Greenland total, "6,215 ± 467 Gt of ice
... between 1972 and 2023", matches neither the file's December 2023 value (-6196.146 Gt since July 1971) nor that
value less the 1971 months (-6229.119 Gt), so no Greenland check is made; the file is what is published.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime
from itertools import pairwise
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "imbie-2026"
PAPER_URL = "https://www.nature.com/articles/s41597-026-08088-0"
GT_PER_MM = Decimal(360)
MM_TOLERANCE = Decimal("1e-8")
SIGMA_STATEMENT = "The respective one sigma uncertainties for each reconciled dataset are provided."
VERSION = re.compile(r"\(Version (\d+\.\d+)\)")

GT = Unit(code="Gt", label="gigatonnes", short="Gt")
MM = Unit(code="mm", label="millimetres", short="mm")


@dataclass(frozen=True)
class Sheet:
    key: str
    name: str
    data_name: str
    entity: str
    start: str
    geography: str
    estimates: int
    """Independent estimates combined, from the files' '# history:' line ("21 estimates for Antarctica and 24
    estimates for Greenland")."""

    @property
    def gt(self) -> Input:
        return Input(SOURCE, f"{self.key}-gt")

    @property
    def mm(self) -> Input:
        return Input(SOURCE, f"{self.key}-mm")


GREENLAND = Sheet("greenland", "Greenland", "Greenland", "GRL", "July 1971", "Greenland Ice Sheet", 24)
ANTARCTICA = Sheet(
    "antarctica",
    "Antarctic",
    "Antarctica",
    "ATA",
    "January 1979",
    "Antarctic Ice Sheet (West and East Antarctica and the Antarctic Peninsula)",
    21,
)
HISTORY = "21 estimates for Antarctica and 24 estimates for Greenland"


class ImbieFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    period: str
    value: Decimal
    sigma: Decimal


@dataclass(frozen=True)
class Table:
    rows: list[Row]
    version: str
    coverage_start: str
    coverage_end: str


def _header(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in text.splitlines():
        if not ln.startswith("#"):
            break
        k, _, v = ln[1:].partition(":")
        out.setdefault(k.strip(), v.strip())
    return out


def read_table(raw: bytes, sheet: Sheet, unit: str) -> Table:
    text = raw.decode("utf-8")
    head = _header(text)
    if head.get("data_type") != f"{sheet.data_name} {unit}":
        raise ImbieFormatError(f"data_type {head.get('data_type')!r} != {sheet.data_name} {unit!r}")
    if SIGMA_STATEMENT not in text:
        raise ImbieFormatError("the header no longer states that the uncertainties are one sigma")
    if HISTORY not in head.get("history", ""):
        raise ImbieFormatError(f"the history line no longer says {HISTORY!r}")
    m = VERSION.search(head.get("citation", ""))
    if not m:
        raise ImbieFormatError("no '(Version x.y)' in the citation line")
    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(body)))
    value_col = f"Cumulative mass balance anomaly ({unit})"
    sigma_col = f"Cumulative mass balance anomaly uncertainty ({unit})"
    if reader.fieldnames is None or value_col not in reader.fieldnames or sigma_col not in reader.fieldnames:
        raise ImbieFormatError(f"columns {reader.fieldnames} lack {value_col!r} or {sigma_col!r}")
    rows: list[Row] = []
    for r in reader:
        d = r["Date"]
        if not re.fullmatch(r"\d{4}-\d{2}-01", d):
            raise ImbieFormatError(f"Date {d!r} is not the first of a month")
        rows.append(Row(d[:7], Decimal(r[value_col]), Decimal(r[sigma_col])))
    return Table(rows, m.group(1), head.get("time_coverage_start", ""), head.get("time_coverage_end", ""))


def check_months(t: Table) -> None:
    """Rows are consecutive months from time_coverage_start to time_coverage_end."""
    for a, b in pairwise(t.rows):
        y, mo = int(a.period[:4]), int(a.period[5:])
        nxt = f"{y + mo // 12:04d}-{mo % 12 + 1:02d}"
        if b.period != nxt:
            raise ImbieFormatError(f"months not consecutive: {a.period} then {b.period}")
    if f"{t.rows[0].period}-01" != t.coverage_start or f"{t.rows[-1].period}-01" != t.coverage_end:
        raise ImbieFormatError("first/last rows do not match time_coverage_start/end")


def read_checked(raw: bytes, sheet: Sheet, unit: str) -> Table:
    t = read_table(raw, sheet, unit)
    check_months(t)
    return t


def mass_observations(t: Table, sheet: Sheet) -> list[Observation]:
    return [
        Observation(
            entity=sheet.entity,
            period=r.period,
            value=float(r.value),
            lower=float(r.value - r.sigma),
            upper=float(r.value + r.sigma),
            interval="1sigma",
        )
        for r in t.rows
    ]


def sea_level_observations(gt: Table, mm: Table, sheet: Sheet) -> list[Observation]:
    if [r.period for r in gt.rows] != [r.period for r in mm.rows]:
        raise ImbieFormatError(f"{sheet.key}: the Gt and mm files cover different months")
    for g, m in zip(gt.rows, mm.rows, strict=True):
        if abs(g.value / GT_PER_MM - m.value) > MM_TOLERANCE or abs(g.sigma / GT_PER_MM - m.sigma) > MM_TOLERANCE:
            raise ImbieFormatError(f"{sheet.key} {g.period}: mm {m.value} ± {m.sigma} is not Gt/360 ({g.value})")
    return [
        Observation(
            entity=sheet.entity,
            period=r.period,
            value=float(-r.value),
            lower=float(-r.value - r.sigma),
            upper=float(-r.value + r.sigma),
            interval="1sigma",
        )
        for r in mm.rows
    ]


def _published(f: InputFile) -> str | None:
    lm = f.snapshot.last_modified
    return parsedate_to_datetime(lm).date().isoformat() if lm else None


def _mass_run(sheet: Sheet):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[sheet.gt.key]
        t = read_checked(f.path.read_bytes(), sheet, "Gt")
        return Result(
            observations=mass_observations(t, sheet),
            vintage=t.version,
            date_published=_published(f),
            steps=[
                f"Read the 'Cumulative mass balance anomaly (Gt)' column of imbie3_{sheet.key}_Gt_partitioned.csv "
                f"(IMBIE version {t.version}), {t.rows[0].period} to {t.rows[-1].period}, as printed.",
                "Lower and upper are the value minus and plus the file's 'Cumulative mass balance anomaly "
                "uncertainty (Gt)', which the file states is one standard deviation (exact decimal arithmetic).",
            ],
        )

    return run


def _sea_level_run(sheet: Sheet):
    def run(files: dict[str, InputFile]) -> Result:
        fg, fm = files[sheet.gt.key], files[sheet.mm.key]
        gt = read_checked(fg.path.read_bytes(), sheet, "Gt")
        mm = read_checked(fm.path.read_bytes(), sheet, "mm")
        if gt.version != mm.version:
            raise ImbieFormatError(f"Gt file is version {gt.version}, mm file {mm.version}")
        return Result(
            observations=sea_level_observations(gt, mm, sheet),
            vintage=mm.version,
            date_published=_published(fm),
            steps=[
                f"Read the 'Cumulative mass balance anomaly (mm)' column and its uncertainty from "
                f"imbie3_{sheet.key}_mm_partitioned.csv (IMBIE version {mm.version}), {mm.rows[0].period} to "
                f"{mm.rows[-1].period}.",
                f"Checked every month against imbie3_{sheet.key}_Gt_partitioned.csv: the mm value and its uncertainty "
                "equal the Gt values divided by 360 (IMBIE's 360 Gt of ice per mm of sea level), so the mm column "
                "has the mass-balance sign, negative for a loss of ice.",
                "Flipped the sign, so that a positive value is a rise in global mean sea level. Lower and upper are "
                "the flipped value minus and plus the one-sigma uncertainty.",
            ],
            changes="sign flipped from mass balance (negative for ice loss) to contribution to sea level (positive "
            "for a rise).",
        )

    return run


def _scope_baseline(sheet: Sheet) -> str:
    return (
        f"Zero just before {sheet.start}, the start of IMBIE's {sheet.name} record; the first month's value is that "
        "month's change."
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    out: list[Transform] = []
    for sheet in (GREENLAND, ANTARCTICA):
        basis = (
            f"Reconciled from {sheet.estimates} independent satellite estimates (altimetry, gravimetry and the "
            "input-output method) by IMBIE 2026; total mass balance, the sum of surface mass balance and ice dynamics."
        )
        out.append(
            Transform(
                spec=Spec(
                    id=f"ice-sheet-mass.imbie-2026.{sheet.key}",
                    title=f"{sheet.name} Ice Sheet mass change since {sheet.start} (IMBIE)",
                    description=f"Cumulative change in the mass of the {sheet.name} Ice Sheet each month from "
                    f"{sheet.start} to December 2023, from the IMBIE team's reconciliation of satellite surveys, "
                    "with the one-sigma uncertainty. Negative values are a loss of ice.",
                    kind="series",
                    unit=GT,
                    display=Display(decimals=0),
                    scope=Scope(geography=sheet.geography, baseline=_scope_baseline(sheet), basis=basis),
                    geo_coverage="global-only",
                    headline_entity=sheet.entity,
                ),
                inputs=(sheet.gt,),
                run=_mass_run(sheet),
                module_file=here,
                validation=Validation(min_rows=500, value_range=(-8000.0, 2000.0)),
            )
        )
        checks: tuple[PublisherCheck, ...] = ()
        if sheet is ANTARCTICA:
            checks = (
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="1.0",
                    entity=sheet.entity,
                    period="2023-12",
                    stated="13.3",
                    quote="In all, the Antarctic Ice Sheet lost 4,780 ± 513 Gt of ice between 1979 and 2023, raising "
                    "the global sea level by 13.3 ± 1.4 mm",
                    url=PAPER_URL,
                ),
            )
        out.append(
            Transform(
                spec=Spec(
                    id=f"sea-level-contribution.imbie-2026.{sheet.key}",
                    title=f"Sea level rise from the {sheet.name} Ice Sheet since {sheet.start} (IMBIE)",
                    description=f"How much the {sheet.name} Ice Sheet's loss of ice has added to global mean sea level "
                    f"each month from {sheet.start} to December 2023, from the IMBIE team's reconciliation of "
                    "satellite surveys, with the one-sigma uncertainty. IMBIE converts 360 Gt of ice to 1 mm of sea "
                    "level.",
                    kind="series",
                    unit=MM,
                    display=Display(decimals=1),
                    scope=Scope(
                        geography=sheet.geography,
                        baseline=_scope_baseline(sheet),
                        basis=basis + " Positive values raise global mean sea level; 360 Gt of ice = 1 mm.",
                    ),
                    geo_coverage="global-only",
                    headline_entity=sheet.entity,
                ),
                inputs=(sheet.gt, sheet.mm),
                run=_sea_level_run(sheet),
                module_file=here,
                validation=Validation(min_rows=500, value_range=(-5.0, 25.0)),
                checks=checks,
            )
        )
    return out

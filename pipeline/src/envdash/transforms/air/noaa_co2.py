"""NOAA GML carbon dioxide: monthly mean at Mauna Loa and the annual global marine-surface mean.

Vintage. NOAA labels each release by the month it was made ("Version 2026-09" on gml.noaa.gov/ccgg/trends/
gl_data.html for the files created on 5 September 2026). The files carry no version string, only
"# File Creation: Sat Sep  5 03:55:38 2026", so the vintage is that line's year and month.

Sentinels in co2_mm_mlo.csv (column header: year,month,decimal date,average,deseasonalized,ndays,sdev,unc). The file
says: "Missing months have been interpolated, for NOAA data indicated by negative stdev and uncertainty. We have no
information for SIO data about Ndays, stdv, unc so that they are also indicated by negative numbers." We publish the
`average` column only and keep every month, adding a note where the file's own markers say something about it:
- March 1958 to April 1974 (Scripps): NOAA does not say which months were interpolated.
- From May 1974, ndays = -1: no measurement days in the month, which NOAA states it filled by interpolation.
- From May 1974, ndays >= 0 but sdev negative: measured, but NOAA gives no standard deviation for the month.
- December 2022 to July 2023: measured at the Maunakea Observatories while Mauna Loa was shut by the eruption.
NOAA's monthly `unc` column is not published because the file does not say what interval it is. A negative average
(no such month in the current file) would become a null value with the sentinel as its reason; nothing is filled in.

Uncertainty in co2_annmean_gl.csv: the file states "The reported uncertainty is the mean of the standard deviations
for each annual average", so lower/upper are mean ∓ unc with interval 1sigma (exact decimal arithmetic on the printed
digits). The file also states "the data presented for the last year are subject to change", so the last year is
published with status preliminary.

If any of the quoted header statements disappears, the transform stops: a person must re-read the file before
these rules are applied to it.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "noaa-gml-trends"
MONTHLY_MLO = Input(SOURCE, "co2-mm-mlo")
ANNUAL_GL = Input(SOURCE, "co2-annmean-gl")
PPM = Unit(code="ppm", label="parts per million", short="ppm")

SIO_LAST_MONTH = "1974-04"
MAUNAKEA_MONTHS = {"2022-12", "2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06"}
MAUNAKEA_PARTIAL = "2023-07"

MONTHLY_REQUIRED = (
    "Data from March 1958 through April 1974 have been obtained by C. David Keeling of the Scripps Institution of "
    "Oceanography (SIO)",
    "Missing months have been interpolated, for NOAA data indicated by negative stdev and uncertainty. We have no "
    "information for SIO data about Ndays, stdv, unc so that they are also indicated by negative numbers",
    "Observations starting from December 2022 to July 4, 2023 are from a site at the Maunakea Observatories",
)
ANNUAL_REQUIRED = (
    "The reported uncertainty is the mean of the standard deviations for each annual average",
    "the data presented for the last year are subject to change",
)


class NoaaFormatError(ValueError):
    pass


def header_text(raw: str) -> str:
    """The '#' comment block as one line of text."""
    lines = [ln[1:].strip() for ln in raw.splitlines() if ln.startswith("#")]
    return re.sub(r"\s+", " ", " ".join(lines))


def file_creation(raw: str) -> datetime:
    m = re.search(r"^# File Creation:\s+(.+?)\s*$", raw, re.M)
    if not m:
        raise NoaaFormatError("no '# File Creation:' line")
    return datetime.strptime(" ".join(m.group(1).split()), "%a %b %d %H:%M:%S %Y")


def _require(header: str, statements: tuple[str, ...], name: str) -> None:
    for s in statements:
        if s not in header:
            raise NoaaFormatError(f"{name}: header no longer says {s!r}; re-read the file before trusting these rules")


def _table(raw: str, expected: list[str], name: str) -> pl.DataFrame:
    df = pl.read_csv(raw.encode("utf-8"), comment_prefix="#", infer_schema=False)
    if df.columns != expected:
        raise NoaaFormatError(f"{name}: columns {df.columns} != expected {expected}")
    return df


def parse_monthly(raw: str) -> tuple[list[Observation], datetime]:
    _require(header_text(raw), MONTHLY_REQUIRED, "co2_mm_mlo.csv")
    created = file_creation(raw)
    cols = ["year", "month", "decimal date", "average", "deseasonalized", "ndays", "sdev", "unc"]
    df = _table(raw, cols, "co2_mm_mlo.csv")
    obs: list[Observation] = []
    for row in df.iter_rows(named=True):
        period = f"{int(row['year']):04d}-{int(row['month']):02d}"
        avg = float(row["average"])
        ndays = int(row["ndays"])
        sdev = float(row["sdev"])
        notes: list[str] = []
        if period <= SIO_LAST_MONTH:
            notes.append(
                "Scripps Institution of Oceanography measurement; NOAA's file gives no days, standard deviation or "
                "uncertainty for this month and does not say whether it was interpolated."
            )
        elif ndays < 0:
            notes.append(
                "No measurement days this month (days = -1 in NOAA's file); NOAA fills missing months by interpolation."
            )
        elif sdev < 0:
            notes.append(f"Measured on {ndays} days; NOAA's file gives no standard deviation for this month.")
        if period in MAUNAKEA_MONTHS:
            notes.append(
                "Measured at the Maunakea Observatories, about 21 miles north, while Mauna Loa Observatory was shut "
                "after the eruption."
            )
        elif period == MAUNAKEA_PARTIAL:
            notes.append("Measured at the Maunakea Observatories until 4 July 2023 and at Mauna Loa after that.")
        note = " ".join(notes) or None
        if avg < 0:
            obs.append(
                Observation(
                    entity="MLO",
                    period=period,
                    value=None,
                    missing_reason=f"NOAA's file has the sentinel {row['average']} instead of a monthly mean.",
                    note=note,
                )
            )
        else:
            obs.append(Observation(entity="MLO", period=period, value=avg, note=note))
    return obs, created


def parse_annual_global(raw: str) -> tuple[list[Observation], datetime]:
    _require(header_text(raw), ANNUAL_REQUIRED, "co2_annmean_gl.csv")
    created = file_creation(raw)
    df = _table(raw, ["year", "mean", "unc"], "co2_annmean_gl.csv")
    rows = list(df.iter_rows(named=True))
    obs: list[Observation] = []
    for i, row in enumerate(rows):
        mean, unc = Decimal(row["mean"]), Decimal(row["unc"])
        status = "preliminary" if i == len(rows) - 1 else "final"
        if mean < 0:
            obs.append(
                Observation(
                    entity="WLD",
                    period=f"{int(row['year']):04d}",
                    value=None,
                    status=status,
                    missing_reason=f"NOAA's file has the sentinel {row['mean']} instead of an annual mean.",
                )
            )
        elif unc < 0:
            obs.append(
                Observation(
                    entity="WLD",
                    period=f"{int(row['year']):04d}",
                    value=float(mean),
                    status=status,
                    note=f"NOAA's file gives no uncertainty for this year (sentinel {row['unc']}).",
                )
            )
        else:
            obs.append(
                Observation(
                    entity="WLD",
                    period=f"{int(row['year']):04d}",
                    value=float(mean),
                    lower=float(mean - unc),
                    upper=float(mean + unc),
                    interval="1sigma",
                    status=status,
                )
            )
    return obs, created


def _monthly(files: dict[str, InputFile]) -> Result:
    raw = files[MONTHLY_MLO.key].path.read_text(encoding="utf-8")
    obs, created = parse_monthly(raw)
    return Result(
        observations=obs,
        vintage=f"{created:%Y-%m}",
        date_published=created.date().isoformat(),
        steps=[
            "Read the monthly mean column (average) of co2_mm_mlo.csv, created by NOAA on "
            f"{created.day} {created:%B %Y}. The vintage is the year and month of that creation date, which is how "
            "NOAA labels its versions.",
            "Kept every month as published. Where NOAA's own markers say something about a month (a Scripps-era "
            "value, a month with no measurement days that NOAA interpolated, a month without a standard deviation, "
            "or a month measured at Maunakea after the 2022 eruption) the observation carries that as a note. The "
            "deseasonalized, days, standard deviation and uncertainty columns are not published.",
        ],
    )


def _annual_global(files: dict[str, InputFile]) -> Result:
    raw = files[ANNUAL_GL.key].path.read_text(encoding="utf-8")
    obs, created = parse_annual_global(raw)
    return Result(
        observations=obs,
        vintage=f"{created:%Y-%m}",
        date_published=created.date().isoformat(),
        steps=[
            f"Read co2_annmean_gl.csv, created by NOAA on {created.day} {created:%B %Y}. The vintage is the year and "
            "month of that creation date, which is how NOAA labels its versions.",
            "Lower and upper are the mean minus and plus NOAA's stated uncertainty, which the file defines as the "
            "mean of the standard deviations of 200 Monte Carlo global averages (one standard deviation).",
            "The last year is marked preliminary because the file states that the data for the last year are "
            "subject to change.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="co2.noaa-gml.monthly-mlo",
                title="Carbon dioxide at Mauna Loa, monthly mean",
                description="Monthly mean carbon dioxide in dry air measured at Mauna Loa Observatory, Hawaii, "
                "since March 1958: the Keeling Curve. Values before May 1974 were measured by the Scripps "
                "Institution of Oceanography.",
                kind="series",
                unit=PPM,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Mauna Loa Observatory, Hawaii (19.5° N, 155.6° W)",
                    basis="Dry-air mole fraction; monthly means of daily means, as published (not deseasonalized).",
                ),
                geo_coverage="global-only",
                headline_entity="MLO",
            ),
            inputs=(MONTHLY_MLO,),
            run=_monthly,
            module_file=here,
            validation=Validation(min_rows=800, value_range=(300.0, 500.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="2026-09",
                    entity="MLO",
                    period="2026-08",
                    stated="427.55",
                    quote="Monthly Average Mauna Loa CO₂ August 2026: 427.55 ppm",
                    url="https://gml.noaa.gov/ccgg/trends/",
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id="co2.noaa-gml.annual-global",
                title="Carbon dioxide, global annual mean",
                description="Annual mean carbon dioxide in dry air averaged over NOAA's global network of marine "
                "surface sites, since 1979.",
                kind="series",
                unit=PPM,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean of marine surface sites",
                    basis="Dry-air mole fraction; NOAA's global marine boundary layer average.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ANNUAL_GL,),
            run=_annual_global,
            module_file=here,
            validation=Validation(min_rows=45, value_range=(300.0, 500.0)),
        ),
    ]

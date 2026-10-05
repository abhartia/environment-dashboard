"""NOAA NCEI ocean heat content of the World Ocean: yearly 0-2000 m (from 2005), yearly 0-700 m (from 1955) and
five-year 0-2000 m (from 1955-59), in units of 10^22 joules, as published.

Inputs: the World Ocean basin time series files of NCEI Accession 0164586 (Levitus, Boyer et al.):
yearly/h22-w0-2000m.dat, yearly/h22-w0-700m.dat and pentad/pent_h22-w0-2000m.dat.

Format. NCEI's "Heat Content Basin Time Series" page (www.ncei.noaa.gov/access/global-ocean-heat-content/
basin_heat_data.html, read 2026-10-05) says: "HEAT CONTENT UNITS: 10 22 joules"; the first column is "year+0.5 (for
the yearly heat content) or mid-point of five-year compositing period (for the pentadal heat content)"; the 2nd and
3rd columns are the heat content of the whole basin and its standard error, then the northern and southern
hemisphere parts with theirs; "The first line of file contains the labels for each of 7 columns. Read the second line
through the last line using an equivalent of the FORTRAN FORMAT (F8.1, 6F8.3) statement." The reader takes exactly
that: a first line equal to HEADER, then 56-character lines of seven 8-character fields. Anything else stops the
build.

Periods. A yearly row's first field must be <year>.500 and becomes the period "<year>". A pentadal row's first field
must be <mid>.5, the middle of the five years, and becomes the range "<mid - 2.5>/<mid + 2.5 - 1>" (1957.5 is
1955-1959). The pentadal file has one row per overlapping five-year window (1955-59, 1956-60, ...), all published.

What is published. The World Ocean value (column WO) and, as lower and upper, the value minus and plus its standard
error (column WOse; exact decimal arithmetic on the printed digits), interval 1sigma. The hemisphere columns are not
published. Values are anomalies: the NCEI accession record says the temperature data "are used to calculate
temperature (and salinity) differences from a long-term climatological mean (the World Ocean Atlas series)", and
neither the files nor the product pages name that climatology's period, so the scope says exactly that. NCEI does
not mark any year as preliminary, so every value is published as final.

Vintage. The files carry no version or date. The vintage is the file's HTTP Last-Modified date (6 July 2026 for the
files that added 2025), which is when NCEI last revised it; a snapshot without Last-Modified stops the build.

Publisher check. None: no NCEI statement giving a yearly World Ocean value for this vintage was found (searched
2026-10-05: the product landing page, the basin time series page, the accession 0164586 record, NCEI's 2025 annual
global climate report and NOAA Climate.gov's ocean heat content article). The values are regression-tested against
the files in pipeline/tests/test_ocean_ncei_ohc.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "ncei-ocean-heat"
YEARLY_2000 = Input(SOURCE, "world-0-2000m-yearly")
YEARLY_700 = Input(SOURCE, "world-0-700m-yearly")
PENTADAL_2000 = Input(SOURCE, "world-0-2000m-pentadal")

HEADER = "    YEAR      WO    WOse      NH    NHse      SH    SHse"
FIELD = 8
FIELDS = 7

UNIT = Unit(code="1e22J", label="10²² joules (10 zettajoules)", short="10²² J")
BASELINE = (
    "Difference from NCEI's long-term climatological mean (the World Ocean Atlas series); the files and product "
    "pages do not name the climatology's period"
)


class NceiOhcFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    period: str
    value: Decimal
    se: Decimal


def vintage_of(last_modified: str | None) -> str:
    """The file's HTTP Last-Modified date, ISO: NCEI's files carry no version label."""
    if not last_modified:
        raise NceiOhcFormatError("the snapshot has no Last-Modified header, which is the only vintage the file has")
    return parsedate_to_datetime(last_modified).date().isoformat()


def _period(first: str, pentadal: bool, name: str) -> str:
    whole, _, frac = first.partition(".")
    if not whole.isdigit():
        raise NceiOhcFormatError(f"{name}: time field {first!r} is not a year")
    if pentadal:
        if frac != "5":
            raise NceiOhcFormatError(f"{name}: pentad time {first!r} is not the middle of five years (<year>.5)")
        start = int(whole) - 2
        return f"{start:04d}/{start + 4:04d}"
    if frac != "500":
        raise NceiOhcFormatError(f"{name}: yearly time {first!r} is not <year>.500")
    return f"{int(whole):04d}"


def read_rows(raw: str, *, pentadal: bool, name: str) -> list[Row]:
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if not lines or lines[0] != HEADER:
        raise NceiOhcFormatError(f"{name}: first line {lines[0] if lines else ''!r} != expected {HEADER!r}")
    rows: list[Row] = []
    for n, line in enumerate(lines[1:], start=2):
        if len(line) != FIELD * FIELDS:
            raise NceiOhcFormatError(f"{name} line {n}: {len(line)} characters, not {FIELDS} fields of {FIELD}")
        fields = [line[i : i + FIELD].strip() for i in range(0, FIELD * FIELDS, FIELD)]
        try:
            value, se = Decimal(fields[1]), Decimal(fields[2])
        except InvalidOperation:
            raise NceiOhcFormatError(f"{name} line {n}: {fields[1]!r} or {fields[2]!r} is not a number") from None
        if se < 0:
            raise NceiOhcFormatError(f"{name} line {n}: negative standard error {fields[2]}")
        rows.append(Row(_period(fields[0], pentadal, name), value, se))
    if not rows:
        raise NceiOhcFormatError(f"{name}: no data rows")
    return rows


def observations(rows: list[Row]) -> list[Observation]:
    return [
        Observation(
            entity="WLD",
            period=r.period,
            value=float(r.value),
            lower=float(r.value - r.se),
            upper=float(r.value + r.se),
            interval="1sigma",
        )
        for r in rows
    ]


def _runner(inp: Input, file_name: str, *, pentadal: bool, layer: str):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[inp.key]
        rows = read_rows(f.path.read_text(encoding="ascii"), pentadal=pentadal, name=file_name)
        vintage = vintage_of(f.snapshot.last_modified)
        span = f"{rows[0].period} to {rows[-1].period}"
        read = (
            f"Read {file_name} (World Ocean heat content, {layer}, in 10^22 joules; last modified by NCEI on "
            f"{vintage}, which is the vintage, since the file carries no version), {len(rows)} rows from {span}."
        )
        if pentadal:
            read += (
                " Each row is a five-year mean; its time column, the middle of the five years (e.g. 1957.5), "
                "became the five-year range (1955/1959)."
            )
        else:
            read += " The time column (year + 0.5) became the year."
        return Result(
            observations=observations(rows),
            vintage=vintage,
            date_published=vintage,
            steps=[
                read,
                "Published the World Ocean column as printed. Lower and upper are that value minus and plus NCEI's "
                "standard error from the next column (one standard error). The hemisphere columns are not published.",
            ],
        )

    return run


def _scope(depth: str, basis: str) -> Scope:
    return Scope(
        geography=f"World Ocean (including the Arctic Ocean), sea surface to {depth} depth",
        baseline=BASELINE,
        basis=basis,
    )


IN_SITU = (
    "Heat content anomaly integrated over the layer, calculated by NCEI from in situ subsurface temperature profiles "
    "quality controlled in the World Ocean Database (method of Levitus et al. 2012)."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="ohc.ncei.yearly-0-2000m",
                title="Ocean heat content, 0–2000 m, yearly (NCEI)",
                description="Heat stored in the top 2,000 metres of the world ocean in each year since 2005, as the "
                "difference from NCEI's long-term average, in units of 10²² joules, with one standard error.",
                kind="series",
                unit=UNIT,
                display=Display(decimals=1),
                scope=_scope("2000 m", "Yearly means. " + IN_SITU),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(YEARLY_2000,),
            run=_runner(YEARLY_2000, "h22-w0-2000m.dat", pentadal=False, layer="0-2000 m"),
            module_file=here,
            validation=Validation(min_rows=21, value_range=(-40.0, 80.0)),
        ),
        Transform(
            spec=Spec(
                id="ohc.ncei.yearly-0-700m",
                title="Ocean heat content, 0–700 m, yearly (NCEI)",
                description="Heat stored in the top 700 metres of the world ocean in each year since 1955, as the "
                "difference from NCEI's long-term average, in units of 10²² joules, with one standard error.",
                kind="series",
                unit=UNIT,
                display=Display(decimals=1),
                scope=_scope("700 m", "Yearly means. " + IN_SITU),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(YEARLY_700,),
            run=_runner(YEARLY_700, "h22-w0-700m.dat", pentadal=False, layer="0-700 m"),
            module_file=here,
            validation=Validation(min_rows=71, value_range=(-30.0, 60.0)),
        ),
        Transform(
            spec=Spec(
                id="ohc.ncei.pentadal-0-2000m",
                title="Ocean heat content, 0–2000 m, five-year means (NCEI)",
                description="Heat stored in the top 2,000 metres of the world ocean as running five-year means "
                "since 1955–59 (NCEI's basin time series have no yearly or three-month 0–2,000 m values before "
                "2005), as the difference from NCEI's long-term average, in units of 10²² joules, with one standard "
                "error.",
                kind="series",
                unit=UNIT,
                display=Display(decimals=1),
                scope=_scope(
                    "2000 m",
                    "Five-year means, one per overlapping five-year window (1955–59, 1956–60, ...). " + IN_SITU,
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(PENTADAL_2000,),
            run=_runner(PENTADAL_2000, "pent_h22-w0-2000m.dat", pentadal=True, layer="0-2000 m"),
            module_file=here,
            validation=Validation(min_rows=67, value_range=(-40.0, 80.0)),
        ),
    ]

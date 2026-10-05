"""C3S Climate Bulletin: ERA5 monthly global surface air temperature relative to 1850–1900, as C3S publishes it.

Input: the Bulletin's "Fig1b ... global_allmonths_DATA.csv" for the latest month (found through `discover`): a "#"
header ending "Last updated: <dd Mon yyyy>", then columns month, 2t, clim_91-20, ano_91-20, offset_pi, ano_pi, in °C to
four decimals, one row per month from January 1940.

Baseline. ERA5 starts in 1940, so C3S relates it to 1850–1900 with a fixed offset per calendar month (offset_pi,
"Monthly offset between 1850-1900 and 1991-2020"), which it estimates from Berkeley Earth, HadCRUT5 and
NOAAGlobalTemp (https://climate.copernicus.eu/climate-bulletin-about-data-and-analysis). The site publishes the
producer's own ano_pi column unchanged, and checks it is the sum of the file's ano_91-20 and offset_pi on every row,
so a change of method or a broken file stops the build. No offset of ours is applied.

Status. The file marks no month as preliminary and gives no status column, so every month is published as the file
states it. C3S may revise the latest months when ERA5's preliminary data are replaced; the next file then carries
the revised values.

Vintage. The latest month in the file (YYYY-MM), which must equal the month in the file name. The "Last updated" date
is the publication date and fills the {year} of the Copernicus credit line.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "c3s-era5-bulletin"
ALLMONTHS = Input(SOURCE, "global-allmonths")
COLUMNS = ["month", "2t", "clim_91-20", "ano_91-20", "offset_pi", "ano_pi"]
HEADER_REQUIRED = (
    "offset_pi: Monthly offset between 1850-1900 and 1991-2020",
    "ano_pi: Monthly anomaly relative to 1850-1900",
    "Units: deg. C",
)
FILE_MONTH = re.compile(r"/C3S_Bulletin_temp_(\d{6})_Fig1b_timeseries_anomalies_ref1991-2020_global_allmonths_DATA")


class BulletinFormatError(ValueError):
    pass


def header_lines(raw: str) -> list[str]:
    return [ln[1:].strip() for ln in raw.splitlines() if ln.startswith("#")]


def last_updated(raw: str) -> date:
    found = [ln for ln in header_lines(raw) if ln.startswith("Last updated:")]
    if len(found) != 1:
        raise BulletinFormatError("expected one 'Last updated:' header line")
    return datetime.strptime(found[0].removeprefix("Last updated:").strip(), "%d %b %Y").date()


def file_month(url: str | None) -> str:
    m = FILE_MONTH.search(url or "")
    if not m:
        raise BulletinFormatError(f"cannot read the data month from {url!r}")
    return f"{m.group(1)[:4]}-{m.group(1)[4:]}"


def parse(raw: str) -> tuple[list[Observation], dict[str, list[Decimal]]]:
    """Returns (observations of ano_pi, {calendar month "MM": the distinct offset_pi values C3S used})."""
    header = " ".join(header_lines(raw))
    for s in HEADER_REQUIRED:
        if s not in header:
            raise BulletinFormatError(f"header no longer says {s!r}; re-read the file before trusting these rules")
    df = pl.read_csv(raw.encode("utf-8"), comment_prefix="#", infer_schema=False)
    if df.columns != COLUMNS:
        raise BulletinFormatError(f"columns {df.columns} != expected {COLUMNS}")
    obs: list[Observation] = []
    offsets: dict[str, set[Decimal]] = {}
    for month, _t, _clim, ano, off, ano_pi in df.iter_rows():
        if not re.fullmatch(r"\d{4}-\d{2}-01", month):
            raise BulletinFormatError(f"month {month!r} is not YYYY-MM-01")
        a, o, p = Decimal(ano), Decimal(off), Decimal(ano_pi)
        if a + o != p:
            raise BulletinFormatError(f"{month}: ano_pi {ano_pi} is not ano_91-20 {ano} + offset_pi {off}")
        offsets.setdefault(month[5:7], set()).add(o)
        obs.append(Observation(entity="WLD", period=month[:7], value=float(p)))
    return obs, {k: sorted(v) for k, v in sorted(offsets.items())}


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ALLMONTHS.key]
    raw = f.path.read_text(encoding="utf-8")
    obs, offsets = parse(raw)
    updated = last_updated(raw)
    month = file_month(str(f.snapshot.url) if f.snapshot.url else None)
    if obs[-1].period != month:
        raise BulletinFormatError(f"the file name says {month}, but the last row is {obs[-1].period}")
    offset_text = "; ".join(
        f"{datetime(2000, int(k), 1):%B} {' or '.join(str(x) for x in v)}" for k, v in offsets.items()
    )
    return Result(
        observations=obs,
        vintage=month,
        year=str(updated.year),
        date_published=updated.isoformat(),
        steps=[
            f"Read the C3S Climate Bulletin file of global monthly ERA5 surface air temperature for data to {month}, "
            f"last updated by C3S on {updated:%d %B %Y}.",
            "Published C3S's own anomaly from 1850–1900 (column ano_pi) unchanged. C3S computes it as the anomaly from "
            "1991–2020 plus a fixed offset per calendar month (offset_pi), its estimate of the warming from 1850–1900 "
            "to 1991–2020 from Berkeley Earth, HadCRUT5 and NOAAGlobalTemp, because ERA5 starts in 1940. Checked on "
            f"every row that ano_pi equals ano_91-20 plus offset_pi. The offsets in this file (°C): {offset_text}.",
            "The file has no status column and marks no month as preliminary, so no month is labelled preliminary "
            "here. The latest months rest on ERA5's preliminary data, which C3S may revise; a later Bulletin file "
            "then carries the revised values.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="temp.c3s-era5-bulletin.monthly-1850-1900",
                title="Global surface air temperature above 1850–1900, monthly (ERA5, C3S)",
                description="Global mean surface air temperature for each month since January 1940 from the ERA5 "
                "reanalysis, as the difference from the 1850–1900 level that C3S estimates for that calendar month. "
                "Published monthly with the Copernicus Climate Bulletin.",
                kind="series",
                unit=Unit(code="degC", label="degrees Celsius", short="°C"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean (0–360° E, 90° S–90° N)",
                    baseline="1850–1900, through C3S's fixed offset per calendar month from 1991–2020 (offset_pi, "
                    "0.80 to 0.96 °C), estimated from Berkeley Earth, HadCRUT5 and NOAAGlobalTemp",
                    basis="ERA5 reanalysis, monthly mean air temperature at 2 metres.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ALLMONTHS,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=1000, value_range=(-1.0, 3.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="2026-08",
                    entity="WLD",
                    period="2026-08",
                    stated="1.65",
                    quote="August 2026 was 1.65°C above the estimated 1850-1900 pre-industrial average for the month",
                    url="https://climate.copernicus.eu/surface-air-temperature-august-2026",
                ),
            ),
        )
    ]

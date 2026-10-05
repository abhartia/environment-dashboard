"""AVISO+ reference global mean sea level (GMSL) from satellite altimetry (CNES, CLS, LEGOS).

Two indicators, in one module so that its sha256 covers every line that decides them:

- gmsl.aviso.monthly: monthly global mean sea level change since 1993, in millimetres, computed from AVISO's NetCDF;
- gmsl.aviso.rate: AVISO's own stated average rate of rise, quoted from its product page, with a consistency check
  against the same NetCDF.

Licence. The AVISO License Agreement (Issue 20) is CC BY-like but section 3.2 bars re-sharing the original,
unmodified product through a web portal or API; it "does not restrict Sharing Adapted Material". The registry entry is
open with mirror_raw false, so only derived values are published, never the raw file, and the credit line is the
"Modified from the original" form (Result.changes is set for the monthly series). There are no committed fixtures for
this source (tests/fixtures/make_fixture.py refuses sources with mirror_raw false); tests read the real snapshot.

The file. MSL_Serie_MERGED_Global_AVISO_GIA_Adjust_Filter2m.nc holds one value about every 10 days (one per
altimetry cycle) from 5 January 1993: msl in metres, the uncertainty envelope, and two corrections that the file says
are the amounts to ADD to get the uncorrected series (so msl already includes them). Its global attributes carry the
product DOI, the creation date (history), first_date, end_date, zone GLOBAL, gia_corrected, filter_period "2 months",
and the variable's long name says "(periodic signals removed)". Every one of these is checked; a different product
DOI, zone, filter or correction stops the build until a person re-reads the product page and this module.

Monthly series. Each calendar month's value is the arithmetic mean of the cycle values dated in that month (cycles
are not evenly spaced around mission changes, so a month holds 2 to 4 of them; every month from January 1993 holds at
least one, and a month without any would stop the build rather than be filled). The month of the file's last cycle is
not published: the record stops part-way through it (end_date 15 August 2026 in the file of 26 September 2026). The
series is then re-based so the mean of the twelve 1993 months is zero (exact float sums), and converted from metres
to millimetres. AVISO's anomaly has no stated reference period, so "change since 1993" is ours, and is labelled as
such. The 1-sigma uncertainty envelope is not published: AVISO defines it for each cycle value of its own series,
not for monthly means of the re-based series, and we do not re-derive it. AVISO prints no monthly value, so there
is no publisher cross-check; its page's "Since February 1993, the GMSL has risen by approximately 11 cm" is a
rounded statement, compared in the tests only.

Rate. The product page states: "The average sea level rise rate is 3.6 mm per year (+/-0.3 mm/yr, 90%CI) over the
globe and from 1999." It is published as quoted: 3.6 mm per year, 90% range 3.3 to 3.9. The page names no end date;
the period is published as 1999/<year the page was read>. The page has no date of its own, so the vintage is the date
it was read. The build stops unless the quote is in the page's visible text, and unless an ordinary least-squares
slope through the NetCDF's cycle values from 1 January 1999 falls inside AVISO's stated 90% range (it is 3.67 mm per
year in the file of 26 September 2026): that shows the sentence and the file describe the same record. The slope is
a check only and is not published.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import netCDF4
import numpy as np

from envdash.models import Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.literature import verify_quote_in_document

SOURCE = "aviso-gmsl"
NC = Input(SOURCE, "msl-global-filter2m-nc")
PAGE = Input(SOURCE, "msl-product-page")

MM = Unit(code="mm", label="millimetres", short="mm")
MM_PER_YEAR = Unit(code="mm/yr", label="millimetres per year", short="mm/yr")

PRODUCT_DOI = "https://doi.org/10.24400/527896/AVISO-2025.010"
REQUIRED_ATTRS = {
    "doi": PRODUCT_DOI,
    "zone": "GLOBAL",
    "gia_corrected": "True",
    "filter_period": "2 months",
}
MSL_LONG_NAME_MARK = "(periodic signals removed)"
TIME_UNITS = "days since 1970-01-01"
EPOCH = datetime(1970, 1, 1)
BASELINE_YEAR = 1993
HISTORY = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}: created by ")

RATE_QUOTE = "The average sea level rise rate is 3.6 mm per year (+/-0.3 mm/yr, 90%CI) over the globe and from 1999."
RATE_VALUE_TEXT = "3.6 mm per year (+/-0.3 mm/yr, 90%CI)"
RATE_PATTERN = re.compile(r"(\d+\.\d) mm per year \(\+/-(\d+\.\d) mm/yr, 90%CI\) over the globe and from (\d{4})\.")
RATE_LOCATOR = "Mean Sea Level product page, section 'At the global scale'"
DAYS_PER_YEAR = 365.25


class AvisoFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    created: date
    first_date: date
    end_date: date
    times: list[datetime]
    msl_m: list[float]


def read_record(raw: bytes) -> Record:
    """The cycle times and msl values of the NetCDF, after checking every attribute the rules above depend on."""
    with netCDF4.Dataset("aviso-msl.nc", mode="r", memory=raw) as ds:
        attrs = {a: ds.getncattr(a) for a in ds.ncattrs()}
        for k, want in REQUIRED_ATTRS.items():
            if str(attrs.get(k)) != want:
                raise AvisoFormatError(f"global attribute {k} is {attrs.get(k)!r}, not {want!r}; re-read the product")
        m = HISTORY.match(str(attrs.get("history", "")))
        if not m:
            raise AvisoFormatError(f"history {attrs.get('history')!r} does not give a creation date")
        if "time" not in ds.variables or "msl" not in ds.variables:
            raise AvisoFormatError(f"variables {list(ds.variables)} lack time or msl")
        tv, mv = ds.variables["time"], ds.variables["msl"]
        if getattr(tv, "units", None) != TIME_UNITS:
            raise AvisoFormatError(f"time units {getattr(tv, 'units', None)!r}, not {TIME_UNITS!r}")
        if getattr(mv, "units", None) != "m":
            raise AvisoFormatError(f"msl units {getattr(mv, 'units', None)!r}, not 'm'")
        if MSL_LONG_NAME_MARK not in getattr(mv, "long_name", ""):
            raise AvisoFormatError(f"msl long_name no longer says {MSL_LONG_NAME_MARK!r}")
        t, v = tv[:], mv[:]
        if np.ma.count_masked(t) or np.ma.count_masked(v):
            raise AvisoFormatError("time or msl holds fill values, which these rules do not cover; re-read the file")
        days = [float(x) for x in np.ma.getdata(t)]
        msl = [float(x) for x in np.ma.getdata(v)]
    if any(b <= a for a, b in pairwise(days)):
        raise AvisoFormatError("cycle times do not strictly increase")
    times = [EPOCH + timedelta(days=d) for d in days]
    first, end = date.fromisoformat(str(attrs["first_date"])), date.fromisoformat(str(attrs["end_date"]))
    if times[0].date() != first or times[-1].date() != end:
        raise AvisoFormatError(
            f"first_date {first} and end_date {end} do not match the first and last cycle times "
            f"({times[0].date()}, {times[-1].date()})"
        )
    return Record(date.fromisoformat(m.group(1)), first, end, times, msl)


def _months(start: str, stop: str) -> list[str]:
    y, mo = int(start[:4]), int(start[5:])
    out: list[str] = []
    while f"{y:04d}-{mo:02d}" <= stop:
        out.append(f"{y:04d}-{mo:02d}")
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return out


@dataclass(frozen=True)
class Monthly:
    observations: list[Observation]
    baseline_m: float
    cycles_per_month: dict[int, int]
    """{number of cycles in a month: number of such months} over the published months."""
    dropped_month: str
    """The month of the last cycle, not published because the record stops part-way through it."""


def monthly_change(rec: Record) -> Monthly:
    by_month: dict[str, list[float]] = defaultdict(list)
    for t, v in zip(rec.times, rec.msl_m, strict=True):
        by_month[f"{t:%Y-%m}"].append(v)
    last = f"{rec.times[-1]:%Y-%m}"
    months = _months(f"{rec.times[0]:%Y-%m}", last)[:-1]
    empty = [m for m in months if not by_month[m]]
    if empty:
        raise AvisoFormatError(f"no cycle in {', '.join(empty)}; a month is never filled in")
    means = {m: math.fsum(by_month[m]) / len(by_month[m]) for m in months}
    base_months = [m for m in months if m.startswith(f"{BASELINE_YEAR}-")]
    if len(base_months) != 12:
        raise AvisoFormatError(f"{len(base_months)} months of {BASELINE_YEAR}, not 12")
    base = math.fsum(means[m] for m in base_months) / 12
    counts: dict[int, int] = defaultdict(int)
    for m in months:
        counts[len(by_month[m])] += 1
    obs = [Observation(entity="WLD", period=m, value=(means[m] - base) * 1000) for m in months]
    return Monthly(obs, base, dict(sorted(counts.items())), last)


def ols_rate_mm_per_year(rec: Record, start: date) -> float:
    """Least-squares slope (mm per year) through the cycle values dated on or after `start`."""
    t0 = datetime(start.year, start.month, start.day)
    pts = [((t - t0).total_seconds() / 86400 / DAYS_PER_YEAR, v) for t, v in zip(rec.times, rec.msl_m, strict=True)]
    pts = [(x, v) for x, v in pts if x >= 0]
    if len(pts) < 2:
        raise AvisoFormatError(f"fewer than two cycles from {start}")
    slope = np.polyfit([x for x, _ in pts], [v for _, v in pts], 1)[0]
    return float(slope) * 1000


@dataclass(frozen=True)
class StatedRate:
    value: Decimal
    half_width: Decimal
    from_year: int


def stated_rate(quote: str) -> StatedRate:
    m = RATE_PATTERN.search(quote)
    if not m:
        raise AvisoFormatError(f"cannot read a rate, a 90% interval and a start year from {quote!r}")
    return StatedRate(Decimal(m.group(1)), Decimal(m.group(2)), int(m.group(3)))


def _day(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def _vintage(rec: Record) -> str:
    return f"{rec.created.isoformat()} (doi:{PRODUCT_DOI.removeprefix('https://doi.org/')})"


def _monthly(files: dict[str, InputFile]) -> Result:
    f = files[NC.key]
    rec = read_record(f.path.read_bytes())
    mon = monthly_change(rec)
    counts = ", ".join(f"{n} hold {k}" for k, n in mon.cycles_per_month.items())
    return Result(
        observations=mon.observations,
        vintage=_vintage(rec),
        date_published=rec.created.isoformat(),
        steps=[
            "Read the msl variable (global mean sea level anomaly, metres) and the cycle times of "
            f"MSL_Serie_MERGED_Global_AVISO_GIA_Adjust_Filter2m.nc, created by AVISO on {_day(rec.created)}: "
            f"{len(rec.times)} values about 10 days apart from {_day(rec.first_date)} to {_day(rec.end_date)}. "
            "Checked the product DOI, zone GLOBAL, the glacial isostatic adjustment correction, the 2-month filter "
            "and that annual and semi-annual signals are removed, as the file's attributes state.",
            "Averaged the cycle values dated in each calendar month (arithmetic mean). Of the "
            f"{len(mon.observations)} months published, {counts} cycles. The month of the last cycle "
            f"({mon.dropped_month}) is not published because the record stops part-way through it.",
            f"Re-based to the mean of the twelve {BASELINE_YEAR} monthly values ({mon.baseline_m * 1000:.3f} mm on "
            "AVISO's scale, which has no stated reference period) and converted from metres to millimetres.",
            "AVISO's 1-sigma uncertainty envelope is defined for its own cycle values and is not published for "
            "these monthly means.",
        ],
        changes=f"monthly means of AVISO's cycle values, re-based to their {BASELINE_YEAR} mean and converted from "
        "metres to millimetres.",
    )


def _rate(files: dict[str, InputFile]) -> Result:
    page = files[PAGE.key]
    verify_quote_in_document(
        page.path.read_bytes(),
        page.snapshot.content_type,
        str(page.snapshot.url) if page.snapshot.url else None,
        RATE_QUOTE,
    )
    s = stated_rate(RATE_QUOTE)
    lo, hi = s.value - s.half_width, s.value + s.half_width
    nc = files[NC.key]
    rec = read_record(nc.path.read_bytes())
    ours = ols_rate_mm_per_year(rec, date(s.from_year, 1, 1))
    if not float(lo) <= ours <= float(hi):
        raise AvisoFormatError(
            f"a least-squares slope through the file's values from {s.from_year} is {ours:.2f} mm/yr, outside "
            f"AVISO's stated {lo} to {hi} mm/yr: the sentence and the file may no longer describe the same record"
        )
    read_on = page.snapshot.date_accessed
    return Result(
        observations=[
            Observation(
                entity="WLD",
                period=f"{s.from_year}/{read_on.year}",
                value=float(s.value),
                lower=float(lo),
                upper=float(hi),
                interval="90ci",
                note=f'AVISO states the period as "from {s.from_year}" and gives no end date.',
            )
        ],
        vintage=f"product page read {read_on.isoformat()}",
        steps=[
            f"Quoted from AVISO's {RATE_LOCATOR}. The quote was found in the visible text of the page snapshot "
            f"(sha256 {page.snapshot.sha256[:12]}…) before publishing.",
            f'Value: "{RATE_VALUE_TEXT}" is published as {s.value} millimetres per year with the 90% range '
            f"{lo} to {hi} (the value minus and plus {s.half_width}). The page states the period only as "
            f'"from {s.from_year}"; it is published as {s.from_year}/{read_on.year}, {read_on.year} being the year '
            f"the page was read ({_day(read_on)}). The page carries no date, so the vintage is that reading date.",
            f"Consistency check (not published): an ordinary least-squares slope through the cycle values from "
            f"1 January {s.from_year} of the NetCDF created on {_day(rec.created)} (sha256 "
            f"{nc.snapshot.sha256[:12]}…, to {_day(rec.end_date)}) is {ours:.2f} mm per year, inside AVISO's "
            "stated 90% range; the build stops if it is not.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=RATE_LOCATOR, quote=RATE_QUOTE),
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="gmsl.aviso.monthly",
                title="Global mean sea level change since 1993, monthly (AVISO satellite altimetry)",
                description="How much the global average sea level has risen since 1993, month by month, measured "
                "by the reference satellite altimetry missions TOPEX/Poseidon, Jason-1, Jason-2, Jason-3 and "
                "Sentinel-6 Michael Freilich. Calculated by Environment Dashboard from AVISO's values about every "
                "10 days: averaged to calendar months and set so that the 1993 average is zero. Seasonal "
                "(annual and semi-annual) cycles are removed by AVISO.",
                kind="series",
                unit=MM,
                display=Display(decimals=1),
                scope=Scope(
                    geography="Global ocean mean between about 66° S and 66° N (the reference missions' coverage)",
                    baseline="1993 mean of this series (mean of its twelve 1993 monthly values)",
                    basis="Satellite altimetry, AVISO reference GMSL product (doi:10.24400/527896/AVISO-2025.010): "
                    "corrected for glacial isostatic adjustment, annual and semi-annual signals removed, 2-month "
                    "filter, TOPEX-A drift and Jason-3 radiometer corrections included. Monthly means of the cycle "
                    "values computed by Environment Dashboard; the month in which the record ends is left out.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(NC,),
            run=_monthly,
            module_file=here,
            validation=Validation(min_rows=400, value_range=(-50.0, 300.0)),
        ),
        Transform(
            spec=Spec(
                id="gmsl.aviso.rate",
                title="Average rate of global sea level rise since 1999 (AVISO)",
                description="AVISO's stated average rate of global mean sea level rise measured by satellite "
                "altimetry from 1999: 3.6 millimetres per year, with a 90% confidence interval of plus or minus 0.3 "
                "millimetres per year. AVISO's figure, quoted from its product page, not computed by us.",
                kind="published-value",
                unit=MM_PER_YEAR,
                display=Display(decimals=1),
                scope=Scope(
                    geography="Global ocean (AVISO: 'over the globe')",
                    baseline="None: a rate of change, from 1999",
                    basis="Average rate over the satellite altimetry record from 1999 as stated by AVISO, with its "
                    "90% confidence interval; the page names no end date. The same page notes that the processing "
                    "of the 1993–1999 part of the record changed in the latest release.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(PAGE, NC),
            run=_rate,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(0.0, 20.0)),
        ),
    ]

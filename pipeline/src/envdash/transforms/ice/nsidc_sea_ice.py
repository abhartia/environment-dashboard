"""NSIDC Sea Ice Index (G02135) v4: Arctic sea ice extent in September, and the yearly minimum of the 5-day mean.

Inputs: N_09_extent_v4.0.csv (one row per year: the September monthly extent) and N_seaice_extent_daily_v4.0.csv (the
daily extent), both of the Northern Hemisphere ("N"), in million km².

Version. Both file names end in "_v<version>.csv" and must name the same version; that version ("4.0") is the
vintage. The files carry no release date of their own, so the newest data date is stated in a processing step.

September extent. The extent column of the monthly file, as printed. The v4 user guide (section 3.1.6, read
2026-10-05) says NSIDC computes it from the daily gridded concentration fields: "the monthly extent value is obtained by
simply averaging the daily extents over the month", with the unobserved Arctic Pole Hole counted as ice covered. It is
not recomputed here from the daily file. "When insufficient satellite data are available to process the area and
extent values, -9999 is substituted": a negative value becomes a null with the sentinel as its reason. Rows whose
source_dataset column is NSIDC-0803 (JAXA's AMSR2 record, the input from 1 January 2025) carry that as a note.

Yearly minimum. NSIDC states its yearly minimum on the 5-day trailing mean, not the raw daily value: the user guide
(section 3.3.4) says "the daily extent series is smoothed using a 5-day trailing mean. The extent value for a given
day is averaged with the extent value from the previous four days", and NSIDC's 2026 minimum announcement (Sea Ice
Today, 23 September 2026) says "This year's minimum extent, based on a 5-day average, appears to have been set on
September 12." So for each day the mean of that day and the four before it is computed (exact decimal arithmetic on
the printed values), but only when all five days have a value in the file: NSIDC's guide fills up to three missing
days from the days before a gap, which is not done here. The published value is the lowest such mean of each calendar
year, and the period is the day it ends on. Consequences, all stated on the observations or in the steps:
- 1978 to 1986 are not published: before 21 August 1987 the file has a value only every other day (user guide), so
  no five consecutive days exist.
- Days whose 5-day window has a gap are skipped. That covers 1 January to 23 August 1987 and the gap the guide
  describes ("There are no data from 3 December 1987 to 13 January 1988 due to satellite problems"). A year with such
  days carries a note naming them.
- The guide says the 14 September 1984 value "is in error ... should not be used in analysis"; no window may contain
  it (1984 has no complete window in any case).
- A tie between two days for a year's lowest mean takes the earlier day and names the other in a note.
- The last year in the file is preliminary while the file does not reach 31 December: NSIDC itself calls its September
  announcement "a preliminary announcement", and later days could be lower.
The daily file's Missing column (area of missing data, million km²) must be zero on every day of a minimum's window,
or the observation says how much was missing.

Publisher checks: NSIDC's announcement of 23 September 2026 (4.60 million km² on 12 September 2026, and the record
3.39 million km² on 17 September 2012), for version 4.0.

The minimum is not the September mean: both are shown, and neither replaces the other. OSI SAF's index (a different
algorithm) is a separate twin indicator, never mixed in.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "nsidc-sea-ice-index"
SEPTEMBER = Input(SOURCE, "north-monthly-september")
DAILY = Input(SOURCE, "north-daily-extent")
ENTITY = "NH"
MKM2 = Unit(code="million-km2", label="million square kilometres", short="million km²")

MONTHLY_COLUMNS = ["year", "mo", "source_dataset", "region", "extent", "area"]
DAILY_COLUMNS = ["Year", "Month", "Day", "Extent", "Missing", "Source Data"]
DAILY_UNITS = ["YYYY", "MM", "DD", "10^6 sq km", "10^6 sq km"]
AMSR2 = "NSIDC-0803"
WINDOW = 5
# User guide v4, "Daily Sea Ice Extent Data Files" (printed p. 26, read 2026-10-05): "The 14 September 1984 ice
# concentration field contains bad data, so the extent value is in error. The value is provided for completeness
# but should not be used in analysis."
BAD_DAYS = {date(1984, 9, 14): "NSIDC's user guide says the 14 September 1984 value is in error"}
VERSION_IN_URL = re.compile(r"_v(\d+\.\d+)\.csv$")

ANNOUNCEMENT_URL = "https://nsidc.org/sea-ice-today/analyses/arctic-sea-ice-minimum-ties-tenth-lowest-0"


class NsidcFormatError(ValueError):
    pass


def version_of(url: str | None) -> str:
    m = VERSION_IN_URL.search(url or "")
    if not m:
        raise NsidcFormatError(f"cannot read a Sea Ice Index version from {url!r}")
    return m.group(1)


def _published(f: InputFile) -> str | None:
    lm = f.snapshot.last_modified
    return parsedate_to_datetime(lm).date().isoformat() if lm else None


# --- September monthly extent ---------------------------------------------------------------------------------------


def parse_september(raw: bytes) -> list[Observation]:
    rows = list(csv.reader(io.StringIO(raw.decode("ascii")), skipinitialspace=True))
    header = [c.strip() for c in rows[0]]
    if header != MONTHLY_COLUMNS:
        raise NsidcFormatError(f"monthly file columns {header} != {MONTHLY_COLUMNS}")
    obs: list[Observation] = []
    for r in rows[1:]:
        if not r:
            continue
        year, mo, src, region, extent = (c.strip() for c in r[:5])
        if int(mo) != 9 or region != "N":
            raise NsidcFormatError(f"row {r}: expected month 9, region N")
        value = Decimal(extent)
        note = (
            f"NSIDC's file gives the source data set as {src}: JAXA's AMSR2 record, the input from 1 January 2025 "
            "(earlier years use the DMSP passive microwave record, NSIDC-0051)."
            if src == AMSR2
            else None
        )
        period = f"{int(year):04d}-09"
        if value < 0:
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=period,
                    value=None,
                    missing_reason=f"NSIDC's file has the sentinel {extent} instead of an extent.",
                    note=note,
                )
            )
        else:
            obs.append(Observation(entity=ENTITY, period=period, value=float(value), note=note))
    return obs


def _september(files: dict[str, InputFile]) -> Result:
    f = files[SEPTEMBER.key]
    version = version_of(str(f.snapshot.url) if f.snapshot.url else None)
    obs = parse_september(f.path.read_bytes())
    return Result(
        observations=obs,
        vintage=version,
        date_published=_published(f),
        steps=[
            f"Read the extent column of N_09_extent_v{version}.csv, NSIDC's Northern Hemisphere September file "
            f"(one row per year, {obs[0].period[:4]} to {obs[-1].period[:4]}), as printed in million km². NSIDC "
            "computes each value as the mean of the month's daily extents (cells with at least 15% ice "
            "concentration, the unobserved area around the pole counted as ice covered).",
            "Rows whose source data set is NSIDC-0803 (JAXA's AMSR2 record, used from 1 January 2025) carry that as "
            "a note.",
        ],
    )


# --- yearly minimum of the 5-day trailing mean ---------------------------------------------------------------------


@dataclass(frozen=True)
class Day:
    extent: Decimal
    missing: Decimal
    source: str


def parse_daily(raw: bytes) -> dict[date, Day]:
    rows = list(csv.reader(io.StringIO(raw.decode("ascii")), skipinitialspace=True))
    header = [c.strip() for c in rows[0]]
    units = [c.strip() for c in rows[1][:5]]
    if header != DAILY_COLUMNS or units != DAILY_UNITS:
        raise NsidcFormatError(f"daily file header {header} / {units} != {DAILY_COLUMNS} / {DAILY_UNITS}")
    days: dict[date, Day] = {}
    last: date | None = None
    for r in rows[2:]:
        if not r:
            continue
        if len(r) != 6:
            raise NsidcFormatError(f"daily row {r[:5]} has {len(r)} fields, expected 6")
        d = date(int(r[0]), int(r[1]), int(r[2]))
        if last is not None and d <= last:
            raise NsidcFormatError(f"daily rows out of order at {d}")
        last = d
        days[d] = Day(Decimal(r[3].strip()), Decimal(r[4].strip()), r[5])
    return days


def trailing_means(days: dict[date, Day]) -> dict[date, Decimal]:
    """Mean of each day and the four before it, where all five have a value and none is a day NSIDC says not to use."""
    out: dict[date, Decimal] = {}
    for d in days:
        window = [d - timedelta(k) for k in range(WINDOW)]
        if all(w in days and w not in BAD_DAYS for w in window):
            out[d] = sum((days[w].extent for w in window), Decimal(0)) / WINDOW
    return out


def _ranges(ds: list[date]) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    for d in sorted(ds):
        if out and d - out[-1][1] == timedelta(1):
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def _day(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def _span(a: date, b: date) -> str:
    return _day(a) if a == b else f"{_day(a)} to {_day(b)}"


@dataclass(frozen=True)
class Minima:
    observations: list[Observation]
    skipped_years: list[int]
    last_day: date


def yearly_minima(days: dict[date, Day]) -> Minima:
    means = trailing_means(days)
    first, last = min(days), max(days)
    by_year: dict[int, list[tuple[Decimal, date]]] = defaultdict(list)
    for d, m in means.items():
        by_year[d.year].append((m, d))
    skipped = [y for y in range(first.year, last.year + 1) if y not in by_year]
    obs: list[Observation] = []
    for y in sorted(by_year):
        low = min(m for m, _ in by_year[y])
        at = sorted(d for m, d in by_year[y] if m == low)
        notes: list[str] = []
        if len(at) > 1:
            notes.append(f"The same lowest 5-day mean is also reached on {', '.join(_day(d) for d in at[1:])}.")
        year_end = min(date(y, 12, 31), last)
        uncovered = [
            date(y, 1, 1) + timedelta(k)
            for k in range((year_end - date(y, 1, 1)).days + 1)
            if date(y, 1, 1) + timedelta(k) not in means
        ]
        if uncovered:
            notes.append(
                "No 5-day mean can be formed for "
                + "; ".join(_span(a, b) for a, b in _ranges(uncovered))
                + ", because NSIDC's file lacks a value for at least one day of those windows."
            )
        window = [at[0] - timedelta(k) for k in range(WINDOW)]
        missing = sum((days[w].missing for w in window), Decimal(0))
        if missing:
            notes.append(f"NSIDC's file reports missing data on days of this window (sum {missing} million km²).")
        if any(AMSR2 in days[w].source for w in window):
            notes.append("NSIDC computed these days from JAXA's AMSR2 record (NSIDC-0803), the input from 2025.")
        status = "final"
        if y == last.year and last < date(y, 12, 31):
            status = "preliminary"
            notes.append(f"The year is not over: the lowest 5-day mean from 1 January to {_day(last)}.")
        obs.append(
            Observation(
                entity=ENTITY,
                period=at[0].isoformat(),
                value=float(low),
                status=status,
                note=" ".join(notes) or None,
            )
        )
    return Minima(obs, skipped, last)


def _minimum(files: dict[str, InputFile]) -> Result:
    f = files[DAILY.key]
    version = version_of(str(f.snapshot.url) if f.snapshot.url else None)
    m = yearly_minima(parse_daily(f.path.read_bytes()))
    skipped = ", ".join(str(y) for y in m.skipped_years) or "none"
    return Result(
        observations=m.observations,
        vintage=version,
        date_published=_published(f),
        steps=[
            f"Read the Extent column of N_seaice_extent_daily_v{version}.csv (million km², data to "
            f"{_day(m.last_day)}).",
            "For every day whose four preceding days also have a value, took the mean of the five (NSIDC's 5-day "
            "trailing mean, exact decimal arithmetic). Windows with a missing day are skipped, never filled; no "
            "window may contain 14 September 1984, which NSIDC's user guide says is in error.",
            "For each calendar year, published the lowest of those means, dated by the day it ends on (the earlier "
            f"day if two tie). Years with no complete window are not published: {skipped} (the file has a value only "
            "every other day before 21 August 1987).",
            "The last year is marked preliminary until the file reaches 31 December.",
        ],
        changes="5-day trailing means of the daily extent, and the lowest of them in each year.",
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    geography = "Northern Hemisphere oceans (the Arctic Ocean and surrounding seas)"
    return [
        Transform(
            spec=Spec(
                id="sea-ice-extent.nsidc.arctic-september",
                title="Arctic sea ice extent in September (NSIDC)",
                description="Mean extent of Arctic sea ice in September, the month of the yearly minimum, since 1979: "
                "the area of ocean where satellites measure at least 15% ice cover, from NSIDC's Sea Ice Index. "
                "From 2025 NSIDC uses JAXA's AMSR2 satellite record instead of the DMSP record.",
                kind="series",
                unit=MKM2,
                display=Display(decimals=2),
                scope=Scope(
                    geography=geography,
                    basis="Sea ice extent: mean over the month of the daily area of grid cells with at least 15% ice "
                    "concentration (25 km grid, passive microwave), the unobserved area around the pole counted as "
                    "ice covered. Not sea ice area, and not OSI SAF's index.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(SEPTEMBER,),
            run=_september,
            module_file=here,
            validation=Validation(min_rows=47, value_range=(2.0, 9.0)),
        ),
        Transform(
            spec=Spec(
                id="sea-ice-extent.nsidc.arctic-minimum-5day",
                title="Arctic sea ice yearly minimum extent (NSIDC, 5-day mean)",
                description="The lowest Arctic sea ice extent of each year since 1987, on the 5-day trailing mean "
                "NSIDC uses for its minimum announcements, and the day it was reached. Earlier years are not shown: "
                "the satellite record then has a value only every other day.",
                kind="derived",
                unit=MKM2,
                display=Display(decimals=2),
                scope=Scope(
                    geography=geography,
                    basis="Lowest 5-day trailing mean of NSIDC's daily sea ice extent (area of cells with at least 15% "
                    "ice concentration) in each calendar year; the period is the last day of that 5-day window.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(DAILY,),
            run=_minimum,
            module_file=here,
            validation=Validation(min_rows=39, value_range=(2.0, 9.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="4.0",
                    entity=ENTITY,
                    period="2026-09-12",
                    stated="4.60",
                    quote="On September 12, Arctic sea ice likely reached its annual minimum extent of 4.60 million "
                    "square kilometers (1.78 million square miles).",
                    url=ANNOUNCEMENT_URL,
                ),
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="4.0",
                    entity=ENTITY,
                    period="2012-09-17",
                    stated="3.39",
                    quote="the satellite-era record minimum extent of 3.39 million square kilometers (1.31 million "
                    "square miles), which occurred on September 17, 2012",
                    url=ANNOUNCEMENT_URL,
                ),
            ),
        ),
    ]

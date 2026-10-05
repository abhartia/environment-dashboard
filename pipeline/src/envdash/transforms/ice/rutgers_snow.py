"""Northern Hemisphere snow cover extent by month, from the NOAA climate data record of weekly snow maps (Rutgers).

Input: nhsce_v01r01_19661004_<end>.nc from NCEI (found by the artifact's discover rule). It holds one map per week on
an 88 × 88 polar stereographic grid: snow_cover_extent(time, y, x) (0 no snow, 1 snow covered, -127 fill), land
(1 land, 0 water), area (km² per cell) and time in "days since 1966-10-03".

Weeks. Estilow et al. (2015, ESSD 7, 137, p. 139): "Starting from the beginning of the record on Tuesday, 4 October
1966, each weekly CDR granule represents 7 days spanning from Tuesday to Monday." The file's time values are the
Mondays: the first is 1966-10-10 and time_coverage_start is 1966-10-04, the last equals time_coverage_end. The build
stops unless every time value is a Monday, they are 7 days apart, and both coverage attributes agree with them.

Weekly extent. The paper (p. 140): "The area summation of all grid pixels that indicate snow in a given week generates
the weekly snow cover extent for the entire Northern Hemisphere." Cell areas are float32 values printed with one
decimal (10676.8 to 41804.6 km²); each is read as its shortest decimal form and summed exactly in tenths of km². A map
must be either complete (only 0 and 1, snow only on land cells) or entirely fill; anything else stops the build.
Entirely filled maps are the weeks with no satellite imagery: the paper lists the months they fall in as "July 1968,
June–October 1969, and July–September 1971".

Monthly extent. The CDR's algorithm description (C-ATBD CDRP-ATBD-0156 Rev 3, section 3.4.5) describes the look-up
table imsday-week-weight.txt as giving "the month, and the number of days each week falls within a given month", and
the README of the CDR code package says it holds "the number of days each week falls within a given month". So each
day of a month takes the extent of the weekly map covering it, and the month's value is the mean over its days: the
weekly extents weighted by the number of their days in the month (exact decimal arithmetic). Only whole months inside
the record are published (from November 1966 to the month of the last Monday, when that Monday is the month's last
day). A month with any day in a week without a map is published as missing, with the weeks named; nothing is filled.

Comparison, not a check. Rutgers Global Snow Lab publishes its own monthly table "based on NH SCE CDR v01r01"
(climate.rutgers.edu/snowcover/table_area.php?ui_set=1, read 2026-10-05; no licence is stated, so its values are not
used). Against the file of 3 September 2026, these monthly means equal that table's 0.01 million km² rounding in 365 of
709 months and are within 0.036 million km² in all of them (June 2026: 6.2316 here, 6.23 there); the same months are
missing in both. Assigning whole weeks to months instead (by their Monday, Tuesday or majority of days) differs from
it by 1.5 to 3.2 million km². Rutgers' routine is not in the CDR code package, so the small differences cannot be
traced and the table is not used as a publisher check.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import netCDF4
import numpy as np

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "rutgers-snow-cdr"
GRID = Input(SOURCE, "nhsce-weekly-grid")
ENTITY = "NH"
MKM2 = Unit(code="million-km2", label="million square kilometres", short="million km²")
TIME_UNITS = "days since 1966-10-03"
EPOCH = date(1966, 10, 3)
FILL = -127
WEEK = 7
TUESDAY_TO_MONDAY = 0  # date.weekday() of a Monday


class SnowFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Cdr:
    week_ends: list[date]
    weekly_tenths: list[int | None]
    """Snow-covered land area of each weekly map in tenths of km², or None for a week with no map."""
    product_version: str
    date_created: str
    coverage_end: date


def cell_tenths(area: np.ndarray) -> np.ndarray:
    """Each cell's area in tenths of km², from the shortest decimal form of its float32 value."""
    out = np.empty(area.shape, dtype=np.int64)
    for idx, x in np.ndenumerate(area):
        d = Decimal(np.format_float_positional(np.float32(x))) * 10
        if d != d.to_integral_value():
            raise SnowFormatError(f"cell area {x!r} has more than one decimal")
        out[idx] = int(d)
    return out


def weekly_tenths(snow: np.ndarray, land: np.ndarray, tenths: np.ndarray) -> list[int | None]:
    complete = ((snow == 0) | (snow == 1)).all(axis=(1, 2))
    empty = (snow == FILL).all(axis=(1, 2))
    bad = np.flatnonzero(~(complete | empty))
    if bad.size:
        raise SnowFormatError(f"weekly maps {bad.tolist()[:5]} are partly filled; expected complete or empty maps")
    if ((snow == 1) & (land == 0)).any():
        raise SnowFormatError("a map has snow on a water cell")
    sums = (snow == 1).reshape(snow.shape[0], -1).astype(np.int64) @ tenths.ravel()
    return [None if empty[i] else int(sums[i]) for i in range(snow.shape[0])]


def read_cdr(path: Path) -> Cdr:
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        t = ds["time"]
        if t.units != TIME_UNITS or t.calendar != "gregorian":
            raise SnowFormatError(f"time is {t.units!r} ({t.calendar}), expected {TIME_UNITS!r} (gregorian)")
        ends = [EPOCH + timedelta(int(x)) for x in t[:]]
        start = date.fromisoformat(ds.time_coverage_start)
        end = date.fromisoformat(ds.time_coverage_end)
        if any(e.weekday() != TUESDAY_TO_MONDAY for e in ends):
            raise SnowFormatError("a time value is not a Monday")
        if any((b - a).days != WEEK for a, b in pairwise(ends)):
            raise SnowFormatError("weekly maps are not 7 days apart")
        if ends[0] - timedelta(WEEK - 1) != start or ends[-1] != end:
            raise SnowFormatError(f"maps {ends[0]}..{ends[-1]} do not match time_coverage {start}..{end}")
        land = ds["land"][:].astype(np.int8)
        tenths = cell_tenths(ds["area"][:])
        weekly = weekly_tenths(ds["snow_cover_extent"][:], land, tenths)
        return Cdr(ends, weekly, ds.product_version, ds.date_created, end)


@dataclass(frozen=True)
class Month:
    period: str
    tenths: int
    days: int
    gap_weeks: tuple[date, ...]


def months(cdr: Cdr) -> list[Month]:
    """Each whole month inside the record: summed daily extent and the weeks without a map that cover its days."""
    per_day: dict[date, tuple[int | None, date]] = {}
    for end, v in zip(cdr.week_ends, cdr.weekly_tenths, strict=True):
        for k in range(WEEK):
            per_day[end - timedelta(k)] = (v, end)
    first, last = min(per_day), max(per_day)
    by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for d in per_day:
        by_month[(d.year, d.month)].append(d)
    out: list[Month] = []
    for (y, m), ds in sorted(by_month.items()):
        month_start = date(y, m, 1)
        month_end = date(y + m // 12, m % 12 + 1, 1) - timedelta(1)
        if month_start < first or month_end > last:
            continue
        gaps = sorted({per_day[d][1] for d in ds if per_day[d][0] is None})
        total = sum(per_day[d][0] or 0 for d in ds)
        out.append(Month(f"{y:04d}-{m:02d}", total, len(ds), tuple(gaps)))
    return out


def observations(ms: list[Month]) -> list[Observation]:
    obs: list[Observation] = []
    for m in ms:
        if m.gap_weeks:
            weeks = ", ".join(f"{d.day} {d:%B %Y}" for d in m.gap_weeks)
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=m.period,
                    value=None,
                    missing_reason=f"The CDR has no snow map for the week(s) ending {weeks}, which cover days of "
                    "this month (no satellite imagery).",
                )
            )
        else:
            value = Decimal(m.tenths) / (Decimal(10) * m.days * Decimal(1_000_000))
            obs.append(Observation(entity=ENTITY, period=m.period, value=float(value)))
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[GRID.key]
    cdr = read_cdr(f.path)
    obs = observations(months(cdr))
    gaps = [o.period for o in obs if o.value is None]
    created = datetime.fromisoformat(cdr.date_created.replace("Z", "+00:00"))
    return Result(
        observations=obs,
        vintage=f"{cdr.product_version} to {cdr.coverage_end.isoformat()}",
        date_published=created.date().isoformat(),
        steps=[
            f"Read the {len(cdr.week_ends):,} weekly maps of the NOAA snow cover extent CDR ({cdr.product_version}, "
            f"file created {created.day} {created:%B %Y}, weeks ending {cdr.week_ends[0]} to {cdr.week_ends[-1]}). "
            "Each map covers the seven days from Tuesday to the Monday it is dated.",
            "Weekly extent: the summed area of the land cells marked snow covered (cell areas as printed to 0.1 km², "
            "exact arithmetic).",
            "Monthly extent: each day takes the extent of the weekly map covering it, and the month is the mean over "
            "its days, i.e. weekly extents weighted by their number of days in the month (the CDR's own week-month "
            "day counts). Converted from km² to million km².",
            f"Only whole months inside the record are published. Months with a day in a week without a map are "
            f"published as missing, never filled: {', '.join(gaps) or 'none'}.",
        ],
        changes="weekly snow maps summed to areas and averaged by month (weighted by days), in million km².",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="snow-cover.rutgers-snow-cdr.nh-monthly",
                title="Northern Hemisphere snow cover extent by month",
                description="Area of Northern Hemisphere land covered by snow, as a monthly mean since November 1966, "
                "computed from the weekly snow maps of the NOAA climate data record made at Rutgers University. "
                "Before June 1999 the maps were drawn by NOAA analysts from satellite images; since then they come "
                "from the US National Ice Center's daily snow and ice analysis. Nine months in 1968-1971 have no "
                "maps.",
                kind="derived",
                unit=MKM2,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Northern Hemisphere land, including Greenland (the CDR's land mask, 88 × 88 grid of "
                    "cells from about 10,700 to 41,800 km²)",
                    basis="Monthly mean of weekly snow cover extent, each week weighted by its days in the month; a "
                    "week's extent is the total area of land cells charted as snow covered (from June 1999, cells "
                    "where at least 42% of the daily analysis' land pixels show snow).",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(GRID,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=700, value_range=(0.5, 60.0)),
        )
    ]

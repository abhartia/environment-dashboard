"""Northern Hemisphere snow cover by month (envdash/transforms/ice/rutgers_snow.py).

The input is a 24.6 MB NetCDF file. A byte-exact slice of it is not a readable NetCDF file, so there is no committed
fixture: the tests that read data are marked `snapshot` and read the current snapshot from the local cache (the
NCEI file nhsce_v01r01_19661004_20260831.nc, created 3 September 2026, until NCEI replaces it).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.ice import rutgers_snow as snow


def test_registered_with_one_input_and_unit():
    [t] = snow.transforms(Paths.default())
    assert t.spec.id == "snow-cover.rutgers-snow-cdr.nh-monthly"
    assert t.inputs == (snow.GRID,) and t.spec.unit.code == "million-km2"


def _current() -> InputFile:
    paths = Paths.default()
    sha = snapshots.read_current(paths)[snow.GRID.key]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    return InputFile(Path(snapshots.cache_path(paths, sha)), snap)


@pytest.mark.snapshot
def test_weeks_run_tuesday_to_monday_and_gaps_are_whole_maps():
    cdr = snow.read_cdr(_current().path)
    assert cdr.week_ends[0] == date(1966, 10, 10) and cdr.product_version == "v01r01"
    assert all(e.weekday() == 0 for e in cdr.week_ends)
    missing = [e for e, v in zip(cdr.week_ends, cdr.weekly_tenths, strict=True) if v is None]
    # The paper's missing months (July 1968, June-October 1969, July-September 1971) are these 37 weeks.
    assert len(missing) == 37
    assert missing[0] == date(1968, 7, 8) and missing[-1] == date(1971, 9, 27)


@pytest.mark.snapshot
def test_monthly_means_and_missing_months():
    f = _current()
    [t] = snow.transforms(Paths.default())
    result = t.run({snow.GRID.key: f})
    validate(t, result.observations)
    by = {o.period: o for o in result.observations}
    assert result.observations[0].period == "1966-11"
    assert [o.period for o in result.observations if o.value is None] == [
        "1968-07",
        "1969-06",
        "1969-07",
        "1969-08",
        "1969-09",
        "1969-10",
        "1971-07",
        "1971-08",
        "1971-09",
    ]
    if f.snapshot.sha256 == "1268766f7fbf2d314c31d16bdc6dd550d3972fb3371b1ba7d3e55638727f9d69":
        assert result.vintage == "v01r01 to 2026-08-31"
        assert result.observations[-1].period == "2026-08"
        # Regression values (our own computation; Rutgers' own table prints 6.23 and 2.67).
        assert round(by["2026-06"].value, 4) == 6.2316
        assert round(by["2026-08"].value, 4) == 2.6746


@pytest.mark.snapshot
def test_a_month_is_the_day_weighted_mean_of_its_weeks():
    cdr = snow.read_cdr(_current().path)
    weekly = dict(zip(cdr.week_ends, cdr.weekly_tenths, strict=True))
    # June 2026: weeks ending Mondays 1, 8, 15, 22 and 29 June and 6 July cover its 30 days with 1, 7, 7, 7, 7 and 1
    # days.
    weights = {
        date(2026, 6, 1): 1,
        date(2026, 6, 8): 7,
        date(2026, 6, 15): 7,
        date(2026, 6, 22): 7,
        date(2026, 6, 29): 7,
        date(2026, 7, 6): 1,
    }
    expected = sum(weekly[d] * w for d, w in weights.items())
    june = next(m for m in snow.months(cdr) if m.period == "2026-06")
    assert june.days == 30 and june.tenths == expected and not june.gap_weeks

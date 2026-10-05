"""NSIDC Sea Ice Index v4 transforms (envdash/transforms/ice/nsidc_sea_ice.py).

Fixtures: the whole N_09_extent_v4.0.csv, and N_seaice_extent_daily_v4.0.csv cut to its first 1,724 data rows (26
October 1978 to 20 January 1988, with the every-other-day SMMR years and the December 1987 gap) and its last 641 (1
January 2025 to 3 October 2026), both of the 2026-10-05 snapshot.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from envdash import canonical, snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.ice import nsidc_sea_ice as nsidc

from support import fixture


def _input(artifact_id: str) -> InputFile:
    path, meta = fixture(nsidc.SOURCE, artifact_id)
    data = path.read_bytes()
    snap = Snapshot(
        sha256=canonical.sha256_bytes(data),
        bytes=len(data),
        source_id=nsidc.SOURCE,
        artifact_id=artifact_id,
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    return InputFile(path, snap)


def _transform(indicator_id: str):
    return next(t for t in nsidc.transforms(Paths.default()) if t.spec.id == indicator_id)


def _daily():
    return nsidc.parse_daily(fixture(nsidc.SOURCE, "north-daily-extent")[0].read_bytes())


def test_september_as_printed_with_amsr2_notes():
    obs = nsidc.parse_september(fixture(nsidc.SOURCE, "north-monthly-september")[0].read_bytes())
    by = {o.period: o for o in obs}
    assert len(obs) == 48 and obs[0].period == "1979-09" and obs[-1].period == "2026-09"
    assert by["1979-09"].value == 7.05 and by["2012-09"].value == 3.57 and by["2026-09"].value == 4.81
    assert by["2024-09"].note is None
    assert "NSIDC-0803" in by["2025-09"].note and "NSIDC-0803" in by["2026-09"].note
    assert all(o.entity == "NH" and o.status == "final" for o in obs)


def test_september_run_and_validation():
    t = _transform("sea-ice-extent.nsidc.arctic-september")
    result = t.run({nsidc.SEPTEMBER.key: _input("north-monthly-september")})
    validate(t, result.observations)
    assert result.vintage == "4.0"


def test_trailing_mean_needs_five_consecutive_days():
    days = _daily()
    means = nsidc.trailing_means(days)
    # Every other day until 20 August 1987: no window before 24 August 1987.
    assert min(means) == date(1987, 8, 24)
    # The December 1987 to January 1988 gap, and the fixture's own cut before 1 January 2025, are not filled.
    assert date(1987, 12, 2) in means and date(1987, 12, 3) not in means
    assert date(2025, 1, 4) not in means and date(2025, 1, 5) in means
    # The mean of 8 to 12 September 2026, in exact decimals of the printed values.
    window = [days[date(2026, 9, d)].extent for d in range(8, 13)]
    assert means[date(2026, 9, 12)] == sum(window) / 5


def test_yearly_minima_from_the_fixture():
    m = nsidc.yearly_minima(_daily())
    by = {o.period[:4]: o for o in m.observations}
    # 1978-1986 have values only every other day; 1989-2024 are cut out of the fixture.
    assert m.skipped_years == [*range(1978, 1987), *range(1989, 2025)]
    assert by["1987"].period == "1987-09-05" and by["1987"].value == 6.963
    assert "1 January 1987 to 23 August 1987" in by["1987"].note
    assert "3 December 1987 to 31 December 1987" in by["1987"].note
    assert by["2025"].period == "2025-09-10" and round(by["2025"].value, 4) == 4.6018
    assert by["2025"].status == "final"
    assert by["2026"].period == "2026-09-12" and by["2026"].value == 4.5976
    assert by["2026"].status == "preliminary" and "3 October 2026" in by["2026"].note
    assert "NSIDC-0803" in by["2026"].note


def test_minimum_publisher_check_for_2026():
    t = _transform("sea-ice-extent.nsidc.arctic-minimum-5day")
    result = t.run({nsidc.DAILY.key: _input("north-daily-extent")})
    assert result.vintage == "4.0"
    outcomes = {c.check.period: c for c in run_checks(t, {nsidc.SOURCE: result.vintage}, result.observations)}
    assert outcomes["2026-09-12"].status == "pass"
    # 2012 is not in the fixture; the full-file test below checks it.
    assert outcomes["2012-09-17"].status == "fail"


def test_daily_header_must_match():
    raw = fixture(nsidc.SOURCE, "north-daily-extent")[0].read_bytes()
    with pytest.raises(nsidc.NsidcFormatError, match="header"):
        nsidc.parse_daily(raw.replace(b"10^6 sq km", b"km^2", 1))


def test_version_from_url():
    _, meta = fixture(nsidc.SOURCE, "north-daily-extent")
    assert nsidc.version_of(meta["url"]) == "4.0"
    with pytest.raises(nsidc.NsidcFormatError):
        nsidc.version_of(meta["url"].replace("_v4.0.csv", ".csv"))


@pytest.mark.snapshot
def test_full_daily_file_passes_both_checks():
    paths = Paths.default()
    key = snapshots.key(nsidc.SOURCE, "north-daily-extent")
    sha = snapshots.read_current(paths)[key]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    t = _transform("sea-ice-extent.nsidc.arctic-minimum-5day")
    result = t.run({nsidc.DAILY.key: InputFile(Path(snapshots.cache_path(paths, sha)), snap)})
    validate(t, result.observations)
    by = {o.period[:4]: o for o in result.observations}
    assert by["2012"].period == "2012-09-17" and round(by["2012"].value, 2) == 3.39
    assert by["1988"].period == "1988-09-12" and "1 January 1988 to 16 January 1988" in by["1988"].note
    assert all(c.status == "pass" for c in run_checks(t, {nsidc.SOURCE: "4.0"}, result.observations))

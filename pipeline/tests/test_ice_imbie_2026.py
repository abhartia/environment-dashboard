"""IMBIE 2026 ice-sheet transforms (envdash/transforms/ice/imbie_2026.py).

Fixtures: the Greenland and Antarctica Gt and mm files cut to their header and first and last 24 monthly rows.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.ice import imbie_2026 as imbie

from support import fixture


def _raw(artifact_id: str) -> bytes:
    return fixture(imbie.SOURCE, artifact_id)[0].read_bytes()


def _table(sheet: imbie.Sheet, unit: str) -> imbie.Table:
    return imbie.read_table(_raw(f"{sheet.key}-{unit.lower()}"), sheet, unit)


def _transform(indicator_id: str):
    return next(t for t in imbie.transforms(Paths.default()) if t.spec.id == indicator_id)


def test_greenland_mass_as_printed_with_one_sigma():
    t = _table(imbie.GREENLAND, "Gt")
    assert t.version == "1.0" and t.coverage_start == "1971-07-01" and t.coverage_end == "2023-12-01"
    obs = imbie.mass_observations(t, imbie.GREENLAND)
    first, last = obs[0], obs[-1]
    # The first month already holds one month at the first yearly rate: 65.9465 / 12.
    assert first.period == "1971-07" and first.value == 5.495541667
    assert last.period == "2023-12" and last.value == -6196.145791 and last.entity == "GRL"
    assert last.interval == "1sigma"
    assert Decimal(str(last.upper)) - Decimal(str(last.lower)) == 2 * Decimal("467.3542395")


def test_sea_level_is_the_mm_column_with_the_sign_flipped():
    for sheet, expected in ((imbie.GREENLAND, 17.21151609), (imbie.ANTARCTICA, 13.27631111)):
        obs = imbie.sea_level_observations(_table(sheet, "Gt"), _table(sheet, "mm"), sheet)
        assert obs[-1].period == "2023-12" and obs[-1].value == expected
        assert obs[-1].lower < obs[-1].value < obs[-1].upper


def test_mm_must_be_gt_over_360():
    sheet = imbie.ANTARCTICA
    # The last row of the real mm file, with its cumulative value changed in the third decimal.
    mm = imbie.read_table(_raw("antarctica-mm").replace(b"-13.27631111", b"-13.27931111", 1), sheet, "mm")
    with pytest.raises(imbie.ImbieFormatError, match="Gt/360"):
        imbie.sea_level_observations(_table(sheet, "Gt"), mm, sheet)


def test_antarctic_publisher_check():
    sheet = imbie.ANTARCTICA
    obs = imbie.sea_level_observations(_table(sheet, "Gt"), _table(sheet, "mm"), sheet)
    t = _transform("sea-level-contribution.imbie-2026.antarctica")
    [outcome] = run_checks(t, {imbie.SOURCE: "1.0"}, obs)
    assert outcome.status == "pass"


def test_months_must_be_consecutive():
    # The fixture's cut (row 24 then row 607) is exactly the kind of gap the check refuses.
    with pytest.raises(imbie.ImbieFormatError, match="not consecutive"):
        imbie.check_months(_table(imbie.GREENLAND, "Gt"))


def test_header_must_say_one_sigma_and_name_the_sheet():
    raw = _raw("greenland-gt")
    with pytest.raises(imbie.ImbieFormatError, match="one sigma"):
        imbie.read_table(raw.replace(b"one sigma", b"two sigma", 1), imbie.GREENLAND, "Gt")
    with pytest.raises(imbie.ImbieFormatError, match="data_type"):
        imbie.read_table(raw, imbie.ANTARCTICA, "Gt")


@pytest.mark.snapshot
def test_full_files_build_all_four():
    paths = Paths.default()
    current = snapshots.read_current(paths)
    for t in imbie.transforms(paths):
        files = {}
        for i in t.inputs:
            sha = current[i.key]
            snap = snapshots.read_manifest(paths, sha)
            assert snap is not None
            files[i.key] = InputFile(Path(snapshots.cache_path(paths, sha)), snap)
        result = t.run(files)
        validate(t, result.observations)
        assert all(c.status == "pass" for c in run_checks(t, {imbie.SOURCE: result.vintage}, result.observations))

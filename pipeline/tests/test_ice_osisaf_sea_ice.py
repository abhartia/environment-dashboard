"""OSI SAF Sea-Ice Index v3.0 September extent (envdash/transforms/ice/osisaf_sea_ice.py).

Fixture: the whole ice_extent_nh_sii-v3p0_monthly.txt of the 2026-10-04 run (created 2026-10-04 09:36:46).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from envdash import canonical
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.ice import osisaf_sea_ice as osisaf

from support import fixture


def _raw() -> bytes:
    return fixture(osisaf.SOURCE, "nh-extent-monthly")[0].read_bytes()


def test_septembers_in_million_km2():
    obs, created = osisaf.parse_september(_raw())
    by = {o.period: o for o in obs}
    assert created == datetime(2026, 10, 4, 9, 36, 46)
    # 1978 is -999 (the record starts in late October 1978) and is left out.
    assert len(obs) == 48 and obs[0].period == "1979-09" and obs[-1].period == "2026-09"
    # 7488542 and 5341947 km² in the file.
    assert by["1979-09"].value == 7.488542 and by["2026-09"].value == 5.341947
    assert all(o.value is not None and o.entity == "NH" for o in obs)


def test_a_september_in_progress_is_not_published():
    raw = _raw().replace(b"# Creation date: 2026-10-04", b"# Creation date: 2026-09-20", 1)
    obs, _ = osisaf.parse_september(raw)
    assert obs[-1].period == "2025-09"


def test_rows_must_have_five_fields():
    raw = _raw().replace(b"2026 09 16 5341947", b"2026 09 16 5341947 OSI438AFT", 1)
    with pytest.raises(osisaf.OsisafFormatError, match="5"):
        osisaf.parse_september(raw)


def test_header_must_name_the_product():
    raw = _raw().replace(b"Sea Ice Index v3.0", b"Sea Ice Index v2.3", 1)
    with pytest.raises(osisaf.OsisafFormatError, match="header"):
        osisaf.parse_september(raw)


def test_run_and_validation():
    path, meta = fixture(osisaf.SOURCE, "nh-extent-monthly")
    data = path.read_bytes()
    snap = Snapshot(
        sha256=canonical.sha256_bytes(data),
        bytes=len(data),
        source_id=osisaf.SOURCE,
        artifact_id="nh-extent-monthly",
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    t = osisaf.transforms(Paths.default())[0]
    result = t.run({osisaf.MONTHLY.key: InputFile(path, snap)})
    validate(t, result.observations)
    assert result.vintage == "3.0" and result.date_published == "2026-10-04"
    assert osisaf.version_of(meta["url"]) == "3.0"

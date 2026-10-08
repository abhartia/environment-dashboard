"""Net Zero Tracker, Net Zero Stocktake 2025 dataset (envdash/transforms/action/net_zero_tracker.py).

The Tracker's data are CC BY-NC 4.0 (the stricter of its two statements), so no fixture is committed (fixtures are cut
only from open-class sources whose raw files may be re-hosted); the tests that read the file use the full snapshot
from the local cache and are marked `snapshot`.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.action import net_zero_tracker as nzt


def test_eu_is_published_as_eu27():
    assert nzt.entity("EUU") == "EU27"
    assert nzt.entity("USA") == "USA"


def test_a_file_other_than_the_deposit_is_refused():
    with pytest.raises(nzt.NetZeroTrackerFormatError, match="md5"):
        nzt.read_rows(b"Country,Entity_type\r\n")


def _current() -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[nzt.CSV.key]
    return InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))


def _rows() -> list[dict[str, str]]:
    return nzt.read_rows(_current().path.read_bytes())


@pytest.mark.snapshot
def test_counts_are_the_trackers():
    _, t = nzt.transforms(Paths.default())
    assert t.spec.id == nzt.COUNTS
    result = t.run({nzt.CSV.key: _current()})
    validate(t, result.observations)
    by = {o.dims["status"]: o.value for o in result.observations}
    # Data_finalised_for_Zenodo_16_09(Sheet1).csv, Entity_type Country: 198 rows, 137 with data_is_nzt 1.
    assert by == {
        "any-net-zero-target": 137,
        "achieved-self-declared": 4,
        "in-law": 34,
        "in-policy-document": 58,
        "declaration-pledge": 14,
        "proposed-in-discussion": 27,
        "other-end-target": 57,
        "no-target": 4,
    }
    assert all(o.entity == "WLD" and o.period == "2025-09-17" for o in result.observations)
    (check,) = run_checks(t, {nzt.SOURCE: nzt.VINTAGE}, result.observations)
    assert check.status == "pass"


@pytest.mark.snapshot
def test_each_country_has_its_target_year_and_status():
    t, _ = nzt.transforms(Paths.default())
    result = t.run({nzt.CSV.key: _current()})
    validate(t, result.observations)
    assert len(result.observations) == 198
    by = {o.entity: o for o in result.observations}
    assert by["EU27"].value == 2050 and by["EU27"].dims["status"] == "in-law"
    assert by["IND"].value == 2070 and by["IND"].dims["status"] == "in-law"
    assert by["CHN"].value == 2060 and by["CHN"].dims["status"] == "in-policy-document"
    assert "Carbon neutral(ity)" in (by["CHN"].note or "")
    usa = by["USA"]
    assert usa.value is None and usa.dims["status"] == "no-target"
    afg = by["AFG"]
    assert afg.value is None and afg.dims["status"] == "other-end-target"
    assert "Reduction v. BAU" in (afg.missing_reason or "")


@pytest.mark.snapshot
def test_a_flag_that_disagrees_with_the_label_stops_the_build():
    row = dict(next(r for r in _rows() if r["Country"] == "CHN"))
    row["data_is_nzt"] = "0"
    with pytest.raises(nzt.NetZeroTrackerFormatError, match="data_is_nzt"):
        nzt.target(row)


@pytest.mark.snapshot
def test_an_unknown_status_or_target_label_stops_the_build():
    row = dict(next(r for r in _rows() if r["Country"] == "CHN"))
    row["Status_of_end_target"] = "Under review"
    with pytest.raises(nzt.NetZeroTrackerFormatError, match="Under review"):
        nzt.target(row)
    row = dict(next(r for r in _rows() if r["Country"] == "AFG"))
    row["End_target"] = "Intensity target"
    with pytest.raises(nzt.NetZeroTrackerFormatError, match="Intensity target"):
        nzt.target(row)

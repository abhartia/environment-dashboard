"""Systems Change Lab: share of outcome indicators by progress status, IEA-sourced indicators excluded
(envdash/transforms/action/systems_change_lab.py).

The export carries IEA and other third-party data (mirror_raw false), so no fixture is committed; the tests that read
it use the full snapshot from the local cache and are marked `snapshot`.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.action import systems_change_lab as scl


def test_iea_is_recognised_in_any_spelling_the_export_uses():
    # Provider values from the export of 2026-10-05.
    assert scl.IEA.search("IEA")
    assert scl.IEA.search("IEA, IRENA, UNSD, World Bank, WHO")
    assert scl.IEA.search("https://www.iea.org/data-and-statistics")
    assert not scl.IEA.search("IRENA")
    assert not scl.IEA.search("Ember")


def _current() -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[scl.EXPORT.key]
    return InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))


def _rezip(change) -> bytes:
    """The real export with one metadata file changed, to show what is refused."""
    src = zipfile.ZipFile(io.BytesIO(_current().path.read_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            dst.writestr(name, change(name, data))
    return out.getvalue()


@pytest.mark.snapshot
def test_shares_from_the_real_export():
    (t,) = scl.transforms(Paths.default())
    result = t.run({scl.EXPORT.key: _current()})
    validate(t, result.observations)
    assert abs(sum(o.value for o in result.observations if o.value is not None) - 100) < 1e-9
    by = {o.dims["status"]: o for o in result.observations}
    assert by["on-track"].note == "1 of 179 outcome indicators: FIN-1."
    by_status, iea, n = scl.classify(_current().path.read_bytes())
    assert n == 438 and len(iea) == 17 and "PWR-41" in iea
    assert all(not code.startswith("PWR-41") for codes in by_status.values() for code in codes)


@pytest.mark.snapshot
def test_an_unknown_status_is_refused():
    def change(name: str, data: bytes) -> bytes:
        return data.replace(b'"Insufficient Data"', b'"Unclear"') if name == "BLDG-1/BLDG-1_metadata.csv" else data

    with pytest.raises(scl.SclFormatError, match="Unclear"):
        scl.classify(_rezip(change))


@pytest.mark.snapshot
def test_an_indicator_without_data_sources_is_refused():
    def change(name: str, data: bytes) -> bytes:
        return data.split(b'"Data source(s):"')[0] if name == "BLDG-1/BLDG-1_metadata.csv" else data

    with pytest.raises(scl.SclFormatError, match="BLDG-1"):
        scl.classify(_rezip(change))

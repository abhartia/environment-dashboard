"""IPCC AR6 WGI SPM B.5.3 sea level projections (envdash/transforms/ocean/ipcc_ar6_sea_level.py).

The SPM is display-only (IPCC copyright), so there is no committed fixture: the tests that read the PDF use the real
snapshot from the cache and are marked `snapshot` (run with `uv run pytest -m snapshot` after
`uv run envdash fetch -s ipcc-ar6-wg1-spm`). The others check the transform against its own quote.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.literature import QuoteNotFound, verify_quote
from envdash.transforms.ocean import ipcc_ar6_sea_level as sl

ID = "gmsl.ipcc-ar6.rise-2100-likely"


def _transform():
    (t,) = sl.transforms(Paths.default())
    return t


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_transform_declares_a_registered_display_only_input():
    t = _transform()
    assert t.spec.id == ID and t.spec.kind == "published-value"
    src = load_registry(Paths.default()).sources[sl.SOURCE]
    assert src.licence_class == "display-only" and src.obligations.mirror_raw is False
    assert [i.key for i in t.inputs] == [f"{sl.SOURCE}/spm-pdf"]
    assert {a.id for a in src.artifacts} == {"spm-pdf"}
    assert t.spec.scope.baseline == "1995–2014"


def test_table_equals_the_quote():
    sl.check_table(sl.QUOTE)
    assert sl.ranges_in_quote(sl.QUOTE) == {
        "SSP1-1.9": ("0.28", "0.55"),
        "SSP1-2.6": ("0.32", "0.62"),
        "SSP2-4.5": ("0.44", "0.76"),
        "SSP5-8.5": ("0.63", "1.01"),
    }


def test_the_2150_ranges_are_not_read_as_2100():
    # The quote's 2150 clause names the same scenarios; only the 2100 clause is read.
    assert "0.98–1.88" in sl.QUOTE
    assert ("0.98", "1.88") not in sl.ranges_in_quote(sl.QUOTE).values()


def test_a_quote_that_differs_from_the_table_is_refused():
    with pytest.raises(sl.SpmQuoteError, match="differ"):
        sl.check_table(sl.QUOTE.replace("0.44–0.76 m", "0.45–0.76 m"))


def test_observations_are_both_ends_of_each_range():
    obs = sl.observations()
    assert len(obs) == 8
    assert all(o.status == "projection" and o.period == "2100" and o.entity == "WLD" for o in obs)
    by = {(o.dims["scenario"], o.dims["bound"]): o.value for o in obs}
    assert by[("ssp585", "likely-high")] == 1.01 and by[("ssp119", "likely-low")] == 0.28
    validate(_transform(), obs)


# --- real snapshot (cache) ----------------------------------------------------------------------------------------


def _current() -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[sl.SPM.key]
    snap = snapshots.read_manifest(p, sha)
    assert isinstance(snap, Snapshot)
    return InputFile(snapshots.cache_path(p, sha), snap)


@pytest.mark.snapshot
def test_quote_is_on_page_21_of_the_spm():
    f = _current()
    assert f.snapshot.bytes == 3_361_797
    verify_quote(f.path.read_bytes(), sl.PDF_PAGE, sl.QUOTE)
    result = _transform().run({sl.SPM.key: f})
    assert len(result.observations) == 8
    assert result.published_value and result.published_value.locator == sl.LOCATOR


@pytest.mark.snapshot
def test_a_changed_number_is_not_on_the_page():
    with pytest.raises(QuoteNotFound):
        verify_quote(_current().path.read_bytes(), sl.PDF_PAGE, sl.QUOTE.replace("0.63–1.01", "0.63–1.10"))

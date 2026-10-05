"""AVISO global mean sea level transforms (envdash/transforms/ocean/aviso_gmsl.py).

The AVISO licence bars re-hosting the unmodified product (registry: open, mirror_raw false), and committed fixtures
are cut only from sources whose raw file may be re-hosted (tests/fixtures/make_fixture.py). So the value tests read
the real NetCDF and product page from the snapshot cache and are marked `snapshot` (run with
`uv run pytest -m snapshot` after `uv run envdash fetch -s aviso-gmsl`). The tests that need no raw data check the
transform's declarations and its reading of AVISO's own sentence.
"""

from __future__ import annotations

import math
import shutil
from datetime import date
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from envdash import snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.literature import QuoteNotFound, verify_quote_in_document
from envdash.transforms.ocean import aviso_gmsl as av

IDS = {"gmsl.aviso.monthly", "gmsl.aviso.rate"}


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_transforms_declare_registered_inputs():
    paths = Paths.default()
    ts = {t.spec.id: t for t in av.transforms(paths)}
    assert set(ts) == IDS
    src = load_registry(paths).sources[av.SOURCE]
    assert src.licence_class == "open" and src.obligations.mirror_raw is False
    assert "Modified from the original" in (src.obligations.attribution_modified or "")
    artifacts = {a.id for a in src.artifacts}
    for t in ts.values():
        assert {i.source_id for i in t.inputs} == {av.SOURCE}
        assert {i.artifact_id for i in t.inputs} <= artifacts
    assert ts["gmsl.aviso.monthly"].spec.unit.code == "mm"
    assert ts["gmsl.aviso.monthly"].spec.scope.baseline.startswith("1993 mean")
    assert ts["gmsl.aviso.rate"].spec.kind == "published-value"
    assert av.PRODUCT_DOI.removeprefix("https://doi.org/") == src.citation.DOI


def test_stated_rate_is_read_from_the_sentence():
    s = av.stated_rate(av.RATE_QUOTE)
    assert (s.value, s.half_width, s.from_year) == (av.Decimal("3.6"), av.Decimal("0.3"), 1999)
    assert av.RATE_VALUE_TEXT in av.RATE_QUOTE


def test_a_sentence_without_the_interval_is_refused():
    with pytest.raises(av.AvisoFormatError, match="cannot read"):
        av.stated_rate(av.RATE_QUOTE.replace(", 90%CI", ""))


def test_months_run_through_year_ends():
    assert av._months("1993-11", "1994-02") == ["1993-11", "1993-12", "1994-01", "1994-02"]


# --- real snapshots (cache) ---------------------------------------------------------------------------------------


def _current(artifact_id: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[f"{av.SOURCE}/{artifact_id}"]
    snap = snapshots.read_manifest(p, sha)
    assert isinstance(snap, Snapshot)
    return InputFile(snapshots.cache_path(p, sha), snap)


def _edited_nc(tmp_path: Path, edit) -> bytes:
    """The real NetCDF with one change applied through netCDF4 (to show that a changed file is refused)."""
    out = tmp_path / "edited.nc"
    shutil.copy(_current(av.NC.artifact_id).path, out)
    with netCDF4.Dataset(out, mode="a") as ds:
        edit(ds)
    return out.read_bytes()


@pytest.mark.snapshot
def test_record_of_26_september_2026():
    rec = av.read_record(_current(av.NC.artifact_id).path.read_bytes())
    assert rec.created == date(2026, 9, 26)
    assert (rec.first_date, rec.end_date) == (date(1993, 1, 5), date(2026, 8, 15))
    assert len(rec.times) == 1236
    assert rec.msl_m[0] == 0.0020695430973826376 and rec.msl_m[-1] == 0.11810054310168677


@pytest.mark.snapshot
def test_the_txt_and_the_netcdf_hold_the_same_values():
    # The registry's TXT (decimal year, msl, envelope) and the NetCDF msl variable are the same series.
    rec = av.read_record(_current(av.NC.artifact_id).path.read_bytes())
    rows = [ln.split() for ln in _current("msl-global-filter2m-txt").path.read_text().splitlines()]
    assert [float(r[1]) for r in rows] == rec.msl_m


@pytest.mark.snapshot
def test_monthly_change_since_1993():
    rec = av.read_record(_current(av.NC.artifact_id).path.read_bytes())
    mon = av.monthly_change(rec)
    obs = mon.observations
    assert len(obs) == 403 and obs[0].period == "1993-01" and obs[-1].period == "2026-07"
    assert mon.dropped_month == "2026-08"
    assert mon.cycles_per_month == {2: 9, 3: 360, 4: 34}
    # January 1993 is the mean of the first three cycles, less the 1993 baseline.
    jan = math.fsum(rec.msl_m[:3]) / 3
    assert obs[0].value == pytest.approx((jan - mon.baseline_m) * 1000, abs=1e-12)
    assert mon.baseline_m == pytest.approx(0.007232964915631773, abs=1e-15)
    assert math.fsum(o.value for o in obs[:12]) == pytest.approx(0, abs=1e-9)
    assert obs[-1].value == pytest.approx(111.7744299608096, abs=1e-9)
    # AVISO's page: "Since February 1993, the GMSL has risen by approximately 11 cm." The same file gives 114.7 mm
    # from February 1993 to July 2026: a rounded statement, compared here only and recorded, not adjusted.
    by = {o.period: o.value for o in obs}
    assert by["2026-07"] - by["1993-02"] == pytest.approx(114.739, abs=1e-3)


@pytest.mark.snapshot
def test_the_monthly_series_passes_validation():
    f = _current(av.NC.artifact_id)
    t = next(t for t in av.transforms(Paths.default()) if t.spec.id == "gmsl.aviso.monthly")
    result = t.run({av.NC.key: f})
    validate(t, result.observations)
    assert result.vintage == "2026-09-26 (doi:10.24400/527896/AVISO-2025.010)"
    assert result.changes and "re-based" in result.changes


@pytest.mark.snapshot
def test_rate_is_quoted_and_consistent_with_the_file():
    page = _current(av.PAGE.artifact_id)
    nc = _current(av.NC.artifact_id)
    t = next(t for t in av.transforms(Paths.default()) if t.spec.id == "gmsl.aviso.rate")
    result = t.run({av.PAGE.key: page, av.NC.key: nc})
    (o,) = result.observations
    assert (o.value, o.lower, o.upper, o.interval) == (3.6, 3.3, 3.9, "90ci")
    assert o.period == "1999/2026" and o.status == "final"
    assert result.published_value and result.published_value.quote == av.RATE_QUOTE
    rec = av.read_record(nc.path.read_bytes())
    assert round(av.ols_rate_mm_per_year(rec, date(1999, 1, 1)), 2) == 3.67


@pytest.mark.snapshot
def test_a_rate_not_on_the_page_is_refused():
    page = _current(av.PAGE.artifact_id)
    with pytest.raises(QuoteNotFound):
        verify_quote_in_document(
            page.path.read_bytes(),
            page.snapshot.content_type,
            str(page.snapshot.url),
            av.RATE_QUOTE.replace("3.6 mm", "3.4 mm"),
        )


@pytest.mark.snapshot
def test_another_product_doi_is_refused(tmp_path):
    raw = _edited_nc(tmp_path, lambda ds: ds.setncattr("doi", "https://doi.org/10.24400/527896/AVISO-2026.001"))
    with pytest.raises(av.AvisoFormatError, match="doi"):
        av.read_record(raw)


@pytest.mark.snapshot
def test_another_filter_is_refused(tmp_path):
    raw = _edited_nc(tmp_path, lambda ds: ds.setncattr("filter_period", "6 months"))
    with pytest.raises(av.AvisoFormatError, match="filter_period"):
        av.read_record(raw)


@pytest.mark.snapshot
def test_a_fill_value_is_refused(tmp_path):
    def blank_one(ds):
        v = ds.variables["msl"]
        v[100] = np.ma.masked

    raw = _edited_nc(tmp_path, blank_one)
    with pytest.raises(av.AvisoFormatError, match="fill values"):
        av.read_record(raw)

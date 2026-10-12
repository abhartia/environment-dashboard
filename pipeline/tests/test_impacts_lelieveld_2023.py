"""Lelieveld et al. 2023: deaths from fossil-fuel air pollution, world, 2019
(envdash/transforms/impacts/lelieveld_2023.py).

Fixtures (each with its .provenance.json sidecar, cut from the snapshots of 2026-10-12): the whole of
mortality_region_2019_ref.xlsx and mortality_region_2019_noFF.xlsx from the Edmond deposit (17 KB each, CC0 1.0), so
the transform runs on the real files.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.impacts import lelieveld_2023 as lv

from support import fixture


def _raw(artifact_id: str) -> bytes:
    path, _ = fixture(lv.SOURCE, artifact_id)
    return path.read_bytes()


def _ref() -> bytes:
    return _raw(lv.REF.artifact_id)


def _no_fossil() -> bytes:
    return _raw(lv.NO_FOSSIL.artifact_id)


def _with_cell(raw: bytes, region: str, column: int, new) -> bytes:
    """The real workbook with one cell changed, to show that a changed file is refused."""
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    rows = [r for r in wb[lv.SHEET].iter_rows() if isinstance(r[0].value, str) and r[0].value.strip() == region]
    assert len(rows) == 1
    rows[0][column].value = new
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_registry_entry_is_the_cc0_deposit_and_twins_the_lancet_estimate():
    reg = load_registry(Paths.default())
    src = reg.sources[lv.SOURCE]
    assert src.licence_class == "open" and src.licence.spdx == "CC0-1.0" and src.obligations.mirror_raw
    # The licence is read from the repository's own dataset record, not from the article (which is CC BY-NC).
    assert src.evidence.terms_check == "api" and "persistentId=doi:10.17617/3.T7XAXH" in str(src.evidence.terms_url)
    assert '"name":"CC0 1.0"' in src.evidence.licence_quote
    assert {a.id: str(a.url) for a in src.artifacts} == {
        lv.REF.artifact_id: "https://edmond.mpg.de/api/access/datafile/236841",
        lv.NO_FOSSIL.artifact_id: "https://edmond.mpg.de/api/access/datafile/236835",
    }
    # Twins both ways: shown side by side, never blended.
    assert src.twins == ["lancet-countdown-2025"]
    assert lv.SOURCE in reg.sources["lancet-countdown-2025"].twins
    # The credit names the deposit and the article it belongs to, as the repository's community norm asks.
    for credit in (src.obligations.attribution, src.obligations.attribution_modified or ""):
        assert "doi:10.17617/3.T7XAXH" in credit and "doi:10.1136/bmj-2023-077784" in credit


def test_spec_is_a_labelled_calculation_with_the_papers_check():
    (t,) = lv.transforms(Paths.default())
    assert t.spec.id == lv.INDICATOR and t.spec.kind == "derived"
    assert t.inputs == (lv.REF, lv.NO_FOSSIL)
    d = t.spec.description
    assert "a harm of the burning itself, not of the warming" in d and "modelled" in d
    assert "Calculated from the authors' deposited model runs" in d and "never combined" in d
    assert "none is calculated here" in d
    (c,) = t.checks
    # "5.13 million" is written with its three significant digits: tolerance half the last printed digit.
    assert (c.stated, c.tolerance, c.period, c.vintage) == ("5.13E6", 5000.0, lv.PERIOD, lv.VINTAGE)
    assert "5.13 million (3.63 to 6.32)" in c.quote and c.url == "https://doi.org/10.1136/bmj-2023-077784"
    assert lv.ABSTRACT_FOSSIL in lv.NOTE and "95% confidence interval" in lv.NOTE


def test_the_difference_of_the_two_runs_is_the_papers_figure():
    ref, without, diff = lv.fossil_deaths(_ref(), _no_fossil())
    assert (ref, without, diff) == (8_341_770, 3_215_143, 5_126_627)
    (o,) = lv.observations(_ref(), _no_fossil())
    assert (o.entity, o.period, o.value, o.status) == ("WLD", "2019", 5_126_627.0, "final")
    # No range is calculated: confidence limits cannot be subtracted. The note quotes the paper's own.
    assert o.lower is None and o.upper is None and o.note == lv.NOTE
    (t,) = lv.transforms(Paths.default())
    outcomes = run_checks(t, {lv.SOURCE: lv.VINTAGE}, [o])
    assert [x.status for x in outcomes] == ["pass"], outcomes


def test_the_column_read_is_the_one_the_paper_reports():
    # The reference total's 95% limits must round to the paper's printed 5.63 and 11.19 million.
    lower = lv.TOTAL_COLUMN + 1
    with pytest.raises(lv.LelieveldFormatError, match="the paper prints"):
        lv.fossil_deaths(_with_cell(_ref(), lv.WORLD, lower, 5_700_000), _no_fossil())


def test_a_changed_or_mismatched_file_is_refused():
    # The two files swapped: each one's cause columns carry its own run's suffix.
    with pytest.raises(lv.LelieveldFormatError, match="header"):
        lv.fossil_deaths(_no_fossil(), _ref())
    # A run with another population is not the same model world.
    with pytest.raises(lv.LelieveldFormatError, match="different population"):
        lv.fossil_deaths(_ref(), _with_cell(_no_fossil(), "South Asia", 1, 1900.0))
    # A missing value is not read as zero.
    with pytest.raises(lv.LelieveldFormatError, match="not a number"):
        lv.fossil_deaths(_ref(), _with_cell(_no_fossil(), lv.WORLD, lv.TOTAL_COLUMN, None))
    # More deaths without fossil fuels than with them is not a difference to publish.
    with pytest.raises(lv.LelieveldFormatError, match="more deaths without fossil fuels"):
        lv.fossil_deaths(_ref(), _with_cell(_no_fossil(), lv.WORLD, lv.TOTAL_COLUMN, 9_000_000))


def test_runs_whole_on_the_recorded_snapshots():
    # The fixtures are the whole files, so their manifests are the real snapshots of 2026-10-12.
    p = Paths.default()
    files = {}
    for i in (lv.REF, lv.NO_FOSSIL):
        path, meta = fixture(lv.SOURCE, i.artifact_id)
        snap = snapshots.read_manifest(p, meta["full_sha256"])
        assert snap is not None and snap.url is not None and str(snap.url) == meta["url"]
        files[i.key] = InputFile(path, snap)
    (t,) = lv.transforms(p)
    r = t.run(files)
    validate(t, r.observations)
    assert r.vintage == lv.VINTAGE and r.changes and len(r.steps) == 2
    assert [o.value for o in r.observations] == [5_126_627.0]

"""Drawdown Explorer: climate impact of solutions by adoption level (envdash/transforms/action/drawdown_explorer.py).

The spreadsheets embed third-party tables (mirror_raw false), so no fixture is committed; the tests read the full
snapshots from the local cache and are marked `snapshot`.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.action import drawdown_explorer as dd


def test_every_table_reads_a_registered_artifact():
    src = load_registry(Paths.default()).sources[dd.SOURCE]
    registered = {a.id for a in src.artifacts}
    assert set(dd.ARTIFACTS) <= registered
    assert len(dd.ARTIFACTS) == 28


def _file(artifact: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[f"{dd.SOURCE}/{artifact}"]
    return InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))


def _rows(t: dd.Table) -> list[tuple]:
    return dd.sheet_rows(_file(t.artifact).path.read_bytes(), t.sheet)


def _table(artifact: str, basis: str | None = None) -> dd.Table:
    return next(t for t in dd.TABLES if t.artifact == artifact and (basis is None or t.rows[0][1] == basis))


@pytest.mark.snapshot
def test_all_declared_tables_from_the_real_spreadsheets():
    (t,) = dd.transforms(Paths.default())
    result = t.run({i.key: _file(i.artifact_id) for i in t.inputs})
    validate(t, result.observations)
    obs = {(o.dims["solution"], o.dims["level"], o.dims["basis"]): o for o in result.observations}
    assert len(obs) == 136
    assert obs[("deploy-onshore-wind-turbines", "current", "gwp100")].value == 1.6
    assert obs[("use-heat-pumps", "achievable-high", "gwp100")].value == 0.93
    assert obs[("protect-forests", "ceiling", "gwp20")].value == 4.096562477
    assert ("protect-forests", "ceiling", "gwp100") not in obs
    assert obs[("mobilize-electric-cars", "achievable-low", "gwp100")].value == 1.2625887428628486
    assert obs[("improve-diets", "current", "gwp100")].value is None
    assert obs[("reduce-food-loss-and-waste", "current", "gwp100")].missing_reason == (
        "The spreadsheet's cell for this level reads 'Not determined', not a number."
    )


@pytest.mark.snapshot
def test_a_title_that_differs_is_refused():
    t = _table("use-heat-pumps")
    with pytest.raises(dd.DrawdownFormatError, match="title"):
        dd.read_table(_rows(t), replace(t, title=t.title.replace("100-year", "20-year")))


@pytest.mark.snapshot
def test_the_wrong_row_is_refused():
    t = _table("use-heat-pumps")
    with pytest.raises(dd.DrawdownFormatError):
        dd.read_table(_rows(t), replace(t, title_cell=(t.title_cell[0] + 1, 5)))


@pytest.mark.snapshot
def test_text_where_a_number_should_be_is_refused():
    t = _table("improve-diets")
    with pytest.raises(dd.DrawdownFormatError, match="not a number"):
        dd.read_table(_rows(t), replace(t, not_given=()))


@pytest.mark.snapshot
def test_a_mislabelled_basis_row_is_refused():
    t = _table("increase-carpooling")
    swapped = ((65, "gwp100", "100-year basis"), (66, "gwp20", "20-year basis"))
    with pytest.raises(dd.DrawdownFormatError, match="label"):
        dd.read_table(_rows(t), replace(t, rows=swapped))

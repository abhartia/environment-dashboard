"""Andre et al. (2024): actual and perceived support for climate action, Table S4 of the Supplementary Information
(envdash/transforms/action/andre_2024.py).

Fixture: the whole Supplementary Information PDF (CC BY 4.0), cut with tests/fixtures/make_fixture.py.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover, run_checks, validate
from envdash.transforms.action import andre_2024 as an
from envdash.validate import validate_all

FIXTURES = Path(__file__).parent / "fixtures" / an.SOURCE


def _fixture() -> tuple[Path, dict]:
    for side in sorted(FIXTURES.glob("*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == an.SI.artifact_id:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(an.SI.artifact_id)


@pytest.fixture(scope="module")
def rows() -> list[tuple[str, list[str]]]:
    return an.read_table(_fixture()[0].read_bytes())


def _value(obs, entity, measure):
    (o,) = [o for o in obs if o.entity == entity and o.dims["measure"] == measure]
    return o


def test_table_s4_has_125_countries_and_world(rows):
    assert len(rows) == 126 and rows[-1] == ("World", ["68.5", "86.2", "88.6", "42.8", "29.9"])
    assert rows[0] == ("Myanmar", ["92.8", "95.4", "–", "60.2", "52.2"])
    assert {n for n, _ in rows} == set(an.NAMES)


def test_values_and_dashes(rows):
    obs = an.observations(rows)
    assert len(obs) == 5 * 126
    assert _value(obs, "USA", "willing-to-contribute").value == 48.1
    assert _value(obs, "USA", "perceived-willing-others").value == 33.2
    assert _value(obs, "TGO", "willing-to-contribute").value == 79.9
    dashes = [o for o in obs if o.value is None]
    assert {(o.entity, o.dims["measure"]) for o in dashes} == {
        ("MMR", "demand-political-action"),
        ("ARE", "demand-political-action"),
        ("SAU", "demand-political-action"),
    }
    assert all(o.missing_reason for o in dashes)


def test_world_matches_the_abstract(rows):
    (t,) = an.transforms(Paths.default())
    obs = an.observations(rows)
    validate(t, obs)
    outcomes = run_checks(t, {an.SOURCE: an.VINTAGE}, obs)
    assert [c.status for c in outcomes] == ["pass", "pass", "pass"]


def test_an_unlisted_name_is_refused(monkeypatch):
    names = dict(an.NAMES)
    del names["T ogo"]
    monkeypatch.setattr(an, "NAMES", names)
    with pytest.raises(an.AndreFormatError, match="T ogo"):
        an.read_table(_fixture()[0].read_bytes())


def test_a_missing_page_is_refused(monkeypatch):
    monkeypatch.setattr(an, "PAGES", (6, 7))
    with pytest.raises(an.AndreFormatError, match="expected 125 and World"):
        an.read_table(_fixture()[0].read_bytes())


def test_build_exports_publicly(tmp_path):
    (tmp_path / "literature").mkdir()
    (tmp_path / "sources").mkdir()
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{an.SOURCE}.yaml", tmp_path / "sources")
    paths = Paths.default().with_(
        sources=tmp_path / "sources",
        literature=tmp_path / "literature",
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )
    path, meta = _fixture()
    snap, _ = snapshots.record(
        paths,
        data=path.read_bytes(),
        source_id=an.SOURCE,
        artifact_id=an.SI.artifact_id,
        url=meta["url"],
        acquisition="automatic",
        today=date.fromisoformat(meta["date_accessed"]),
        note="test fixture: the whole Supplementary Information",
    )
    snapshots.set_current(paths, {an.SI.key: snap.sha256})
    reg = load_registry(paths)
    report = build_and_export(paths, reg, [t for t in discover(paths) if t.spec.id == an.INDICATOR])
    assert [o.state for o in report.outcomes] == ["built"], [o.reason for o in report.outcomes]
    assert [c.status for c in report.outcomes[0].checks] == ["pass", "pass", "pass"]
    assert validate_all(paths, reg) == []

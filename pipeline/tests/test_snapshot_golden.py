"""Full-snapshot tests (-m snapshot): need pipeline/.snapshots populated by envdash fetch (or restored from R2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.literature import QuoteNotFound, verify_quote

pytestmark = pytest.mark.snapshot


def _files(root: Path, skip: set[str]) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).as_posix() not in skip
    }


def test_golden_rebuild_is_byte_identical(tmp_path):
    repo = Paths.default()
    paths = repo.with_(data=tmp_path / "data", private=tmp_path / "data-private", manifests=tmp_path / "manifests")
    # Same snapshot manifests and pointers as the committed build; build records go to the temporary directory.
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "snapshots").symlink_to(repo.snapshot_manifests)
    (tmp_path / "manifests" / "current.json").write_bytes(repo.current.read_bytes())
    reg = load_registry(paths)
    report = build_and_export(paths, reg, discover(paths), force=True)
    assert report.ok, [(o.id, o.reason) for o in report.failed]
    assert _files(paths.data, {"v1/status.json"}) == _files(repo.data, {"v1/status.json"})
    assert _files(paths.private, set()) == _files(repo.private, set())


def _current_bytes(source_id: str, artifact_id: str) -> bytes:
    p = Paths.default()
    return snapshots.cache_path(p, snapshots.read_current(p)[f"{source_id}/{artifact_id}"]).read_bytes()


def test_ipcc_quote_is_in_the_real_pdf_and_a_changed_one_is_not():
    lit = load_registry(Paths.default()).literature["ipcc-ar6-wg3-spm-c12"]
    pdf = _current_bytes(lit.source_id, lit.artifact_id)
    verify_quote(pdf, lit.pdf_page, lit.quote)
    with pytest.raises(QuoteNotFound):
        verify_quote(pdf, lit.pdf_page, lit.quote.replace("at least half", "at least two thirds"))
    with pytest.raises(QuoteNotFound):
        verify_quote(pdf, lit.pdf_page + 1, lit.quote)


def test_hadcrut_full_file_regression():
    from envdash.transforms.temperature.hadcrut5 import rebase

    obs, offset, excluded, _ = rebase(
        _current_bytes("hadcrut5", "global-annual"), _current_bytes("hadcrut5", "global-monthly")
    )
    by = {o.period: o.value for o in obs}
    assert round(float(offset), 6) == -0.359436
    assert round(by["2024"], 3) == 1.547 and round(by["2025"], 3) == 1.433
    assert excluded == 2026 and obs[0].period == "1850" and len(obs) == 176

"""Test helpers. Fixtures are byte-exact slices of real snapshots (see tests/fixtures/make_fixture.py)."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from envdash import canonical, snapshots
from envdash.build import load_export
from envdash.paths import REPO_ROOT, Paths

FIXTURES = Path(__file__).parent / "fixtures"
SLICE_SOURCES = ("noaa-gml-trends", "hadcrut5", "ipcc-ar6-wg3-spm")


def fixture(source_id: str, artifact_id: str) -> tuple[Path, dict]:
    """The fixture file cut from (source, artifact) and its provenance sidecar."""
    for side in sorted(FIXTURES.glob(f"{source_id}/*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == artifact_id:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(f"no fixture for {source_id}/{artifact_id}")


def exported(path: Path) -> dict:
    """An exported indicator file (an IndicatorFile, observations as columns) expanded to the Indicator it was written
    from, as plain JSON (observations as records)."""
    return canonical.to_plain(load_export(path))


def make_tmp_paths(tmp_path: Path) -> Paths:
    """Real registry, transforms and uv.lock; snapshot store and outputs in a temporary directory."""
    lit = tmp_path / "literature"
    lit.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()
    for sid in SLICE_SOURCES:  # only this slice's entries, so other registry work in progress cannot break tests
        shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{sid}.yaml", sources / f"{sid}.yaml")
    return Paths.default().with_(
        sources=sources,
        literature=lit,
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )


def load_fixture_snapshot(paths: Paths, source_id: str, artifact_id: str) -> str:
    """Record a fixture as the current snapshot of (source, artifact) in a temporary store, keeping its real URL and
    access date. Returns its sha256 (of the fixture bytes, which differ from the full file's)."""
    path, meta = fixture(source_id, artifact_id)
    snap, _ = snapshots.record(
        paths,
        data=path.read_bytes(),
        source_id=source_id,
        artifact_id=artifact_id,
        url=meta["url"],
        acquisition="automatic",
        today=date.fromisoformat(meta["date_accessed"]),
        note=f"test fixture: {meta['rows_kept']} of {meta['full_sha256']}",
    )
    snapshots.set_current(paths, {snapshots.key(source_id, artifact_id): snap.sha256})
    return snap.sha256


def copy_sources(paths: Paths, tmp_path: Path, *ids: str) -> Paths:
    """A sources directory holding copies of some real registry entries (to edit in a test)."""
    d = tmp_path / "sources-edited"
    d.mkdir(exist_ok=True)
    for i in ids:
        shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{i}.yaml", d / f"{i}.yaml")
    return paths.with_(sources=d)

"""`envdash snapshots pull`: which snapshots are wanted, which are pulled, and the checks on what comes back.

Real fixture bytes throughout (noaa-gml-trends slices); R2 is replaced by an in-memory bucket that serves those bytes
compressed exactly as `envdash archive` stores them.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from envdash import archive, snapshot_pull, snapshots
from envdash.export import build_and_export
from envdash.registry import load_registry
from envdash.transform import discover

from support import fixture, load_fixture_snapshot

ANNUAL = "co2.noaa-gml.annual-global"


class Bucket:
    """Holds objects by (bucket, key) and answers get_object like the S3 client does."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def get_object(self, Bucket: str, Key: str) -> dict:
        import io

        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


def _built(tmp_paths) -> str:
    """Build the annual CO2 indicator from its fixture; returns the fixture snapshot's sha256."""
    sha = load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    reg = load_registry(tmp_paths)
    assert build_and_export(tmp_paths, reg, [t for t in discover(tmp_paths) if t.spec.id == ANNUAL]).ok
    return sha


def _archive(tmp_paths, sha: str, bucket: Bucket) -> None:
    raw = snapshots.cache_path(tmp_paths, sha).read_bytes()
    key = archive.r2_key(sha)
    bucket.objects[(archive.PUBLIC_BUCKET, key)] = archive.compress(raw)
    snapshots.update_manifest(tmp_paths, sha, r2_bucket=archive.PUBLIC_BUCKET, r2_key=key)


def test_wanted_lists_current_pointers_and_indicator_inputs(tmp_paths):
    sha = _built(tmp_paths)
    # A second current pointer that no indicator reads is wanted too.
    other = load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-mm-mlo")
    want = snapshot_pull.wanted(tmp_paths)
    assert want[sha] == [
        "current noaa-gml-trends/co2-annmean-gl",
        f"input of {ANNUAL} (noaa-gml-trends/co2-annmean-gl)",
    ]
    assert want[other] == ["current noaa-gml-trends/co2-mm-mlo"]
    assert list(want) == sorted(want)


def test_wanted_includes_inputs_no_longer_current(tmp_paths):
    sha = _built(tmp_paths)
    snapshots.set_current(
        tmp_paths, {"noaa-gml-trends/co2-annmean-gl": load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-mm-mlo")}
    )
    want = snapshot_pull.wanted(tmp_paths)
    assert want[sha] == [f"input of {ANNUAL} (noaa-gml-trends/co2-annmean-gl)"]


def test_wanted_needs_the_catalogue(tmp_paths):
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    with pytest.raises(snapshot_pull.PullError, match=r"catalog\.json is missing"):
        snapshot_pull.wanted(tmp_paths)


def test_plan_keeps_verified_files_and_refuses_unarchived_ones(tmp_paths):
    sha = _built(tmp_paths)
    assert snapshot_pull.plan(tmp_paths).present == [sha]

    cached = snapshots.cache_path(tmp_paths, sha)
    cached.unlink()
    p = snapshot_pull.plan(tmp_paths)
    assert p.present == [] and p.download == []
    (problem,) = p.problems
    assert problem.startswith(f"{sha} (noaa-gml-trends/co2-annmean-gl): never archived to R2")

    bucket = Bucket()
    snapshots.store_bytes(tmp_paths, fixture("noaa-gml-trends", "co2-annmean-gl")[0].read_bytes())
    _archive(tmp_paths, sha, bucket)
    cached.write_bytes(fixture("noaa-gml-trends", "co2-mm-mlo")[0].read_bytes())  # a corrupt local copy
    p = snapshot_pull.plan(tmp_paths)
    assert [s.sha256 for s in p.download] == [sha] and p.problems == []


def test_plan_reports_a_missing_manifest(tmp_paths):
    sha = _built(tmp_paths)
    snapshots.cache_path(tmp_paths, sha).unlink()
    snapshots.manifest_path(tmp_paths, sha).unlink()
    (problem,) = snapshot_pull.plan(tmp_paths).problems
    assert "no manifest" in problem and "current noaa-gml-trends/co2-annmean-gl" in problem


def test_pull_downloads_and_verifies(tmp_paths):
    sha = _built(tmp_paths)
    bucket = Bucket()
    _archive(tmp_paths, sha, bucket)
    good = snapshots.cache_path(tmp_paths, sha).read_bytes()
    snapshots.cache_path(tmp_paths, sha).unlink()
    todo = snapshot_pull.plan(tmp_paths).download
    assert snapshot_pull.pull(tmp_paths, bucket, todo) == [sha]
    assert snapshots.cache_path(tmp_paths, sha).read_bytes() == good
    assert snapshot_pull.plan(tmp_paths).present == [sha]


def test_pull_refuses_bytes_that_do_not_match_the_manifest(tmp_paths):
    sha = _built(tmp_paths)
    bucket = Bucket()
    _archive(tmp_paths, sha, bucket)
    snapshots.cache_path(tmp_paths, sha).unlink()
    other = fixture("noaa-gml-trends", "co2-mm-mlo")[0].read_bytes()
    bucket.objects[(archive.PUBLIC_BUCKET, archive.r2_key(sha))] = archive.compress(other)
    with pytest.raises(snapshot_pull.PullError, match="not the"):
        snapshot_pull.pull(tmp_paths, bucket, snapshot_pull.plan(tmp_paths).download)
    assert not snapshots.cache_path(tmp_paths, sha).exists()
    bucket.objects[(archive.PUBLIC_BUCKET, archive.r2_key(sha))] = other  # not compressed at all
    with pytest.raises(snapshot_pull.PullError, match="not a zstd frame"):
        snapshot_pull.pull(tmp_paths, bucket, snapshot_pull.plan(tmp_paths).download)


def test_cli_fails_explicitly_without_r2_credentials(tmp_paths, monkeypatch):
    from envdash import cli

    sha = _built(tmp_paths)
    _archive(tmp_paths, sha, Bucket())
    snapshots.cache_path(tmp_paths, sha).unlink()
    monkeypatch.setattr(cli, "_paths", lambda: tmp_paths)
    for name in archive.R2_ENV:
        monkeypatch.delenv(name, raising=False)
    result = CliRunner().invoke(cli.app, ["snapshots", "pull"])
    assert result.exit_code == 1
    assert "R2 is not configured: set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, CLOUDFLARE_ACCOUNT_ID" in result.output


def test_cli_with_everything_cached_needs_no_credentials(tmp_paths, monkeypatch):
    from envdash import cli

    _built(tmp_paths)
    monkeypatch.setattr(cli, "_paths", lambda: tmp_paths)
    for name in archive.R2_ENV:
        monkeypatch.delenv(name, raising=False)
    result = CliRunner().invoke(cli.app, ["snapshots", "pull"])
    assert result.exit_code == 0, result.output
    assert "all 1 snapshot(s) already cached and verified" in result.output
    assert json.loads(tmp_paths.current.read_text())  # nothing about the pointers changed

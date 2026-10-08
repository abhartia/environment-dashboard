"""The snapshot store: raw bytes by sha256 in a local cache, one manifest per sha256, and the current pointers.

- Bytes: pipeline/.snapshots/<sha256> (gitignored; the durable copy is R2, see archive.py).
- Manifest: pipeline/manifests/snapshots/<sha256>.json (models.Snapshot), written once. `date_accessed` is the day
  those bytes were first fetched and never changes; only the archive fields (r2_*, wayback) are filled in later. For
  a discovered artifact the manifest's url is the resolved URL and `discovery` names the listing it was found on; for
  an artifact with a content_key, `content_sha256` is the content fingerprint next to the raw sha256; for an
  artifact with a zip_member, the bytes are that member's and `zip_member` names it inside the zip at `url`.
- Pointers: pipeline/manifests/current.json maps "<source>/<artifact>" to the sha256 the build reads. A source's
  pointers move together, and only when every artifact of that source fetched cleanly.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from envdash import canonical
from envdash.models import Snapshot, SnapshotDiscovery
from envdash.paths import Paths


def key(source_id: str, artifact_id: str) -> str:
    return f"{source_id}/{artifact_id}"


def cache_path(paths: Paths, sha: str) -> Path:
    return paths.cache / sha


def manifest_path(paths: Paths, sha: str) -> Path:
    return paths.snapshot_manifests / f"{sha}.json"


def read_manifest(paths: Paths, sha: str) -> Snapshot | None:
    p = manifest_path(paths, sha)
    if not p.exists():
        return None
    return Snapshot.model_validate_json(p.read_bytes())


def write_manifest(paths: Paths, snap: Snapshot) -> None:
    canonical.write_if_changed(manifest_path(paths, snap.sha256), canonical.dump_bytes(snap))


def all_manifests(paths: Paths) -> list[Snapshot]:
    if not paths.snapshot_manifests.exists():
        return []
    return [Snapshot.model_validate_json(p.read_bytes()) for p in sorted(paths.snapshot_manifests.glob("*.json"))]


def store_bytes(paths: Paths, data: bytes) -> str:
    sha = canonical.sha256_bytes(data)
    dest = cache_path(paths, sha)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(sha + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
    return sha


def record(
    paths: Paths,
    *,
    data: bytes,
    source_id: str,
    artifact_id: str,
    url: str | None,
    acquisition: str,
    today: date,
    etag: str | None = None,
    last_modified: str | None = None,
    content_type: str | None = None,
    note: str | None = None,
    discovery: SnapshotDiscovery | None = None,
    content_key: str | None = None,
    content_sha256: str | None = None,
    zip_member: str | None = None,
) -> tuple[Snapshot, bool]:
    """Cache the bytes and write their manifest if this sha256 is new. Returns (manifest, is_new)."""
    sha = store_bytes(paths, data)
    existing = read_manifest(paths, sha)
    if existing is not None:
        return existing, False
    snap = Snapshot(
        sha256=sha,
        bytes=len(data),
        source_id=source_id,
        artifact_id=artifact_id,
        url=url,
        date_accessed=today,
        acquisition=acquisition,
        etag=etag,
        last_modified=last_modified,
        content_type=content_type,
        r2_bucket=None,
        r2_key=None,
        compression="zstd",
        wayback=None,
        note=note,
        discovery=discovery,
        content_key=content_key,
        content_sha256=content_sha256,
        zip_member=zip_member,
    )
    write_manifest(paths, snap)
    return snap, True


def read_current(paths: Paths) -> dict[str, str]:
    if not paths.current.exists():
        return {}
    return dict(json.loads(paths.current.read_text(encoding="utf-8")))


def set_current(paths: Paths, updates: dict[str, str]) -> None:
    cur = read_current(paths)
    cur.update(updates)
    canonical.write_if_changed(paths.current, canonical.dump_bytes(cur))


def update_manifest(paths: Paths, sha: str, **changes: object) -> Snapshot:
    """Fill archive fields on an existing manifest. Identity fields (bytes, url, date_accessed) cannot change."""
    allowed = {"r2_bucket", "r2_key", "wayback"}
    if set(changes) - allowed:
        raise ValueError(f"only {sorted(allowed)} may change on a snapshot manifest")
    snap = read_manifest(paths, sha)
    if snap is None:
        raise FileNotFoundError(f"no manifest for {sha}")
    new = snap.model_copy(update=changes)
    Snapshot.model_validate(new.model_dump())  # re-validate after model_copy
    write_manifest(paths, new)
    return new

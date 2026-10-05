"""`envdash snapshots pull`: fill the local raw-snapshot cache (pipeline/.snapshots) from R2 on a fresh machine.

Which snapshots: every sha256 that pipeline/manifests/current.json points at (what the next build reads) and every
input of every published indicator (the origins listed in data/v1/catalog.json, for every licence class), so that
both a rebuild and the snapshot tests (-m snapshot) have their bytes. Each needs its manifest
(pipeline/manifests/snapshots/<sha256>.json) with the R2 location `envdash archive` recorded (r2_bucket, r2_key).

What happens to each:
- already in the cache and hashing to its name: kept;
- in R2: downloaded, zstd-decompressed, and written only if the bytes hash to the sha256 and have the manifest's size;
- no manifest, or never archived to R2: a problem, named with the reason it was wanted. The pull fails rather than
  skip it, because a build or test would otherwise fail later with a less useful message.

Credentials come from the environment as for `envdash archive` (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
CLOUDFLARE_ACCOUNT_ID); they are needed only when something must be downloaded, and their absence then stops the
pull and names them.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import zstandard

from envdash import canonical, snapshots
from envdash.models import Catalog, Snapshot
from envdash.paths import Paths


class PullError(RuntimeError):
    pass


def wanted(paths: Paths) -> dict[str, list[str]]:
    """sha256 -> why it is wanted ("current <source>/<artifact>", "input of <indicator id>"), sorted by sha256."""
    why: dict[str, list[str]] = {}
    for k, sha in sorted(snapshots.read_current(paths).items()):
        why.setdefault(sha, []).append(f"current {k}")
    catalog_path = paths.data / "v1" / "catalog.json"
    if not catalog_path.exists():
        raise PullError(f"{paths.rel(catalog_path)} is missing: the published indicators' inputs cannot be listed")
    catalog = Catalog.model_validate_json(catalog_path.read_bytes())
    for e in catalog.indicators:
        for o in e.provenance.origins:
            why.setdefault(o.sha256, []).append(f"input of {e.id} ({o.source_id}/{o.artifact_id})")
    return {sha: why[sha] for sha in sorted(why)}


@dataclass
class Plan:
    present: list[str] = field(default_factory=list)
    """Cached already, bytes verified."""
    download: list[Snapshot] = field(default_factory=list)
    """Archived in R2 and missing (or corrupt) locally."""
    problems: list[str] = field(default_factory=list)
    """Wanted but impossible to pull: no manifest, or never archived to R2."""


def plan(paths: Paths) -> Plan:
    out = Plan()
    for sha, reasons in wanted(paths).items():
        cached = snapshots.cache_path(paths, sha)
        if cached.exists() and canonical.sha256_file(cached) == sha:
            out.present.append(sha)
            continue
        snap = snapshots.read_manifest(paths, sha)
        because = "; ".join(reasons)
        if snap is None:
            out.problems.append(f"{sha}: no manifest {paths.rel(snapshots.manifest_path(paths, sha))} ({because})")
        elif snap.r2_bucket is None or snap.r2_key is None:
            out.problems.append(
                f"{sha} ({snap.source_id}/{snap.artifact_id}): never archived to R2; run envdash archive where the "
                f"bytes are, then commit the manifest ({because})"
            )
        else:
            out.download.append(snap)
    return out


def decode(snap: Snapshot, body: bytes) -> bytes:
    """The raw bytes of an R2 object: zstd-decompressed, and checked against the manifest's sha256 and size."""
    if snap.compression != "zstd":
        raise PullError(f"{snap.sha256}: compression {snap.compression!r} is not zstd")
    try:
        raw = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(body)).read()
    except zstandard.ZstdError as e:
        raise PullError(f"{snap.sha256}: {snap.r2_bucket}/{snap.r2_key} is not a zstd frame: {e}") from None
    got = canonical.sha256_bytes(raw)
    if got != snap.sha256 or len(raw) != snap.bytes:
        raise PullError(
            f"{snap.r2_bucket}/{snap.r2_key} decompresses to {len(raw):,} bytes with sha256 {got}, not the "
            f"{snap.bytes:,} bytes with sha256 {snap.sha256} its manifest records"
        )
    return raw


def write_verified(paths: Paths, snap: Snapshot, raw: bytes) -> None:
    """Write bytes already checked by decode(), replacing a corrupt cached copy if there is one."""
    dest = snapshots.cache_path(paths, snap.sha256)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(snap.sha256 + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(dest)


def pull(paths: Paths, client, todo: list[Snapshot]) -> list[str]:
    """Download, verify and cache each snapshot in `todo`; the first bad object stops the pull."""
    done: list[str] = []
    for snap in todo:
        body = client.get_object(Bucket=snap.r2_bucket, Key=snap.r2_key)["Body"].read()
        write_verified(paths, snap, decode(snap, body))
        done.append(snap.sha256)
    return done

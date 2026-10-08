"""Archiving: raw snapshots to Cloudflare R2, and best-effort Wayback Machine captures.

Run explicitly with `envdash archive`; fetching never archives as a side effect.

R2. Each snapshot is zstd-compressed and stored at raw/<sha256>.zst (the hash is of the raw bytes, not the
compressed object). It goes to envdash-public only when the source's terms allow a public mirror
(obligations.mirror_raw) and its class is redistributable; everything else goes to envdash-private. The manifest's
r2_bucket/r2_key are filled in afterwards. Credentials come from the environment (R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, CLOUDFLARE_ACCOUNT_ID); when any is missing the command stops and names them.

Wayback (SPN2). Landing and terms pages of every source are always submitted; data files only for mirror_raw sources
and under 50 MB. A response without a job_id is a failure. Nothing here ever raises into the build: each outcome is
recorded (captured, pending, refused or skipped) with its reason.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
import zstandard

from envdash import canonical, snapshots
from envdash.fetch import USER_AGENT
from envdash.models import REDISTRIBUTABLE, Snapshot, Source, WaybackCapture
from envdash.paths import Paths

PUBLIC_BUCKET = "envdash-public"
PRIVATE_BUCKET = "envdash-private"
R2_ENV = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID")
IA_ENV = ("IA_ACCESS", "IA_SECRET")
WAYBACK_DATA_LIMIT = 50_000_000
SPN2_URL = "https://web.archive.org/save"
SPN2_STATUS = "https://web.archive.org/save/status/{job_id}"


class ArchiveConfigError(RuntimeError):
    pass


def bucket_for(source: Source) -> str:
    if source.obligations.mirror_raw and source.licence_class in REDISTRIBUTABLE:
        return PUBLIC_BUCKET
    return PRIVATE_BUCKET


def r2_key(sha256: str) -> str:
    return f"raw/{sha256}.zst"


def missing_env(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


def r2_client():  # pragma: no cover - needs credentials
    missing = missing_env(R2_ENV)
    if missing:
        raise ArchiveConfigError(
            "R2 is not configured: set " + ", ".join(missing) + " (see docs/runbook.md for the Keychain service names)"
        )
    import boto3

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def compress(data: bytes) -> bytes:
    return zstandard.ZstdCompressor(level=19, write_checksum=True).compress(data)


def upload_snapshot(paths: Paths, client, snap: Snapshot, source: Source) -> Snapshot:  # pragma: no cover - network
    bucket, key = bucket_for(source), r2_key(snap.sha256)
    if snap.r2_bucket == bucket and snap.r2_key == key:
        return snap
    raw = snapshots.cache_path(paths, snap.sha256).read_bytes()
    if canonical.sha256_bytes(raw) != snap.sha256:
        raise RuntimeError(f"cached bytes for {snap.sha256} do not match their hash")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=compress(raw),
        ContentType="application/zstd",
        Metadata={"sha256": snap.sha256, "source-id": snap.source_id, "artifact-id": snap.artifact_id},
    )
    return snapshots.update_manifest(paths, snap.sha256, r2_bucket=bucket, r2_key=key)


# --- Wayback --------------------------------------------------------------------------------------------------


@dataclass
class WaybackTarget:
    url: str
    kind: str  # landing | terms | data
    sha256: str | None = None


def wayback_targets(paths: Paths, sources: dict[str, Source]) -> list[WaybackTarget]:
    targets: list[WaybackTarget] = []
    for src in sources.values():
        targets.append(WaybackTarget(str(src.landing_url), "landing"))
        targets.append(WaybackTarget(str(src.evidence.terms_url), "terms"))
    for sha in sorted(set(snapshots.read_current(paths).values())):
        snap = snapshots.read_manifest(paths, sha)
        if snap is None or snap.url is None or snap.source_id not in sources:
            continue
        src = sources[snap.source_id]
        # A zip-member snapshot's url is the whole zip (gigabytes), not the bytes recorded: no data capture.
        if src.obligations.mirror_raw and snap.bytes < WAYBACK_DATA_LIMIT and snap.zip_member is None:
            targets.append(WaybackTarget(str(snap.url), "data", sha))
    seen: set[str] = set()
    return [t for t in targets if not (t.url in seen or seen.add(t.url))]


def spn2_capture(client: httpx.Client, url: str, *, polls: int = 6, wait: float = 10.0) -> WaybackCapture:
    """Submit one URL to Save Page Now 2. Never raises."""
    missing = missing_env(IA_ENV)
    if missing:
        return WaybackCapture(status="skipped", reason=f"{', '.join(missing)} not set")
    auth = {"Authorization": f"LOW {os.environ['IA_ACCESS']}:{os.environ['IA_SECRET']}", "Accept": "application/json"}
    try:
        r = client.post(SPN2_URL, data={"url": url, "skip_first_archive": "1"}, headers=auth)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        job_id = body.get("job_id") if isinstance(body, dict) else None
        if not job_id:
            msg = body.get("message") if isinstance(body, dict) else None
            return WaybackCapture(status="refused", reason=f"HTTP {r.status_code}, no job_id: {msg or r.text[:200]}")
        for _ in range(polls):
            time.sleep(wait)
            s = client.get(SPN2_STATUS.format(job_id=job_id), headers=auth).json()
            if s.get("status") == "success":
                ts, original = s.get("timestamp"), s.get("original_url") or url
                return WaybackCapture(
                    status="captured", url=f"https://web.archive.org/web/{ts}/{original}", captured_at=ts
                )
            if s.get("status") == "error":
                return WaybackCapture(status="refused", reason=str(s.get("message") or s.get("status_ext")))
        return WaybackCapture(status="pending", reason=f"job {job_id} still running after {polls} polls")
    except Exception as e:  # best effort: never raise into the build
        return WaybackCapture(status="refused", reason=f"{type(e).__name__}: {e}")


def wayback_all(paths: Paths, sources: dict[str, Source]) -> dict[str, WaybackCapture]:  # pragma: no cover
    out: dict[str, WaybackCapture] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for t in wayback_targets(paths, sources):
            cap = spn2_capture(client, t.url)
            out[t.url] = cap
            if t.sha256 and cap.status == "captured":
                snapshots.update_manifest(paths, t.sha256, wayback=cap)
    record = paths.wayback / "pages.json"
    pages: dict[str, WaybackCapture] = {}
    if record.exists():
        import json

        pages = {u: WaybackCapture.model_validate(c) for u, c in json.loads(record.read_text()).items()}
    for u, c in out.items():
        if c.status == "captured" or pages.get(u) is None or pages[u].status != "captured":
            pages[u] = c  # a later failure never erases an earlier capture
    canonical.write_if_changed(
        record,
        canonical.dump_bytes({u: c.model_dump(mode="json") for u, c in sorted(pages.items())}),
    )
    return out

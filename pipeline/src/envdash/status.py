"""data/v1/status.json: how each source fared in the latest run. Written every run, pass or fail.

A source's entry is replaced when this run checked it and kept as it was otherwise. `last_success` is the last time
it ended ok, unchanged or manual. A build failure (a transform or validation failing on the source's files) turns an
ok or unchanged fetch into failed, with the reason.
"""

from __future__ import annotations

import os
from datetime import date

from pydantic import ValidationError

from envdash import canonical, snapshots
from envdash.export import BuildReport
from envdash.fetch import SourceFetch, now_iso
from envdash.models import SourceRunStatus, Status
from envdash.paths import Paths
from envdash.registry import Registry


def run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def read_status(paths: Paths) -> Status | None:
    if not paths.status_file.exists():
        return None
    try:
        return Status.model_validate_json(paths.status_file.read_bytes())
    except ValidationError:
        return None  # an unreadable heartbeat is replaced, not trusted


def _manual_last_verified(paths: Paths, source_id: str) -> date | None:
    cur = snapshots.read_current(paths)
    dates = [
        m.date_accessed
        for k, sha in cur.items()
        if k.startswith(source_id + "/") and (m := snapshots.read_manifest(paths, sha)) is not None
    ]
    return max(dates) if dates else None


def _literature_source(paths: Paths, literature_id: str) -> str | None:
    """The source a broken literature file names, if it names one, so the failure is reported against it."""
    import yaml

    try:
        raw = yaml.load(
            (paths.literature / f"{literature_id}.yaml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
    except (OSError, yaml.YAMLError):
        return None
    sid = raw.get("source_id") if isinstance(raw, dict) else None
    return sid if isinstance(sid, str) else None


def update_status(
    paths: Paths,
    registry: Registry,
    *,
    fetched: dict[str, SourceFetch] | None = None,
    built: BuildReport | None = None,
    extra_failures: dict[str, str] | None = None,
) -> Status:
    prev = read_status(paths)
    entries: dict[str, SourceRunStatus] = dict(prev.sources) if prev else {}
    now = now_iso()
    vintages: dict[str, str] = {}
    build_fail: dict[str, list[str]] = {}
    if built:
        for o in built.outcomes:
            if o.indicator is not None:
                for sid in o.source_ids:
                    vintages[sid] = o.indicator.vintage
            if o.state == "failed":
                for sid in o.source_ids:
                    build_fail.setdefault(sid, []).append(f"{o.id}: {o.reason}")
        for lid, err in built.literature_errors.items():
            sid = _literature_source(paths, lid)
            if sid is not None:
                build_fail.setdefault(sid, []).append(err)
    for sid, f in (fetched or {}).items():
        prev_e = entries.get(sid)
        state = f.state
        reason = f.reason
        if sid in build_fail and state in {"ok", "unchanged", "manual"}:
            state, reason = "failed", "; ".join(build_fail.pop(sid))
        success = state in {"ok", "unchanged", "manual"}
        entries[sid] = SourceRunStatus(
            state=state,
            checked_at=f.checked_at,
            reason=reason,
            last_success=f.checked_at if success else (prev_e.last_success if prev_e else None),
            vintage=vintages.get(sid, prev_e.vintage if prev_e else None),
            manual_last_verified=_manual_last_verified(paths, sid) if state == "manual" else None,
            terms=f.terms,
        )
    for sid, reasons in build_fail.items():  # build-only run, or a source not fetched this run
        prev_e = entries.get(sid)
        entries[sid] = SourceRunStatus(
            state="failed",
            checked_at=now,
            reason="; ".join(reasons),
            last_success=prev_e.last_success if prev_e else None,
            vintage=prev_e.vintage if prev_e else None,
            manual_last_verified=prev_e.manual_last_verified if prev_e else None,
            terms=prev_e.terms if prev_e else None,
        )
    if built:
        for sid, v in vintages.items():
            if sid in entries and sid not in build_fail and entries[sid].vintage != v:
                entries[sid] = entries[sid].model_copy(update={"vintage": v})
    for sid, reason in (extra_failures or {}).items():
        if sid in registry.sources or sid in registry.source_errors:
            prev_e = entries.get(sid)
            entries[sid] = SourceRunStatus(
                state="failed",
                checked_at=now,
                reason=reason,
                last_success=prev_e.last_success if prev_e else None,
                vintage=prev_e.vintage if prev_e else None,
                manual_last_verified=None,
                terms=prev_e.terms if prev_e else None,
            )
    status = Status(generated_at=now, run_url=run_url(), sources=dict(sorted(entries.items())))
    canonical.write_if_changed(paths.status_file, canonical.dump_bytes(status))
    return status

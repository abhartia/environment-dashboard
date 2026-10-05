"""Run every transform whose inputs changed, validate the result and export it.

Build key = sha256 over: each input's raw sha256 and the sha256 of its snapshot manifest, the transform module's
sha256, uv.lock's sha256, the sha256 of each source registry YAML read, and of any other file the transform names
(a literature YAML). The manifest and YAML hashes are there because their text is copied into the export (ETag,
archive URLs, credit lines, licence); without them an edit there would be silently skipped. When the key equals the
one recorded for the existing export (pipeline/manifests/builds/<id>.json) and that file is unchanged, the transform
is not run. The git SHA is never part of an export.

A transform that fails (bad file, failed validation or publisher cross-check) leaves its previous export in place;
its sources are reported failed for this run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from envdash import canonical, snapshots
from envdash.models import (
    REDISTRIBUTABLE,
    Indicator,
    Latest,
    Origin,
    ProcessingStep,
    Snapshot,
    Source,
    strictest,
)
from envdash.paths import Paths
from envdash.registry import Registry, render
from envdash.transform import CheckOutcome, InputFile, Result, Transform, ValidationFailed, run_checks, validate

PUBLIC_FILES_BASE = "https://files.environmentdashboard.org/"


@dataclass
class IndicatorOutcome:
    id: str
    state: str  # built | skipped | failed
    source_ids: list[str]
    reason: str | None = None
    checks: list[CheckOutcome] = field(default_factory=list)
    indicator: Indicator | None = None
    """The indicator now exported (the new one, or the previous one when skipped or failed)."""


class BuildError(Exception):
    pass


def lock_sha(paths: Paths) -> str:
    return canonical.sha256_file(paths.lock)


def export_path(paths: Paths, indicator_id: str, licence_class: str) -> Path:
    base = paths.public_indicators if licence_class in REDISTRIBUTABLE else paths.private_indicators
    return base / f"{indicator_id}.json"


def build_key(
    paths: Paths, t: Transform, registry: Registry, pointers: dict[str, str], lock_sha256: str
) -> tuple[str, dict]:
    parts = {
        "inputs": {
            i.key: {
                "sha256": pointers[i.key],
                "manifest_sha256": canonical.sha256_file(snapshots.manifest_path(paths, pointers[i.key])),
            }
            for i in t.inputs
        },
        "transform_sha256": canonical.sha256_file(t.module_file),
        "lock_sha256": lock_sha256,
        "sources": {
            sid: canonical.sha256_file(registry.source_files[sid]) for sid in sorted({i.source_id for i in t.inputs})
        },
        "key_files": {paths.rel(f): canonical.sha256_file(f) for f in t.key_files},
    }
    return canonical.sha256_bytes(canonical.dump_bytes(parts)), parts


def _build_record(paths: Paths, indicator_id: str) -> dict | None:
    p = paths.builds / f"{indicator_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_export(path: Path) -> Indicator:
    return Indicator.model_validate_json(path.read_bytes())


def existing_export(paths: Paths, indicator_id: str) -> Path | None:
    for base in (paths.public_indicators, paths.private_indicators):
        p = base / f"{indicator_id}.json"
        if p.exists():
            return p
    return None


def _render_for(src: Source, result: Result, accessed: date, template: str | None) -> str | None:
    if template is None:
        return None
    return render(template, version=result.vintage, date_accessed=accessed, year=result.year)


def assemble(
    paths: Paths,
    t: Transform,
    result: Result,
    sources: dict[str, Source],
    snaps: dict[str, Snapshot],
    lock_sha256: str,
) -> Indicator:
    """Turn a transform's result into the published Indicator, with origins, steps, licence and credit lines."""
    source_ids = sorted({i.source_id for i in t.inputs})
    accessed = {sid: max(snaps[i.key].date_accessed for i in t.inputs if i.source_id == sid) for sid in source_ids}
    origins: list[Origin] = []
    for i in t.inputs:
        src, snap = sources[i.source_id], snaps[i.key]
        origins.append(
            Origin(
                source_id=src.id,
                artifact_id=i.artifact_id,
                producer=src.publisher,
                title=src.title,
                version_producer=result.vintage,
                citation_full=_render_for(src, result, accessed[src.id], src.citation.text) or "",
                url_main=src.landing_url,
                url_download=snap.url,
                date_published=result.date_published,
                date_accessed=snap.date_accessed,
                licence=src.licence,
                sha256=snap.sha256,
                bytes=snap.bytes,
                etag=snap.etag,
                last_modified=snap.last_modified,
                wayback_url=snap.wayback.url if snap.wayback and snap.wayback.status == "captured" else None,
                r2_url=f"{PUBLIC_FILES_BASE}{snap.r2_key}"
                if snap.r2_bucket == "envdash-public" and snap.r2_key
                else None,
                doi=src.citation.DOI,
                acquisition=snap.acquisition,
            )
        )
    script = paths.rel(t.module_file)
    transform_sha = canonical.sha256_file(t.module_file)
    input_shas = [snaps[i.key].sha256 for i in t.inputs]
    processing = [
        ProcessingStep(
            script=script, transform_sha256=transform_sha, lock_sha256=lock_sha256, inputs=input_shas, description=d
        )
        for d in result.steps
    ]
    classes = [sources[s].licence_class for s in source_ids]
    cls = strictest(classes)
    licences = {sources[s].licence for s in source_ids if sources[s].licence_class == cls}
    if len(licences) != 1:
        raise BuildError(f"{t.spec.id}: inputs at class {cls} carry different licences; declare the combined terms")
    credit: list[str] = []
    notices: list[str] = []
    for sid in source_ids:
        ob = sources[sid].obligations
        if result.changes:
            line = _render_for(sources[sid], result, accessed[sid], ob.attribution_modified or ob.attribution)
            credit.append(f"{line} Changes: {result.changes}")
            if ob.derived_disclaimer:
                notices.append(_render_for(sources[sid], result, accessed[sid], ob.derived_disclaimer) or "")
        else:
            credit.append(_render_for(sources[sid], result, accessed[sid], ob.attribution) or "")
        if ob.notice:
            notices.append(_render_for(sources[sid], result, accessed[sid], ob.notice) or "")
    headline_dims = dict(t.spec.headline_dims)
    candidates = [
        o
        for o in result.observations
        if o.entity == t.spec.headline_entity and o.dims == headline_dims and o.value is not None
    ]
    if not candidates:
        raise BuildError(f"{t.spec.id}: no non-null value for headline entity {t.spec.headline_entity}")
    last = max(candidates, key=lambda o: o.period)
    assert last.value is not None
    return Indicator(
        id=t.spec.id,
        title=t.spec.title,
        description=t.spec.description,
        kind=t.spec.kind,
        unit=t.spec.unit,
        display=t.spec.display,
        scope=t.spec.scope,
        geo_coverage=t.spec.geo_coverage,
        headline_entity=t.spec.headline_entity,
        dimensions=list(t.spec.dimensions),
        observations=result.observations,
        latest=Latest(entity=last.entity, period=last.period, value=last.value, status=last.status, dims=last.dims),
        vintage=result.vintage,
        origins=origins,
        processing=processing,
        licence_class=cls,
        licence=licences.pop(),
        attribution=" ".join(credit),
        notice=" ".join(n for n in notices if n) or None,
        published_value=result.published_value,
    )


def build_one(
    paths: Paths,
    t: Transform,
    registry: Registry,
    pointers: dict[str, str],
    lock_sha256: str,
    *,
    force: bool,
) -> IndicatorOutcome:
    source_ids = sorted({i.source_id for i in t.inputs})
    prev_path = existing_export(paths, t.spec.id)

    def fail(reason: str, checks: list[CheckOutcome] | None = None) -> IndicatorOutcome:
        prev = load_export(prev_path) if prev_path else None
        return IndicatorOutcome(t.spec.id, "failed", source_ids, reason, checks or [], prev)

    missing_src = [s for s in source_ids if s not in registry.sources]
    if missing_src:
        why = "; ".join(
            registry.source_errors.get(s, f"no registry entry pipeline/sources/{s}.yaml") for s in missing_src
        )
        return fail(why)
    missing_ptr = [i.key for i in t.inputs if i.key not in pointers]
    if missing_ptr:
        return fail(f"no snapshot yet for {missing_ptr}; run envdash fetch (or envdash snapshot add)")
    snaps: dict[str, Snapshot] = {}
    for i in t.inputs:
        snap = snapshots.read_manifest(paths, pointers[i.key])
        if snap is None:
            return fail(f"current snapshot {pointers[i.key]} of {i.key} has no manifest")
        snaps[i.key] = snap

    key, _ = build_key(paths, t, registry, pointers, lock_sha256)
    rec = _build_record(paths, t.spec.id)
    reusable = (
        not force
        and rec is not None
        and prev_path is not None
        and rec.get("key") == key
        and canonical.sha256_file(prev_path) == rec.get("export_sha256")
    )
    if reusable and prev_path is not None:
        return IndicatorOutcome(t.spec.id, "skipped", source_ids, indicator=load_export(prev_path))

    files: dict[str, InputFile] = {}
    for i in t.inputs:
        p = snapshots.cache_path(paths, snaps[i.key].sha256)
        if not p.exists():
            return fail(
                f"raw bytes {snaps[i.key].sha256} of {i.key} are not in the local cache {paths.rel(paths.cache)}; "
                "run envdash fetch, or restore them from R2"
            )
        files[i.key] = InputFile(p, snaps[i.key])
    try:
        result = t.run(files)
        validate(t, result.observations)
        vintages = {s: result.vintage for s in source_ids}
        checks = run_checks(t, vintages, result.observations)
        failed_checks = [c for c in checks if c.status == "fail"]
        if failed_checks:
            return fail("publisher cross-check failed: " + "; ".join(c.detail for c in failed_checks), checks)
        ind = assemble(paths, t, result, registry.sources, snaps, lock_sha256)
    except (ValidationFailed, BuildError, ValueError, KeyError) as e:
        return fail(f"{type(e).__name__}: {e}")
    return IndicatorOutcome(t.spec.id, "built", source_ids, None, checks, ind)


def write_build_record(paths: Paths, outcome: IndicatorOutcome, key: str, parts: dict, export: Path) -> None:
    rec = {
        "indicator_id": outcome.id,
        "key": key,
        "key_parts": parts,
        "export": paths.rel(export),
        "export_sha256": canonical.sha256_file(export),
        "publisher_checks": [
            {
                "source_id": c.check.source_id,
                "vintage": c.check.vintage,
                "entity": c.check.entity,
                "period": c.check.period,
                "stated": c.check.stated,
                "quote": c.check.quote,
                "url": c.check.url,
                "status": c.status,
                "detail": c.detail,
            }
            for c in outcome.checks
        ],
    }
    canonical.write_if_changed(paths.builds / f"{outcome.id}.json", canonical.dump_bytes(rec))

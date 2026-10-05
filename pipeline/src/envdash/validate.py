"""`envdash validate`: check the registry, the snapshot manifests and everything under data/ and data-private/.

Returns a list of problems; empty means valid. Checks:
- every source and literature YAML loads;
- every snapshot manifest parses, is named by its sha256, and matches its cached bytes when they are present;
- current.json points only at manifests that exist;
- every exported indicator parses as an IndicatorFile whose expansion is a valid Indicator, is in canonical form
  (re-exporting the expansion gives the same bytes), sits on the side (data/ or data-private/) its licence class
  allows, and matches its catalogue entry's sha256; no non-redistributable value or file is under data/;
- an indicator dated in years before 1950 runs from the oldest age to the youngest within each (entity, dims) series,
  and its latest is the youngest observation of its headline series (the model checks period/age_bp consistency);
- datapackage.json lists exactly the public CSVs with the right hashes and only redistributable licences;
- SHA256SUMS matches the files.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from envdash import canonical, snapshots
from envdash.export import SUMS_EXCLUDE, export_bytes
from envdash.models import REDISTRIBUTABLE, Catalog, Indicator, IndicatorFile, Snapshot, SourceList
from envdash.paths import Paths
from envdash.registry import Registry


def _canonical(path: Path, model) -> tuple[object | None, list[str]]:
    data = path.read_bytes()
    try:
        obj = model.model_validate_json(data)
    except ValidationError as e:
        return None, [f"{path.name}: invalid {model.__name__}: {e.errors()[:3]}"]
    if canonical.dump_bytes(obj) != data:
        return obj, [f"{path.name}: not in canonical form (rebuild with envdash build)"]
    return obj, []


def _indicator(path: Path) -> tuple[Indicator | None, list[str]]:
    """An exported IndicatorFile, expanded and checked as an Indicator, and re-exported to the same bytes."""
    data = path.read_bytes()
    try:
        ind = IndicatorFile.model_validate_json(data).to_indicator()
    except ValidationError as e:
        return None, [f"{path.name}: invalid IndicatorFile: {e.errors()[:3]}"]
    if export_bytes(ind) != data:
        return ind, [f"{path.name}: not in canonical form (rebuild with envdash build)"]
    return ind, []


def _paleo_order(ind: Indicator) -> list[str]:
    """Ages strictly decrease (oldest first) within each series, and latest is the youngest headline observation."""
    out: list[str] = []
    last: dict[tuple, float] = {}
    for o in ind.observations:
        series = (o.entity, tuple(sorted(o.dims.items())))
        assert o.age_bp is not None  # the model guarantees it for this time basis
        if series in last and not o.age_bp < last[series]:
            out.append(f"{ind.id}: {o.entity} age {o.age_bp!r} yr BP does not follow {last[series]!r} (oldest first)")
        last[series] = o.age_bp
    head = [
        o.age_bp
        for o in ind.observations
        if o.entity == ind.headline_entity and o.dims == ind.latest.dims and o.value is not None
    ]
    if head and ind.latest.age_bp != min(a for a in head if a is not None):
        out.append(f"{ind.id}: latest age {ind.latest.age_bp!r} yr BP is not the youngest headline observation")
    return out


def validate_all(paths: Paths, registry: Registry) -> list[str]:
    problems: list[str] = [*registry.source_errors.values(), *registry.literature_errors.values()]

    for p in sorted(paths.snapshot_manifests.glob("*.json")) if paths.snapshot_manifests.exists() else []:
        try:
            snap = Snapshot.model_validate_json(p.read_bytes())
        except ValidationError as e:
            problems.append(f"manifest {p.name}: {e.errors()[:2]}")
            continue
        if p.stem != snap.sha256:
            problems.append(f"manifest {p.name} records sha256 {snap.sha256}")
        cached = snapshots.cache_path(paths, snap.sha256)
        if cached.exists() and canonical.sha256_file(cached) != snap.sha256:
            problems.append(f"cached bytes {cached.name} do not hash to their name")
    for k, sha in snapshots.read_current(paths).items():
        if not snapshots.manifest_path(paths, sha).exists():
            problems.append(f"current.json: {k} -> {sha} has no manifest")

    catalog_path = paths.data / "v1" / "catalog.json"
    catalog: Catalog | None = None
    if catalog_path.exists():
        catalog, errs = _canonical(catalog_path, Catalog)  # type: ignore[assignment]
        problems += errs
    else:
        problems.append("data/v1/catalog.json is missing")
    sources_path = paths.data / "v1" / "sources.json"
    if sources_path.exists():
        problems += _canonical(sources_path, SourceList)[1]
    entries = {e.id: e for e in catalog.indicators} if catalog else {}

    seen: set[str] = set()
    for base, public in ((paths.public_indicators, True), (paths.private_indicators, False)):
        for p in sorted(base.glob("*.json")) if base.exists() else []:
            ind, errs = _indicator(p)
            problems += errs
            if ind is None:
                continue
            seen.add(ind.id)
            if p.stem != ind.id:
                problems.append(f"{p.name} holds indicator {ind.id}")
            if public != (ind.licence_class in REDISTRIBUTABLE):
                problems.append(f"{ind.id} ({ind.licence_class}) is on the wrong side: {paths.rel(p)}")
            e = entries.get(ind.id)
            if e is None:
                problems.append(f"{ind.id} is not in the catalogue")
            elif e.export_sha256 != canonical.sha256_file(p):
                problems.append(f"{ind.id}: catalogue export_sha256 does not match {paths.rel(p)}")
            if ind.time_basis == "years-before-1950":
                problems += _paleo_order(ind)
            if public and not (base / f"{ind.id}.csv").exists():
                problems.append(f"{ind.id}: CSV missing")
    for e in entries.values():
        if e.id not in seen:
            problems.append(f"catalogue lists {e.id} but no export exists")
    for p in sorted(paths.public_indicators.glob("*.csv")) if paths.public_indicators.exists() else []:
        if p.stem not in seen or entries.get(p.stem) is None or not entries[p.stem].downloadable:
            problems.append(f"{p.name} is under data/ without a redistributable indicator")

    dp_path = paths.data / "datapackage.json"
    if dp_path.exists():
        dp = json.loads(dp_path.read_text(encoding="utf-8"))
        listed = {r["path"]: r for r in dp.get("resources", [])}
        public_csvs = {
            p.relative_to(paths.data).as_posix(): p
            for p in (paths.public_indicators.glob("*.csv") if paths.public_indicators.exists() else [])
        }
        if set(listed) != set(public_csvs):
            problems.append(f"datapackage.json resources {sorted(listed)} != public CSVs {sorted(public_csvs)}")
        for rel, r in listed.items():
            if rel in public_csvs and r.get("hash") != f"sha256:{canonical.sha256_file(public_csvs[rel])}":
                problems.append(f"datapackage.json hash for {rel} is stale")
            e = entries.get(r.get("name", ""))
            if e is not None and e.licence_class not in REDISTRIBUTABLE:
                problems.append(f"datapackage.json lists {e.id} of class {e.licence_class}")
    else:
        problems.append("data/datapackage.json is missing")

    sums_path = paths.data / "SHA256SUMS"
    if sums_path.exists():
        listed_sums = {}
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            sha, rel = line.split("  ", 1)
            listed_sums[rel] = sha
        actual = {
            p.relative_to(paths.data).as_posix(): p
            for p in paths.data.rglob("*")
            if p.is_file() and p.relative_to(paths.data).as_posix() not in SUMS_EXCLUDE
        }
        if set(listed_sums) != set(actual):
            problems.append(f"SHA256SUMS lists {sorted(set(listed_sums) ^ set(actual))} differently from data/")
        for rel, sha in listed_sums.items():
            if rel in actual and canonical.sha256_file(actual[rel]) != sha:
                problems.append(f"SHA256SUMS: {rel} changed")
    else:
        problems.append("data/SHA256SUMS is missing")
    return problems

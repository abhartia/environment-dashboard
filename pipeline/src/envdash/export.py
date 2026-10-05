"""Write the published files.

data/ (committed, public; redistributable classes only):
  v1/indicators/<id>.json   canonical IndicatorFile JSON: the indicator with its observations as columns (one array
                            per field, notes interned; see models.IndicatorFile)
  v1/indicators/<id>.csv    tidy CSV; '#' header lines carry the title, credit line, notice, licence and the URL of
                            the indicator's page (/data/<id with dots as slashes>). Columns: CSV_FIXED, then one per
                            dimension. An indicator dated in years before 1950 has an empty period and an age_bp.
  v1/catalog.json           every indicator that is not excluded (no-derivatives and display-only entries carry
                            no values: latest is null and there is no download)
  v1/sources.json           the source registry
  datapackage.json          Frictionless Data Package v2 of the CSVs, each with its own licence
  SHA256SUMS                every file above (status.json is rewritten each run and is not listed)
data-private/ (never committed or deployed as a file):
  v1/indicators/<id>.json   no-derivatives and display-only indicators, as IndicatorFile JSON
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from envdash import canonical
from envdash.build import IndicatorOutcome, build_key, build_one, export_path, lock_sha, write_build_record
from envdash.models import REDISTRIBUTABLE, Catalog, CatalogEntry, Indicator, IndicatorFile, Provenance, SourceList
from envdash.paths import Paths
from envdash.registry import Registry
from envdash.snapshots import read_current
from envdash.transform import Transform

SITE = "https://environmentdashboard.org"
SUMS_EXCLUDE = {"SHA256SUMS", "v1/status.json"}
CSV_FIXED = [
    "indicator_id",
    "entity",
    "period",
    "value",
    "lower",
    "upper",
    "interval",
    "status",
    "note",
    "missing_reason",
    "age_bp",
]
"""age_bp is last so that the columns before it keep their positions from before it was added."""


def page_url(indicator_id: str) -> str:
    """The indicator's page on the site: /data/ then the id with each dot as a path segment
    (co2.noaa-gml.monthly-mlo -> /data/co2/noaa-gml/monthly-mlo)."""
    return f"{SITE}/data/{indicator_id.replace('.', '/')}"


@dataclass
class BuildReport:
    outcomes: list[IndicatorOutcome] = field(default_factory=list)
    literature_errors: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> list[IndicatorOutcome]:
        return [o for o in self.outcomes if o.state == "failed"]

    @property
    def ok(self) -> bool:
        return not self.failed and not self.literature_errors


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _num(x: float | None) -> str:
    return "" if x is None else canonical.format_float(x)


def csv_bytes(ind: Indicator) -> bytes:
    dim_ids = [d.id for d in ind.dimensions]
    out = io.StringIO(newline="")
    origin = ind.origins[0]
    lines = [
        ind.title,
        f"Indicator: {ind.id} (vintage {ind.vintage}); unit: {ind.unit.label} ({ind.unit.code})",
        f"Source: {'; '.join(sorted({o.producer for o in ind.origins}))} <{origin.url_main}>",
        f"Credit: {ind.attribution}",
    ]
    if ind.notice:
        lines.append(f"Notice: {ind.notice}")
    lic = ind.licence
    lines.append(f"Licence: {lic.name}" + (f" <{lic.url}>" if lic.url else ""))
    if ind.time_basis == "years-before-1950":
        lines.append(
            "Time: age_bp is the age in years before 1950 as published (negative after 1950); period is empty."
        )
    lines.append(f"Provenance and processing: {page_url(ind.id)}")
    for ln in lines:
        out.write("# " + _one_line(ln) + "\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_FIXED + dim_ids)
    for o in ind.observations:
        w.writerow(
            [
                ind.id,
                o.entity,
                o.period or "",
                _num(o.value),
                _num(o.lower),
                _num(o.upper),
                o.interval or "",
                o.status,
                o.note or "",
                o.missing_reason or "",
                _num(o.age_bp),
            ]
            + [o.dims[d] for d in dim_ids]
        )
    return out.getvalue().encode("utf-8")


def export_bytes(ind: Indicator) -> bytes:
    """The canonical published JSON of an indicator: its IndicatorFile, observations stored as columns."""
    return canonical.dump_bytes(IndicatorFile.from_indicator(ind))


def write_indicator(paths: Paths, ind: Indicator) -> Path:
    """Write the indicator to data/ or data-private/ by its licence class, removing any copy on the other side."""
    dest = export_path(paths, ind.id, ind.licence_class)
    canonical.write_if_changed(dest, export_bytes(ind))
    public_json = paths.public_indicators / f"{ind.id}.json"
    public_csv = paths.public_indicators / f"{ind.id}.csv"
    private_json = paths.private_indicators / f"{ind.id}.json"
    if ind.licence_class in REDISTRIBUTABLE:
        canonical.write_if_changed(public_csv, csv_bytes(ind))
        private_json.unlink(missing_ok=True)
    else:
        public_json.unlink(missing_ok=True)
        public_csv.unlink(missing_ok=True)
    return dest


def catalog_entry(paths: Paths, ind: Indicator) -> CatalogEntry:
    redistributable = ind.licence_class in REDISTRIBUTABLE
    return CatalogEntry(
        id=ind.id,
        title=ind.title,
        unit=ind.unit,
        display=ind.display,
        licence_class=ind.licence_class,
        source_ids=sorted({o.source_id for o in ind.origins}),
        vintage=ind.vintage,
        time_basis=ind.time_basis,
        latest=ind.latest if redistributable else None,
        geo_coverage=ind.geo_coverage,
        entities=sorted({o.entity for o in ind.observations}),
        downloadable=redistributable,
        export_sha256=canonical.sha256_file(export_path(paths, ind.id, ind.licence_class)),
        provenance=Provenance(
            description=ind.description,
            kind=ind.kind,
            scope=ind.scope,
            licence=ind.licence,
            attribution=ind.attribution,
            notice=ind.notice,
            origins=ind.origins,
            processing=ind.processing,
            published_value=ind.published_value,
        ),
    )


def datapackage(paths: Paths, indicators: list[Indicator]) -> dict:
    resources = []
    for ind in indicators:
        if ind.licence_class not in REDISTRIBUTABLE:
            continue
        p = paths.public_indicators / f"{ind.id}.csv"
        data = p.read_bytes()
        lic: dict[str, str] = {"title": ind.licence.name}
        if ind.licence.spdx:
            lic["name"] = ind.licence.spdx
        if ind.licence.url:
            lic["path"] = str(ind.licence.url)
        fields = [
            {"name": "indicator_id", "type": "string"},
            {"name": "entity", "type": "string"},
            {
                "name": "period",
                "type": "string",
                "description": "ISO 8601 year, year-month or date; empty when the row is dated by age_bp",
            },
            {"name": "value", "type": "number", "description": f"{ind.unit.label} ({ind.unit.code})"},
            {"name": "lower", "type": "number"},
            {"name": "upper", "type": "number"},
            {"name": "interval", "type": "string"},
            {"name": "status", "type": "string"},
            {"name": "note", "type": "string"},
            {"name": "missing_reason", "type": "string"},
            {
                "name": "age_bp",
                "type": "number",
                "description": "Age in years before 1950 as published (negative after 1950); empty when the row is "
                "dated by period",
            },
        ] + [{"name": d.id, "type": "string", "title": d.label} for d in ind.dimensions]
        resources.append(
            {
                "name": ind.id,
                "title": ind.title,
                "description": ind.description,
                "path": p.relative_to(paths.data).as_posix(),
                "format": "csv",
                "mediatype": "text/csv",
                "encoding": "utf-8",
                "bytes": len(data),
                "hash": f"sha256:{canonical.sha256_bytes(data)}",
                "dialect": {"$schema": "https://datapackage.org/profiles/2.0/tabledialect.json", "commentChar": "#"},
                "licenses": [lic],
                "sources": [
                    {"title": f"{o.producer}: {o.title}", "path": str(o.url_main)}
                    for o in sorted({o.source_id: o for o in ind.origins}.values(), key=lambda o: o.source_id)
                ],
                "schema": {
                    "$schema": "https://datapackage.org/profiles/2.0/tableschema.json",
                    "fields": fields,
                    "missingValues": [""],
                },
            }
        )
    return {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "name": "environment-dashboard",
        "title": "Environment Dashboard data",
        "description": "Indicators published on environmentdashboard.org, each traceable to its primary source. "
        "Every resource carries its own licence; there is no package-wide licence.",
        "homepage": f"{SITE}/data",
        "resources": sorted(resources, key=lambda r: r["name"]),
    }


def write_sums(paths: Paths) -> None:
    lines = []
    for p in sorted(paths.data.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(paths.data).as_posix()
        if rel in SUMS_EXCLUDE or rel.endswith(".tmp"):
            continue
        lines.append(f"{canonical.sha256_file(p)}  {rel}\n")
    canonical.write_if_changed(paths.data / "SHA256SUMS", "".join(lines).encode("utf-8"))


def remove_orphans(paths: Paths, declared: set[str]) -> list[str]:
    """Indicator files whose transform no longer exists. Ids are never renamed, so this is a deliberate removal."""
    removed = []
    for base in (paths.public_indicators, paths.private_indicators):
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            stem = p.name.removesuffix(".json").removesuffix(".csv")
            if p.suffix in {".json", ".csv"} and stem not in declared:
                p.unlink()
                removed.append(p.name)
    return removed


def build_and_export(
    paths: Paths, registry: Registry, transforms: list[Transform], *, force: bool = False
) -> BuildReport:
    report = BuildReport(literature_errors=dict(registry.literature_errors))
    pointers = read_current(paths)
    lock = lock_sha(paths)
    exported: list[Indicator] = []
    for t in transforms:
        try:
            outcome = build_one(paths, t, registry, pointers, lock, force=force)
        except Exception as e:  # one indicator's bug never stops the others
            outcome = IndicatorOutcome(
                t.spec.id, "failed", sorted({i.source_id for i in t.inputs}), f"{type(e).__name__}: {e}"
            )
        if outcome.state == "built" and outcome.indicator is not None:
            dest = write_indicator(paths, outcome.indicator)
            key, parts = build_key(paths, t, registry, pointers, lock)
            write_build_record(paths, outcome, key, parts, dest)
        elif outcome.state == "failed" and outcome.indicator is not None:
            # The previous export stays, values unchanged; re-serialising it keeps it in the current canonical form
            # (fields added to the contract since it was written appear with their defaults). A no-op otherwise.
            write_indicator(paths, outcome.indicator)
        if outcome.indicator is not None:
            exported.append(outcome.indicator)
        report.outcomes.append(outcome)
    remove_orphans(paths, {t.spec.id for t in transforms})
    exported.sort(key=lambda i: i.id)
    catalog = Catalog(indicators=[catalog_entry(paths, i) for i in exported])
    canonical.write_if_changed(paths.data / "v1" / "catalog.json", canonical.dump_bytes(catalog))
    public_sources = [s for _, s in sorted(registry.sources.items()) if s.licence_class != "excluded"]
    canonical.write_if_changed(
        paths.data / "v1" / "sources.json", canonical.dump_bytes(SourceList(sources=public_sources))
    )
    canonical.write_if_changed(paths.data / "datapackage.json", canonical.dump_bytes(datapackage(paths, exported)))
    write_sums(paths)
    return report

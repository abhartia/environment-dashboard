"""Exports we may show but not redistribute (no-derivatives, display-only) live in data-private/, which is not in git.

`envdash private push` copies them to the private R2 bucket after a build; `envdash private pull` fetches the ones
the catalogue lists before a web build anywhere else (CI, a fresh checkout). Every pulled file must hash to the
export_sha256 the public catalogue records, so the site can only ever show the bytes the pipeline published.
"""

from __future__ import annotations

from pathlib import Path

from envdash import canonical
from envdash.archive import PRIVATE_BUCKET
from envdash.models import Catalog
from envdash.paths import Paths

PREFIX = "exports/v1/indicators"


class PrivateExportError(RuntimeError):
    pass


def _key(indicator_id: str) -> str:
    return f"{PREFIX}/{indicator_id}.json"


def private_entries(paths: Paths) -> list:
    catalog_path = paths.data / "v1" / "catalog.json"
    if not catalog_path.exists():
        raise PrivateExportError("data/v1/catalog.json is missing; run envdash build first")
    catalog = Catalog.model_validate_json(catalog_path.read_bytes())
    return [e for e in catalog.indicators if not e.downloadable]


def push(paths: Paths, client) -> list[str]:  # pragma: no cover - needs R2
    """Upload every private export the catalogue lists; each must exist locally and match its catalogue hash."""
    pushed: list[str] = []
    for entry in private_entries(paths):
        local = paths.private_indicators / f"{entry.id}.json"
        if not local.exists():
            raise PrivateExportError(f"{entry.id}: listed in the catalogue but {paths.rel(local)} is missing")
        data = local.read_bytes()
        if canonical.sha256_bytes(data) != entry.export_sha256:
            raise PrivateExportError(f"{entry.id}: {paths.rel(local)} does not match the catalogue's export_sha256")
        client.put_object(
            Bucket=PRIVATE_BUCKET,
            Key=_key(entry.id),
            Body=data,
            ContentType="application/json",
            Metadata={"sha256": entry.export_sha256},
        )
        pushed.append(entry.id)
    return pushed


def pull(paths: Paths, client) -> list[str]:  # pragma: no cover - needs R2
    """Download every private export the catalogue lists and check it against the catalogue hash."""
    pulled: list[str] = []
    for entry in private_entries(paths):
        local: Path = paths.private_indicators / f"{entry.id}.json"
        if local.exists() and canonical.sha256_file(local) == entry.export_sha256:
            pulled.append(entry.id)
            continue
        try:
            body = client.get_object(Bucket=PRIVATE_BUCKET, Key=_key(entry.id))["Body"].read()
        except client.exceptions.NoSuchKey:
            raise PrivateExportError(
                f"{entry.id}: not in {PRIVATE_BUCKET}/{_key(entry.id)} (run envdash private push)"
            ) from None
        if canonical.sha256_bytes(body) != entry.export_sha256:
            raise PrivateExportError(f"{entry.id}: the archived export does not match the catalogue's export_sha256")
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(body)
        pulled.append(entry.id)
    return pulled

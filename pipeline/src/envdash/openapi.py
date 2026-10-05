"""pipeline/schema/openapi.json: an OpenAPI 3.1 description of the static files under /data/v1.

There is no API server: each GET path is a file the site serves. Component schemas come from the pydantic models
(serialization mode, so every field the exports always write is required). The web generates its client and
TanStack Query options from this file (`npm run gen:api`), so component names are the model names and must stay
stable.

getIndicator returns an IndicatorFile (observations as columns). Indicator, the same indicator with its observations
as records, is listed as a component though no path returns it: it is the shape web/src/lib/indicator-table.ts
expands an IndicatorFile into, so the web's types for it are generated from the same models.
"""

from __future__ import annotations

from pydantic.json_schema import models_json_schema

from envdash import canonical
from envdash.models import SCHEMA_VERSION, Catalog, Indicator, IndicatorFile, SourceList, Status
from envdash.paths import Paths

REF = "#/components/schemas/{model}"


def _ok(schema: str, description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": REF.format(model=schema)}}},
    }


def document() -> dict:
    _, defs = models_json_schema(
        [(m, "serialization") for m in (Catalog, IndicatorFile, Indicator, SourceList, Status)], ref_template=REF
    )
    not_found = {"description": "No such file."}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Environment Dashboard data",
            "version": f"{SCHEMA_VERSION}",
            "description": "Static JSON files published with the site. Every value carries its origins (the exact "
            "raw files, by sha256), the processing applied and its licence.",
            "license": {
                "name": "Each indicator carries its own licence",
                "url": "https://environmentdashboard.org/data",
            },
        },
        "servers": [{"url": "https://environmentdashboard.org"}],
        "paths": {
            "/data/v1/catalog.json": {
                "get": {
                    "operationId": "getCatalog",
                    "summary": "Every published indicator, without its observations",
                    "tags": ["data"],
                    "responses": {"200": _ok("Catalog", "The catalogue.")},
                }
            },
            "/data/v1/indicators/{id}.json": {
                "get": {
                    "operationId": "getIndicator",
                    "summary": "One indicator with its observations (as columns) and provenance",
                    "tags": ["data"],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "Indicator id, e.g. co2.noaa-gml.monthly-mlo",
                            "schema": {"type": "string", "pattern": r"^[a-z0-9-]+(\.[a-z0-9-]+){1,3}$"},
                        }
                    ],
                    "responses": {"200": _ok("IndicatorFile", "The indicator."), "404": not_found},
                }
            },
            "/data/v1/sources.json": {
                "get": {
                    "operationId": "getSources",
                    "summary": "The source registry: licences, evidence, obligations and artifacts",
                    "tags": ["data"],
                    "responses": {"200": _ok("SourceList", "The sources.")},
                }
            },
            "/data/v1/status.json": {
                "get": {
                    "operationId": "getStatus",
                    "summary": "How each source fared in the latest pipeline run",
                    "tags": ["data"],
                    "responses": {"200": _ok("Status", "The status.")},
                }
            },
        },
        "components": {"schemas": dict(sorted(defs["$defs"].items()))},
    }


def write(paths: Paths) -> bool:
    return canonical.write_if_changed(paths.schema / "openapi.json", canonical.dump_bytes(document()))

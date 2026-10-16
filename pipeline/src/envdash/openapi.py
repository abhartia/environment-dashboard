"""pipeline/schema/openapi.json: an OpenAPI 3.1 description of the static files under /data/v1.

There is no API server: each GET path is a file the site serves. Component schemas come from the pydantic models
(serialization mode, so every field the exports always write is required). The web generates its client and
TanStack Query options from this file (`npm run gen:api`), so component names are the model names and must stay
stable.

getIndicator returns an IndicatorFile (observations as columns). Indicator, the same indicator with its observations
as records, is listed as a component though no path returns it: it is the shape web/src/lib/indicator-table.ts
expands an IndicatorFile into, so the web's types for it are generated from the same models.

The map files under /data/v1/geo/ (envdash/geo_shapes.py) are TopoJSON, described by the TopoJsonTopology component
below (written here, not from a model: the topojson library makes them), with their index (GeoIndex) and the CCKP
crosswalk (CSV).
"""

from __future__ import annotations

from pydantic.json_schema import models_json_schema

from envdash import canonical
from envdash.models import SCHEMA_VERSION, Catalog, GeoIndex, Indicator, IndicatorFile, SourceList, Status
from envdash.paths import Paths

REF = "#/components/schemas/{model}"
ENTITY_PATTERN = r"^[A-Z0-9_]{2,12}$"

TOPOLOGY = {
    "title": "TopoJsonTopology",
    "description": "A TopoJSON topology (https://github.com/topojson/topojson-specification): quantised, "
    "delta-encoded arcs and the objects drawn from them. world.topo.json has objects countries (id: entity code) and "
    "disputed; adm1/<entity>.topo.json has objects regions (id: CCKP region code, or V1:<record>) and disputed. Every "
    "geometry carries properties.rp, a representative point [longitude, latitude]; a null geometry is a place too "
    "small to draw at the file's scale. meta carries the credit line and licence.",
    "type": "object",
    "required": ["type", "objects", "arcs", "transform", "meta"],
    "properties": {
        "type": {"const": "Topology"},
        "bbox": {"type": "array", "items": {"type": "number"}},
        "transform": {
            "type": "object",
            "required": ["scale", "translate"],
            "properties": {
                "scale": {"type": "array", "items": {"type": "number"}},
                "translate": {"type": "array", "items": {"type": "number"}},
            },
        },
        "arcs": {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}}},
        "objects": {"type": "object", "additionalProperties": {"type": "object"}},
        "meta": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}


def _ok(schema: str, description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": REF.format(model=schema)}}},
    }


def document() -> dict:
    _, defs = models_json_schema(
        [(m, "serialization") for m in (Catalog, IndicatorFile, Indicator, SourceList, Status, GeoIndex)],
        ref_template=REF,
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
            "/data/v1/geo/index.json": {
                "get": {
                    "operationId": "getGeoIndex",
                    "summary": "The map files: their origins, processing, licence, and how CCKP's regions were matched",
                    "tags": ["geo"],
                    "responses": {"200": _ok("GeoIndex", "The index of the map files.")},
                }
            },
            "/data/v1/geo/world.topo.json": {
                "get": {
                    "operationId": "getWorldShapes",
                    "summary": "Countries and disputed areas of the world, simplified (TopoJSON)",
                    "tags": ["geo"],
                    "responses": {"200": _ok("TopoJsonTopology", "The world map.")},
                }
            },
            "/data/v1/geo/adm1/{entity}.topo.json": {
                "get": {
                    "operationId": "getRegionShapes",
                    "summary": "One country's states or provinces as CCKP's regions, with nearby disputed areas",
                    "tags": ["geo"],
                    "parameters": [
                        {
                            "name": "entity",
                            "in": "path",
                            "required": True,
                            "description": "Entity code of the country, e.g. IND; GeoIndex.countries[].file lists them",
                            "schema": {"type": "string", "pattern": ENTITY_PATTERN},
                        }
                    ],
                    "responses": {"200": _ok("TopoJsonTopology", "The country's map."), "404": not_found},
                }
            },
            "/data/v1/geo/cckp-adm1-crosswalk.csv": {
                "get": {
                    "operationId": "getCckpCrosswalk",
                    "summary": "Every CCKP region and World Bank admin-1 shape, with the pair made and how (CSV)",
                    "tags": ["geo"],
                    "responses": {
                        "200": {
                            "description": "The crosswalk, with '#' comment lines first.",
                            "content": {"text/csv": {"schema": {"type": "string"}}},
                        }
                    },
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
        "components": {"schemas": dict(sorted({**defs["$defs"], "TopoJsonTopology": TOPOLOGY}.items()))},
    }


def write(paths: Paths) -> bool:
    return canonical.write_if_changed(paths.schema / "openapi.json", canonical.dump_bytes(document()))

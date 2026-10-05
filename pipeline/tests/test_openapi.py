from __future__ import annotations

from envdash import canonical, openapi
from envdash.paths import Paths


def test_committed_openapi_matches_models():
    committed = (Paths.default().schema / "openapi.json").read_bytes()
    assert committed == canonical.dump_bytes(openapi.document()), "run: uv run envdash openapi"


def test_paths_and_components():
    doc = openapi.document()
    assert set(doc["paths"]) == {
        "/data/v1/catalog.json",
        "/data/v1/indicators/{id}.json",
        "/data/v1/sources.json",
        "/data/v1/status.json",
    }
    for name in ("Catalog", "CatalogEntry", "Indicator", "Observation", "SourceList", "Status", "Source"):
        assert name in doc["components"]["schemas"]
    assert "note" in doc["components"]["schemas"]["Observation"]["required"]


def test_get_indicator_returns_the_columnar_file():
    doc = openapi.document()
    ok = doc["paths"]["/data/v1/indicators/{id}.json"]["get"]["responses"]["200"]
    assert ok["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/IndicatorFile"}
    schemas = doc["components"]["schemas"]
    assert {"table", "notes"} <= set(schemas["IndicatorFile"]["required"])
    assert "observations" not in schemas["IndicatorFile"]["properties"]
    table = schemas["ObservationTable"]
    assert set(table["required"]) == {"entity", "value", "status", "dims"}
    # Optional columns are absent, never null: the schema is the array alone.
    assert table["properties"]["lower"]["type"] == "array"
    assert table["properties"]["note"]["items"] == {"anyOf": [{"minimum": 0, "type": "integer"}, {"type": "null"}]}

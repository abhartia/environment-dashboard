"""Additive fields of the data contract: access keys, formats, content keys, quotable literature artifacts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from envdash.models import Access, Artifact
from envdash.paths import Paths
from envdash.registry import load_registry

URL = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/WPP2024_CSV_files_update.zip"


def test_access_key_location_rules():
    assert Access(auth="api-key", auth_env="GFW_API_KEY", key_header="x-api-key").key_header == "x-api-key"
    assert Access(auth="api-key", auth_env="IDMC_CLIENT_ID", key_query="client_id").key_query == "client_id"
    with pytest.raises(ValidationError, match="not both"):
        Access(auth="api-key", auth_env="K", key_header="x-api-key", key_query="key")
    with pytest.raises(ValidationError, match="only to auth api-key"):
        Access(auth="earthdata", auth_env="EARTHDATA_TOKEN", key_header="x-api-key")
    # Without a key location the entry still loads; the fetch fails and says why.
    Access(auth="api-key", auth_env="K")


@pytest.mark.parametrize("fmt", ["xml", "rds", "xls", "csv.gz"])
def test_new_formats(fmt):
    Artifact(id="a", url=URL, format=fmt, description="d")


def test_content_key_rules():
    Artifact(id="a", url=URL, format="zip", description="d", content_key="zip-members", member_name_ignore=r"_\d+")
    with pytest.raises(ValidationError, match="needs format zip"):
        Artifact(id="a", url=URL, format="csv", description="d", content_key="zip-members")
    with pytest.raises(ValidationError, match="only with a content_key"):
        Artifact(id="a", url=URL, format="zip", description="d", member_name_ignore="x")
    with pytest.raises(ValidationError, match="not a valid regex"):
        Artifact(id="a", url=URL, format="zip", description="d", content_key="zip-members", member_name_ignore="(")


def test_registry_uses_the_new_fields():
    reg = load_registry(Paths.default())
    assert not reg.source_errors and not reg.literature_errors
    wpp = {a.id: a for a in reg.sources["un-wpp-2024"].artifacts}
    assert wpp["demographic-indicators-medium"].format == "csv.gz"
    assert all(a.access.key_header == "x-api-key" for a in reg.sources["gfw-tree-cover-loss"].artifacts)
    fra = {a.id: a for a in reg.sources["fao-fra-2025"].artifacts}["bulk-download-world"]
    assert fra.content_key == "zip-members" and fra.member_name_ignore
    for sid in ("noaaglobaltemp-v6", "c3s-era5-bulletin", "oisst-v2", "rutgers-snow-cdr"):
        assert any(a.discover is not None and a.url is None for a in reg.sources[sid].artifacts), sid
    gml = reg.sources["noaa-gml-trends"].obligations
    assert gml.no_endorsement and gml.notice and "not subject to copyright protection" in gml.notice
    assert reg.literature["ipcc-ar6-wg3-spm-c12"].pdf_page == 41

"""Additive fields of the data contract: access keys, formats, content keys, quotable literature artifacts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from envdash.models import Access, Artifact
from envdash.paths import Paths
from envdash.registry import load_registry

from support import exported

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


# --- time basis (calendar periods or years before 1950) ------------------------------------------------------------


def test_observation_has_exactly_one_of_period_and_age():
    from envdash.models import Latest, Observation

    # Values from bereiter-2015-co2 (first file row) and noaa-gml-trends co2_annmean_gl.csv (2025 row).
    Observation(entity="ANT_ICECORES", age_bp=-51.03, value=368.02)
    Observation(entity="WLD", period="2025", value=425.62)
    with pytest.raises(ValidationError, match="exactly one of period"):
        Observation(entity="WLD", value=425.62)
    with pytest.raises(ValidationError, match="exactly one of period"):
        Observation(entity="ANT_ICECORES", period="2001", age_bp=-51.03, value=368.02)
    with pytest.raises(ValidationError, match="finite"):
        Observation(entity="ANT_ICECORES", age_bp=float("nan"), value=368.02)
    with pytest.raises(ValidationError, match="exactly one of period"):
        Latest(entity="WLD", value=425.62, status="final")


def test_indicator_time_basis_must_match_its_observations():
    from envdash.models import Indicator, Latest, Observation

    path = Paths.default().data / "v1" / "indicators" / "co2.noaa-gml.annual-global.json"
    raw = exported(path)
    ind = Indicator.model_validate(raw)
    assert ind.time_basis == "calendar"
    # The youngest row of bereiter-2015-co2, put into another indicator's export only to test the model's rules.
    paleo_obs = Observation(entity="ANT_ICECORES", age_bp=-51.03, value=368.02)
    with pytest.raises(ValidationError, match="time_basis calendar needs a period"):
        Indicator.model_validate({**raw, "observations": [paleo_obs.model_dump()]})
    with pytest.raises(ValidationError, match="years-before-1950 needs age_bp"):
        Indicator.model_validate({**raw, "time_basis": "years-before-1950"})
    latest = Latest(entity="ANT_ICECORES", age_bp=-51.03, value=368.02, status="final")
    ok = {**raw, "time_basis": "years-before-1950", "observations": [paleo_obs.model_dump()]}
    assert Indicator.model_validate({**ok, "latest": latest.model_dump()}).latest.age_bp == -51.03


def test_csv_links_the_nested_page_path():
    from envdash.export import page_url

    assert page_url("co2.noaa-gml.monthly-mlo") == "https://environmentdashboard.org/data/co2/noaa-gml/monthly-mlo"

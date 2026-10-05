from __future__ import annotations

import pytest
from pydantic import ValidationError

from envdash.models import Catalog, CatalogEntry, Display, Latest, Observation, Unit, strictest
from envdash.paths import Paths
from envdash.registry import load_registry

PPM = Unit(code="ppm", label="parts per million", short="ppm")


def test_null_value_needs_reason():
    with pytest.raises(ValidationError, match="missing_reason"):
        Observation(entity="WLD", period="2025", value=None)
    Observation(entity="WLD", period="2025", value=None, missing_reason="sentinel -99.99")


def test_bounds_come_together_and_need_interval():
    with pytest.raises(ValidationError, match="together"):
        Observation(entity="WLD", period="2025", value=1.0, lower=0.5)
    with pytest.raises(ValidationError, match="interval"):
        Observation(entity="WLD", period="2025", value=1.0, lower=0.5, upper=1.5)


@pytest.mark.parametrize("period", ["2025", "2025-08", "2025-08-31", "2012/2021"])
def test_period_formats_accepted(period):
    Observation(entity="WLD", period=period, value=1.0)


@pytest.mark.parametrize("period", ["25", "2025-8", "Aug 2025", "2025Q1"])
def test_period_formats_rejected(period):
    with pytest.raises(ValidationError):
        Observation(entity="WLD", period=period, value=1.0)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        Observation(entity="WLD", period="2025", value=1.0, colour="red")


def test_strictest_class():
    assert strictest(["open", "display-only", "noncommercial"]) == "display-only"
    assert strictest(["open", "share-alike"]) == "share-alike"


def _provenance():
    """A real provenance block, from the published catalogue (no invented origins)."""
    catalog = Catalog.model_validate_json((Paths.default().data / "v1" / "catalog.json").read_bytes())
    return catalog.indicators[0].provenance


def _entry(cls: str, latest: Latest | None, downloadable: bool) -> CatalogEntry:
    return CatalogEntry(
        id="co2.noaa-gml.annual-global",
        title="t",
        unit=PPM,
        display=Display(decimals=2),
        licence_class=cls,
        source_ids=["noaa-gml-trends"],
        vintage="2026-09",
        latest=latest,
        geo_coverage="global-only",
        entities=["WLD"],
        downloadable=downloadable,
        export_sha256="0" * 64,
        provenance=_provenance(),
    )


def test_catalog_hides_values_of_display_only():
    latest = Latest(entity="WLD", period="2025", value=425.62, status="preliminary")
    _entry("open", latest, True)
    _entry("display-only", None, False)
    with pytest.raises(ValidationError, match="latest"):
        _entry("display-only", latest, False)
    with pytest.raises(ValidationError, match="downloadable"):
        _entry("no-derivatives", None, True)
    with pytest.raises(ValidationError, match="latest"):
        _entry("open", None, True)


def test_registry_entries_of_this_slice_load():
    reg = load_registry(Paths.default())
    for sid in ("noaa-gml-trends", "hadcrut5", "ipcc-ar6-wg3-spm"):
        assert sid in reg.sources, reg.source_errors.get(sid)
    assert "ipcc-ar6-wg3-spm-c12" in reg.literature, reg.literature_errors
    ipcc = reg.sources["ipcc-ar6-wg3-spm"]
    assert ipcc.licence_class == "display-only" and not ipcc.obligations.mirror_raw


def test_display_only_source_cannot_mirror():
    src = load_registry(Paths.default()).sources["ipcc-ar6-wg3-spm"]
    data = src.model_dump(by_alias=True)
    data["obligations"]["mirror_raw"] = True
    with pytest.raises(ValidationError, match="mirror_raw"):
        type(src).model_validate(data)


def test_automatic_source_needs_urls():
    src = load_registry(Paths.default()).sources["hadcrut5"]
    data = src.model_dump(by_alias=True)
    data["artifacts"][0]["url"] = None
    with pytest.raises(ValidationError, match="url"):
        type(src).model_validate(data)

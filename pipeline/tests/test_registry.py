from __future__ import annotations

from datetime import date

import pytest

from envdash.models import Artifact
from envdash.paths import Paths
from envdash.registry import _coerce_nulls, _load_yaml, load_registry, render

from support import copy_sources


def test_one_broken_entry_does_not_stop_the_others(tmp_paths, tmp_path):
    paths = copy_sources(tmp_paths, tmp_path, "noaa-gml-trends", "hadcrut5")
    (paths.sources / "hadcrut5.yaml").rename(paths.sources / "hadcrut-renamed.yaml")
    reg = load_registry(paths)
    assert "noaa-gml-trends" in reg.sources
    assert "does not match the file name" in reg.source_errors["hadcrut-renamed"]


def test_unknown_placeholder_rejected(tmp_paths, tmp_path):
    paths = copy_sources(tmp_paths, tmp_path, "noaa-gml-trends")
    y = paths.sources / "noaa-gml-trends.yaml"
    y.write_text(y.read_text().replace("version {version}, doi", "version {release}, doi", 1))
    assert "unknown placeholders" in load_registry(paths).source_errors["noaa-gml-trends"]


def test_render_fills_every_placeholder_or_fails():
    t = "HadCRUT.{version} data were obtained on {date_accessed} and are © Met Office {year}"
    assert render(t, version="5.2.0.0", date_accessed=date(2026, 10, 4), year="2026") == (
        "HadCRUT.5.2.0.0 data were obtained on 2026-10-04 and are © Met Office 2026"
    )
    with pytest.raises(ValueError, match="year"):
        render(t, version="5.2.0.0", date_accessed=date(2026, 10, 4), year=None)


def test_hadcrut_credit_line_is_the_required_acknowledgement(tmp_paths):
    src = load_registry(tmp_paths).sources["hadcrut5"]
    line = render(src.obligations.attribution, version="5.2.0.0", date_accessed=date(2026, 10, 4), year="2026")
    required = src.evidence.licence_quote.split("used: ", 1)[1]
    filled = (
        required.replace("[version number]", "5.2.0.0")
        .replace("[date downloaded]", "2026-10-04")
        .replace("[year of first publication]", "2026")
    )
    assert " ".join(line.split()) == " ".join(filled.split())


# --- artifact_grids -----------------------------------------------------------------------------------------------


def test_cckp_grids_expand_into_ordinary_artifacts():
    """wb-cckp's three grids become 270 artifacts after the 25 written out (22 files of countries, the names workbook
    and two gridded climatologies), which stay first and unchanged; the validated source has no trace of the grids, so
    sources.json keeps its shape."""
    paths = Paths.default()
    src = load_registry(paths).sources["wb-cckp"]
    raw = _coerce_nulls(_load_yaml(paths.sources / "wb-cckp.yaml"))
    assert isinstance(raw, dict) and len(raw["artifact_grids"]) == 3
    written = [Artifact.model_validate(a) for a in raw["artifacts"]]
    assert src.artifacts[: len(written)] == written and len(written) == 25
    grid = src.artifacts[len(written) :]
    assert len(grid) == 6 * 3 + 6 * 4 * 3 * 3 + 4 * 3 * 3 == 270
    assert len({a.id for a in src.artifacts}) == len(src.artifacts) == 295
    assert len({str(a.url) for a in src.artifacts}) == 295
    by = {a.id: a for a in grid}
    a = by["cmip6-hd35-2040-2059-ssp245-median-subnat"]
    assert str(a.url) == (
        "https://cckpapi.worldbank.org/cckp/v1/cmip6-x0.25_climatology_hd35_climatology_annual_2040-2059_median_ssp245_"
        "ensemble_all_mean/all_countries_subnationals?_format=json"
    )
    assert (a.format, a.access.conditional, a.max_bytes) == ("json", False, 200_000_000)
    assert a.description.startswith("CMIP6 multi-model ensemble median, 2040–2059 under SSP2-4.5: hot days, the number")
    assert by["cmip6-cdd-1995-2014-historical-p90-subnat"].description.startswith(
        "CMIP6 multi-model ensemble 90th percentile, 1995–2014 reference period (historical runs): the longest run"
    )
    assert "cmip6-tas-anomaly-2080-2099-ssp585-p10-subnat" in by
    assert not any("1995-2014" in i for i in by if i.startswith("cmip6-tas-anomaly-"))
    assert "artifact_grids" not in src.model_dump() and not any("{" in a.id + str(a.url) for a in src.artifacts)


def _edit_cckp(tmp_paths, tmp_path, old: str, new: str, count: int = 1) -> str | None:
    paths = copy_sources(tmp_paths, tmp_path, "wb-cckp")
    y = paths.sources / "wb-cckp.yaml"
    text = y.read_text()
    assert old in text
    y.write_text(text.replace(old, new, count))
    reg = load_registry(paths)
    return reg.source_errors.get("wb-cckp")


def test_a_grid_id_missing_a_placeholder_is_refused(tmp_paths, tmp_path):
    err = _edit_cckp(tmp_paths, tmp_path, "-{scenario}-{statistic}-subnat", "-{scenario}-subnat")
    assert err is not None and "artifact_grids[0].id does not use ['statistic']" in err


def test_a_grid_template_naming_an_undeclared_placeholder_is_refused(tmp_paths, tmp_path):
    err = _edit_cckp(
        tmp_paths,
        tmp_path,
        "_{scenario}_ensemble_all_mean/all_countries_subnationals",
        "_{scenario}_{model}_mean/all_countries_subnationals",
    )
    assert err is not None and "unknown placeholders ['model']" in err


def test_grids_that_repeat_an_id_are_refused(tmp_paths, tmp_path):
    err = _edit_cckp(
        tmp_paths,
        tmp_path,
        "id: cmip6-tas-anomaly-{period}-{scenario}-{statistic}-subnat",
        "id: cmip6-hd35-{period}-{scenario}-{statistic}-subnat",
    )
    assert err is not None and "artifact id 'cmip6-hd35-2020-2039-ssp126-median-subnat' appears twice" in err


def test_a_grid_field_the_artifact_model_does_not_know_is_refused(tmp_paths, tmp_path):
    err = _edit_cckp(
        tmp_paths,
        tmp_path,
        "    format: json\n    description: >-\n      CMIP6 multi-model ensemble {",
        "    fromat: json\n    description: >-\n      CMIP6 multi-model ensemble {",
    )
    assert err is not None and "is invalid" in err and "fromat" in err


def test_a_value_without_a_label_is_refused(tmp_paths, tmp_path):
    err = _edit_cckp(tmp_paths, tmp_path, "        p90: 90th percentile\n", '        p90: ""\n')
    assert err is not None and "values.statistic.p90 needs a label" in err

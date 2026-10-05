from __future__ import annotations

from datetime import date

import pytest

from envdash.registry import load_registry, render

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

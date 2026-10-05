"""Published values quoted from web pages and JSON, checked against real snapshot slices."""

from __future__ import annotations

import shutil

import pytest
import yaml

from envdash import textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.literature import QuoteNotFound, verify_quote_in_document

from support import fixture, load_fixture_snapshot

# NOAA Coral Reef Watch status page (public domain), lines 290-345 of the snapshot of 2026-10-04. In the HTML the
# sentence runs over three source lines and uses a curly apostrophe (world’s).
CRW_QUOTE = (
    "From 1 January 2023 to 30 September 2025, bleaching-level heat stress has impacted ~84.4% of the world's coral "
    "reef area and mass coral bleaching has been documented in at least 83 countries and territories."
)


def _crw():
    path, meta = fixture("noaa-crw", "global-bleaching-status")
    return path.read_bytes(), meta


def test_quote_found_in_visible_text_of_real_page():
    data, meta = _crw()
    verify_quote_in_document(data, "text/html; charset=UTF-8", meta["url"], CRW_QUOTE)
    text = textmatch.document_text(data, "text/html; charset=UTF-8", meta["url"])
    assert "<div" not in text and "Reporting Coral Bleaching Data" not in text  # tags and comments are gone
    with pytest.raises(QuoteNotFound):
        verify_quote_in_document(data, "text/html", meta["url"], CRW_QUOTE.replace("84.4%", "84.5%"))
    # Text inside an HTML comment is not visible, so it cannot be quoted.
    with pytest.raises(QuoteNotFound):
        verify_quote_in_document(data, "text/html", meta["url"], "Reporting Coral Bleaching Data and Observations")


def test_quote_in_real_json_matches_raw_form_and_decoded_values():
    path, meta = fixture("gcp-fossil-co2-2025", "mtco2-metadata")
    data = path.read_bytes()
    text = textmatch.document_text(data, "text/plain; charset=utf-8", meta["url"])
    assert textmatch.contains(text, '"version": "2025v15"')  # the raw form, whitespace ignored
    assert textmatch.contains(text, "Fossil CO2 emissions from Flaring (includes vented methane)")
    assert textmatch.contains(text, "Licensed under Creative Commons Attribution 4.0 International")
    assert not textmatch.contains(text, "Licensed under Creative Commons Attribution-NonCommercial 4.0")


def _crw_entry(**changes) -> dict:
    entry = {
        "id": "crw-fourth-event-reef-area",
        "indicator_id": "coral.noaa-crw.fourth-event-reef-area",
        "source_id": "noaa-crw",
        "artifact_id": "global-bleaching-status",
        "title": "Reef area under bleaching-level heat stress in the fourth global bleaching event",
        "description": "Share of the world's coral reef area that experienced bleaching-level heat stress between 1 "
        "January 2023 and 30 September 2025, as published by NOAA Coral Reef Watch.",
        "unit": {"code": "percent", "label": "percent of the world's coral reef area", "short": "%"},
        "display": {"decimals": 1},
        "scope": {"geography": "World"},
        "geo_coverage": "global-only",
        "headline_entity": "WLD",
        "vintage": "Status update of 2 June 2026",
        "locator": "Current Global Bleaching: Status Update (updated June 2, 2026), first paragraph",
        "pdf_page": None,
        "quote": CRW_QUOTE,
        "value_text": "~84.4%",
        "value_reading": '"~84.4%" is published as 84.4 percent; the page gives no range.',
        "observations": [{"entity": "WLD", "period": "2023-01-01/2025-09-30", "value": "84.4"}],
        "checked_on": "2026-10-04",
        "research_ref": "docs/research/sources-impacts.json#NOAA Coral Reef Watch (CRW)",
    }
    entry.update(changes)
    return entry


def _write_entry(paths, entry: dict) -> None:
    (paths.literature / f"{entry['id']}.yaml").write_text(yaml.safe_dump(entry, sort_keys=False, allow_unicode=True))


def _with_crw_source(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / "noaa-crw.yaml", tmp_paths.sources / "noaa-crw.yaml")
    return tmp_paths


def test_html_literature_value_is_built_from_the_snapshot(tmp_paths):
    paths = _with_crw_source(tmp_paths)
    _write_entry(paths, _crw_entry())
    load_fixture_snapshot(paths, "noaa-crw", "global-bleaching-status")
    reg = load_registry(paths)
    assert reg.literature_errors == {}
    ts = [t for t in discover(paths) if t.spec.id == "coral.noaa-crw.fourth-event-reef-area"]
    report = build_and_export(paths, reg, ts)
    out = report.outcomes[0]
    assert out.state == "built", out.reason
    ind = out.indicator
    assert ind.kind == "published-value" and ind.latest.value == 84.4
    assert ind.published_value.quote == CRW_QUOTE
    assert "visible text of the snapshot" in ind.processing[0].description


def test_html_literature_value_with_a_wrong_quote_is_not_published(tmp_paths):
    paths = _with_crw_source(tmp_paths)
    _write_entry(paths, _crw_entry(quote=CRW_QUOTE.replace("83 countries", "84 countries")))
    load_fixture_snapshot(paths, "noaa-crw", "global-bleaching-status")
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id == "coral.noaa-crw.fourth-event-reef-area"]
    out = build_and_export(paths, reg, ts).outcomes[0]
    assert out.state == "failed" and "quote not found" in out.reason


def test_pdf_page_must_match_the_artifact_format(tmp_paths):
    paths = _with_crw_source(tmp_paths)
    _write_entry(paths, _crw_entry(pdf_page=1))
    errs = load_registry(paths).literature_errors
    assert "not a PDF: pdf_page must be null" in errs["crw-fourth-event-reef-area"]

    lit = yaml.safe_load((REPO_ROOT / "pipeline" / "literature" / "ipcc-ar6-wg3-spm-c12.yaml").read_text())
    lit["pdf_page"] = None
    _write_entry(paths, {**lit, "checked_on": str(lit["checked_on"])})
    errs = load_registry(paths).literature_errors
    assert "is a PDF: pdf_page is required" in errs["ipcc-ar6-wg3-spm-c12"]

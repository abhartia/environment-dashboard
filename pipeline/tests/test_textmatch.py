from __future__ import annotations

from envdash import textmatch
from envdash.registry import load_registry

from support import fixture


def test_licence_quote_found_in_real_csv_header(tmp_paths):
    """NOAA's terms are in the '#' header of its CSV, broken across lines with comment markers."""
    path, _ = fixture("noaa-gml-trends", "co2-mm-mlo")
    quote = load_registry(tmp_paths).sources["noaa-gml-trends"].evidence.licence_quote
    text = textmatch.document_text(path.read_bytes(), "text/csv", "https://gml.noaa.gov/x.csv")
    assert textmatch.contains(text, quote)
    assert not textmatch.contains(text, quote.replace("freely available", "available for a fee"))


def test_match_key_ignores_layout_not_content():
    assert textmatch.match_key("tCO₂-eq⁻¹") == textmatch.match_key("tCO2-eq–1")
    assert textmatch.match_key("miti-\ngation  ( high confidence)") == textmatch.match_key(
        "mitigation (high confidence)"
    )
    assert textmatch.match_key("at least half") != textmatch.match_key("at least a third")


def test_html_to_text():
    html = "<p>HadCRUT5 is provided under the <a href='x'>Open Government License v3</a>.</p><script>x()</script>"
    assert textmatch.contains(textmatch.html_to_text(html), "provided under the Open Government License v3.")

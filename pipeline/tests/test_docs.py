"""Documents generated from the registry, and the registry's credit-line placeholders."""

from __future__ import annotations

from datetime import date

import pytest

from envdash import docs
from envdash.paths import Paths
from envdash.registry import load_registry, long_date, render


def test_committed_licensing_md_matches_the_registry():
    paths = Paths.default()
    reg = load_registry(paths)
    assert docs.licensing_path(paths).read_text(encoding="utf-8") == docs.licensing_markdown(reg), (
        "run: uv run envdash docs licensing"
    )


def test_licensing_rows_follow_the_registry():
    reg = load_registry(Paths.default())
    md = docs.licensing_markdown(reg)
    cat = next(ln for ln in md.splitlines() if ln.startswith("| `cat-2025-thermometer` |"))
    assert "| no-derivatives | no | automatic |" in cat
    rows = [ln for ln in md.splitlines() if ln.startswith("| `")]
    assert len(rows) == len(reg.sources)
    counts = {c: sum(1 for s in reg.sources.values() if s.licence_class == c) for c in ("open", "no-derivatives")}
    footer = md.rstrip().splitlines()[-1]
    assert footer.startswith(f"{len(reg.sources)} sources: {counts['open']} open, ")
    assert f"{counts['no-derivatives']} no-derivatives" in footer


def test_long_access_date_placeholder():
    assert long_date(date(2026, 10, 4)) == "4 October 2026"
    assert render("Accessed on {date_accessed_long}.", version=None, date_accessed=date(2026, 10, 4), year=None) == (
        "Accessed on 4 October 2026."
    )
    with pytest.raises(ValueError, match="no value"):
        render("{date_accessed_long}", version=None, date_accessed=None, year=None)


def test_faostat_credit_uses_the_long_date_its_terms_ask_for():
    src = load_registry(Paths.default()).sources["faostat"]
    for text in (src.obligations.attribution, src.obligations.attribution_modified, src.citation.text):
        assert text is not None and "Accessed on {date_accessed_long}." in text
    line = render(src.obligations.attribution, version=None, date_accessed=date(2026, 10, 4), year="2025")
    assert line.startswith("FAO. 2025. FAOSTAT. Accessed on 4 October 2026. https://www.fao.org/faostat/en/#data")

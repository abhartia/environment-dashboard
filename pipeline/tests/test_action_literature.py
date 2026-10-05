"""Published values quoted from the World Bank carbon pricing report and the ICCT car life-cycle report
(pipeline/literature/wb-carbon-pricing-2026-*.yaml, icct-lca-2025-*.yaml, built by envdash/transforms/literature.py).

The registry entries load without the snapshots; finding each quote on its page needs the full PDFs from the local
cache and is marked `snapshot`.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transforms.literature import verify_quote

ENTRIES = {
    "wb-carbon-pricing-2026-coverage": ("carbon-pricing.wb-2026.emissions-covered", "WLD", "2026", 29.0),
    "wb-carbon-pricing-2026-revenue": ("carbon-pricing.wb-2026.revenue", "WLD", "2025", 107.0),
    "icct-lca-2025-bev": ("cars.icct-2025.lifecycle-bev-eu", "EU27", "2025", 63.0),
    "icct-lca-2025-gasoline": ("cars.icct-2025.lifecycle-gasoline-eu", "EU27", "2025", 235.0),
}


@pytest.mark.parametrize("lid", sorted(ENTRIES))
def test_entry_loads_with_its_value(lid):
    lit = load_registry(Paths.default()).literature[lid]
    indicator, entity, period, value = ENTRIES[lid]
    assert lit.indicator_id == indicator
    assert [(o.entity, o.period, o.value) for o in lit.observations] == [(entity, period, value)]
    assert lit.value_text in lit.quote


@pytest.mark.snapshot
@pytest.mark.parametrize("lid", sorted(ENTRIES))
def test_quote_is_on_its_page(lid):
    p = Paths.default()
    lit = load_registry(p).literature[lid]
    sha = snapshots.read_current(p)[f"{lit.source_id}/{lit.artifact_id}"]
    assert lit.pdf_page is not None
    verify_quote(snapshots.cache_path(p, sha).read_bytes(), lit.pdf_page, lit.quote)

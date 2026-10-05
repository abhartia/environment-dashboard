"""Global Carbon Budget 2025: the global budget transforms (on the real v1.0 workbook) and the quoted ESSD values.

The fixture tests/fixtures/gcb-2025-global/a928cf06c575.xlsx is the whole workbook (an xlsx is a zip archive, so no
line slice of it is a readable workbook); its sidecar records that the fixture sha256 equals the snapshot's.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from decimal import Decimal

import pytest

from envdash import snapshots, textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover
from envdash.transforms.emissions.gcb_global import (
    COLUMNS,
    GcbFormatError,
    budget_observations,
    fossil_net_observations,
    largest_imbalance_residual,
    read_budget,
    total_observations,
)
from envdash.transforms.literature import verify_quote
from envdash.validate import validate_all

from support import fixture, load_fixture_snapshot

IDS = (
    "emissions.gcb-2025.budget-global",
    "emissions.gcb-2025.fossil-net-global",
    "emissions.gcb-2025.total-co2-global",
)
LITERATURE = ("gcb-2025-essd-fossil-2025", "gcb-2025-essd-fossil-growth-2025", "gcb-2025-essd-remaining-budget-1-5c")


def _rows():
    path, _ = fixture("gcb-2025-global", "global-budget")
    return read_budget(path.read_bytes())


def _by_period(obs, **dims):
    return {o.period: o for o in obs if o.dims == dims}


def test_reads_every_year_of_the_budget():
    rows = _rows()
    assert [r.year for r in rows] == list(range(1959, 2025))
    # 2024 in GtC/yr as stored (also reported by the research verifier, docs/research/sources-emissions.json).
    v = rows[-1].values
    assert round(v[COLUMNS[1]], 4) == Decimal("10.5345")
    assert round(v[COLUMNS[2]], 4) == Decimal("1.2515")
    assert round(v[COLUMNS[3]], 4) == Decimal("7.9225")
    assert round(v[COLUMNS[4]], 4) == Decimal("3.3889")
    assert round(v[COLUMNS[5]], 4) == Decimal("1.9422")
    assert round(v[COLUMNS[6]], 4) == Decimal("0.2243")


def test_imbalance_identity_holds_and_fixes_the_fossil_basis():
    rows = _rows()
    assert largest_imbalance_residual(rows) < Decimal("1e-12")
    # If the fossil column were already net of the carbonation sink, the sheet's imbalance definition would not hold.
    net = [
        dataclasses.replace(r, values={**r.values, COLUMNS[1]: r.values[COLUMNS[1]] - r.values[COLUMNS[6]]})
        for r in rows
    ]
    with pytest.raises(GcbFormatError, match="budget imbalance"):
        largest_imbalance_residual(net)


def test_abstract_values_in_gtc():
    """The ESSD abstract's 2024 values (GtC/yr, one decimal) against the sheet, as a regression test."""
    v = _rows()[-1].values
    assert round(v[COLUMNS[1]] - v[COLUMNS[6]], 1) == Decimal("10.3")  # fossil, including the carbonation sink
    assert round(v[COLUMNS[2]], 1) == Decimal("1.3")  # ELUC
    assert round(v[COLUMNS[3]], 1) == Decimal("7.9")  # GATM
    assert round(v[COLUMNS[4]], 1) == Decimal("3.4")  # SOCEAN
    assert round(v[COLUMNS[5]], 1) == Decimal("1.9")  # SLAND
    assert round(v[COLUMNS[7]], 1) == Decimal("-1.7")  # BIM


def test_converted_with_the_sheet_factor():
    rows = _rows()
    budget = budget_observations(rows)
    assert len(budget) == 7 * 66
    fossil = _by_period(budget, component="fossil")
    luc = _by_period(budget, component="land-use-change")
    ocean = _by_period(budget, component="ocean-sink")
    g = rows[-1].values
    assert fossil["2024"].value == float(Decimal(repr(float(g[COLUMNS[1]]))) * Decimal("3.664"))
    # Gross fossil 2024 = 38.6 GtCO2, the same as the national file's World total (10,534.546 MtC x 3.664).
    assert round(fossil["2024"].value, 1) == 38.6
    assert fossil["2024"].interval == "1sigma"
    assert fossil["2024"].lower == pytest.approx(fossil["2024"].value * 0.95, rel=1e-12)
    assert fossil["2024"].upper == pytest.approx(fossil["2024"].value * 1.05, rel=1e-12)
    assert luc["2024"].upper - luc["2024"].lower == pytest.approx(2 * 0.7 * 3.664, abs=1e-12)
    assert ocean["2024"].lower is None and ocean["2024"].interval is None
    assert _by_period(budget, component="budget-imbalance")["2024"].value < 0


def test_headline_net_and_total():
    rows = _rows()
    net = _by_period(fossil_net_observations(rows))
    total = _by_period(total_observations(rows))
    # ESSD executive summary: 37.8 GtCO2 fossil (including the carbonation sink) and 42.4 GtCO2 total in 2024.
    assert round(net["2024"].value, 1) == 37.8
    assert round(total["2024"].value, 1) == 42.4
    assert round(net["2024"].value, 3) == 37.777
    assert round(total["2024"].value, 3) == 42.362
    assert set(net) == set(total) == {str(y) for y in range(1959, 2025)}


def _gcb_paths(tmp_paths: Paths) -> Paths:
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / "gcb-2025-global.yaml", tmp_paths.sources)
    return tmp_paths


def test_build_exports_three_valid_indicators_with_passing_checks(tmp_paths):
    paths = _gcb_paths(tmp_paths)
    load_fixture_snapshot(paths, "gcb-2025-global", "global-budget")
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id in IDS]
    assert sorted(t.spec.id for t in ts) == sorted(IDS)
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"] * 3, [o.reason for o in report.outcomes]
    checks = [c for o in report.outcomes for c in o.checks]
    assert [c.status for c in checks] == ["pass", "pass"]
    net = json.loads((paths.public_indicators / "emissions.gcb-2025.fossil-net-global.json").read_text())
    assert net["vintage"] == "2025 v1.0"
    assert net["latest"]["period"] == "2024"
    assert any("3.664" in p["description"] for p in net["processing"])
    assert "Changes: cement carbonation sink subtracted" in net["attribution"]
    budget = json.loads((paths.public_indicators / "emissions.gcb-2025.budget-global.json").read_text())
    assert budget["latest"]["dims"] == {"component": "fossil"}
    assert [v["id"] for v in budget["dimensions"][0]["values"]] == [
        "fossil",
        "land-use-change",
        "atmospheric-growth",
        "ocean-sink",
        "land-sink",
        "cement-carbonation-sink",
        "budget-imbalance",
    ]
    assert validate_all(paths, reg) == []


def test_unpinned_object_is_refused(tmp_paths):
    paths = _gcb_paths(tmp_paths)
    sha = load_fixture_snapshot(paths, "gcb-2025-global", "global-budget")
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    (t,) = [t for t in discover(paths) if t.spec.id == IDS[1]]
    key = snapshots.key("gcb-2025-global", "global-budget")
    t.run({key: InputFile(snapshots.cache_path(paths, sha), snap)})  # the pinned object builds
    other = snap.model_copy(update={"url": "https://data.icos-cp.eu/objects/AnotherObjectId"})
    with pytest.raises(GcbFormatError, match="not a pinned"):
        t.run({key: InputFile(snapshots.cache_path(paths, sha), other)})


def test_literature_entries_load_and_state_their_values():
    reg = load_registry(Paths.default())
    for lid in LITERATURE:
        assert lid not in reg.literature_errors, reg.literature_errors.get(lid)
        lit = reg.literature[lid]
        assert lit.source_id == "gcb-2025-essd" and lit.pdf_page == 5
        assert lit.value_text in lit.quote
    vals = {lid: reg.literature[lid].observations[0] for lid in LITERATURE}
    assert (vals[LITERATURE[0]].period, vals[LITERATURE[0]].value) == ("2025", 38.1)
    assert (vals[LITERATURE[1]].period, vals[LITERATURE[1]].value) == ("2025", 1.0)
    assert (vals[LITERATURE[2]].period, vals[LITERATURE[2]].value) == ("2026-01-01", 170.0)
    assert reg.sources["gcb-2025-essd"].licence_class == "open"


@pytest.mark.snapshot
def test_quotes_and_publisher_checks_are_in_the_essd_pdf():
    paths = Paths.default()
    reg = load_registry(paths)
    sha = snapshots.read_current(paths)[snapshots.key("gcb-2025-essd", "article-pdf")]
    pdf = snapshots.cache_path(paths, sha).read_bytes()
    for lid in LITERATURE:
        verify_quote(pdf, reg.literature[lid].pdf_page, reg.literature[lid].quote)
    page5 = textmatch.pdf_pages_text(pdf)[4]
    for t in discover(paths):
        for c in t.checks if t.spec.id in IDS else ():
            assert textmatch.contains(page5, c.quote), c.quote

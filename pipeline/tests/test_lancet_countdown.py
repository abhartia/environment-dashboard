"""Lancet Countdown 2025 transforms (envdash/transforms/impacts/lancet_countdown.py).

The source is CC BY-NC-SA 4.0 (class noncommercial). Committed fixtures are cut only from open-class sources
(AGENTS.md rule 9; tests/fixtures/make_fixture.py refuses other classes), so the value tests below read the full
real workbooks from the snapshot cache and are marked `snapshot` (run with `uv run pytest -m snapshot`). The
key-finding sentences are compared with the same workbook's own Global sheet, i.e. the producer's statement for the
same vintage.
"""

from __future__ import annotations

import io
from decimal import ROUND_HALF_UP, Decimal

import openpyxl
import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transforms.impacts import lancet_countdown as lc

# openpyxl warns that it drops drawing shapes when it re-saves a workbook (the refusal tests below); values are kept.
pytestmark = pytest.mark.filterwarnings("ignore:DrawingML support is incomplete:UserWarning")

SOURCE = "lancet-countdown-2025"
IDS = {
    "heat.lancet-2025.deaths-global",
    "heat.lancet-2025.labour-hours-global",
    "heat.lancet-2025.heatwave-days-global",
}


def _current_bytes(source_id: str, artifact_id: str) -> bytes:
    # Copied from tests/test_snapshot_golden.py.
    p = Paths.default()
    return snapshots.cache_path(p, snapshots.read_current(p)[f"{source_id}/{artifact_id}"]).read_bytes()


def _replaced(raw: bytes, sheet: str, row_with: str, old, new) -> bytes:
    """The real workbook with one cell changed, to show that a changed file is refused: in the one row of `sheet`
    containing the text `row_with`, the cell holding `old` is set to `new`."""
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    rows = [r for r in wb[sheet].iter_rows() if any(c.value == row_with for c in r)]
    assert len(rows) == 1, f"{len(rows)} rows of {sheet!r} contain {row_with!r}"
    cells = [c for c in rows[0] if c.value == old]
    assert len(cells) == 1
    cells[0].value = new
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _round(x: Decimal, places: str) -> Decimal:
    return x.quantize(Decimal(places), rounding=ROUND_HALF_UP)


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_transforms_declare_registered_inputs():
    paths = Paths.default()
    ts = {t.spec.id: t for t in lc.transforms(paths)}
    assert set(ts) == IDS
    src = load_registry(paths).sources[SOURCE]
    artifacts = {a.id for a in src.artifacts}
    for t in ts.values():
        assert [i.source_id for i in t.inputs] == [SOURCE]
        assert {i.artifact_id for i in t.inputs} <= artifacts
    # The registry notice carries the Copernicus (ERA5) acknowledgement every one of these indicators needs.
    assert src.obligations.notice and "Copernicus Climate Change Service information {year}" in src.obligations.notice
    check = ts["heat.lancet-2025.labour-hours-global"].checks[0]
    assert check.vintage == lc.VINTAGE and check.stated == "640" and check.tolerance == 0.5
    assert check.url == str(next(a.url for a in src.artifacts if a.id == lc.WORK_HOURS.artifact_id))


# --- full real workbooks (snapshot cache) -------------------------------------------------------------------------


@pytest.mark.snapshot
def test_deaths_and_the_key_finding():
    raw = _current_bytes(SOURCE, lc.MORTALITY.artifact_id)
    obs, g = lc.parse_mortality(raw)
    assert g.report_year == 2025 and g.published.isoformat() == "2025-10-29"
    by = {o.period: o.value for o in obs}
    assert len(obs) == 32 and obs[0].period == "1990" and obs[-1].period == "2021"
    assert by["2021"] == 558304 and by["1990"] == 260952
    assert g.key_finding == (
        "In 2012-2021, global heat-related mortality reached an estimated average 546,000 deaths annually, up 63.2% "
        "from 335,000 in 1990-1999"
    )
    early = sum(Decimal(int(by[str(y)])) for y in range(1990, 2000)) / 10
    late = sum(Decimal(int(by[str(y)])) for y in range(2012, 2022)) / 10
    assert early == Decimal("334690.3")
    assert _round(early, "1E3") == Decimal("335000")  # matches "335,000 in 1990-1999"
    # The same workbook's annual values do not reproduce the other two figures of its key finding: the 2012-2021
    # mean is 545,478.4 (545,000 to the nearest thousand, not 546,000) and the rise is 62.98%, not 63.2%. The WHO,
    # Lancet Countdown region and HDI sheets sum to the same means. Recorded here, not adjusted.
    assert late == Decimal("545478.4")
    assert _round(late, "1E3") == Decimal("545000")
    assert _round((late / early - 1) * 100, "0.01") == Decimal("62.98")


@pytest.mark.snapshot
def test_work_hours_and_the_key_finding():
    raw = _current_bytes(SOURCE, lc.WORK_HOURS.artifact_id)
    obs, g = lc.parse_work_hours(raw)
    assert len(obs) == 5 * 35
    total = {o.period: Decimal(repr(o.value)) for o in obs if o.dims == {"sector": "total"}}
    assert g.key_finding == (
        "A record-high 640 billion potential work hours were lost in 2024, a 98% increase compared to the 1990–99 "
        "annual average."
    )
    assert _round(total["2024"], "1") == Decimal("640")
    assert total["2024"] == max(total.values())  # "record-high"
    base = sum(total[str(y)] for y in range(1990, 2000)) / 10
    assert _round((total["2024"] / base - 1) * 100, "1") == Decimal("98")
    # TotalSunAgCon 639855005.6499999 thousand hours in the Global sheet.
    assert total["2024"] == Decimal("639.85500565")
    sectors = {o.dims["sector"]: o.value for o in obs if o.period == "2024"}
    assert sum(v for k, v in sectors.items() if k != "total") == pytest.approx(sectors["total"], rel=1e-12)


@pytest.mark.snapshot
def test_heatwave_days_and_the_key_finding():
    raw = _current_bytes(SOURCE, lc.HEATWAVE.artifact_id)
    obs, g = lc.parse_heatwave(raw)
    assert len(obs) == 15
    by = {(o.dims["scenario"], o.period): Decimal(repr(o.value)) for o in obs}
    assert by[("observed", "2024")] == Decimal("30.7905888162652")
    assert by[("attributable", "2020")] == Decimal("14.2293997022799")
    assert g.key_finding.startswith(
        "Globally, 84% of the heatwave days that people were exposed to on average annually in 2020-2024, would have "
        "not been expected to occur without climate change."
    )
    years = [str(y) for y in range(2020, 2025)]
    share = sum(by[("attributable", y)] for y in years) / sum(by[("observed", y)] for y in years)
    assert _round(share * 100, "1") == Decimal("84")


@pytest.mark.snapshot
def test_a_different_report_year_is_refused():
    raw = _current_bytes(SOURCE, lc.MORTALITY.artifact_id)
    report = "The 2025 report of the Lancet Countdown on health and climate change"
    edited = _replaced(raw, "DATA GUIDANCE", report, report, report.replace("2025", "2026"))
    with pytest.raises(lc.LancetFormatError, match="2026 report"):
        lc.parse_mortality(edited)


@pytest.mark.snapshot
def test_a_changed_unit_is_refused():
    raw = _current_bytes(SOURCE, lc.WORK_HOURS.artifact_id)
    edited = _replaced(raw, "DATA GUIDANCE", "TotalsunAgCon", "Hours in 1000s", "Hours")
    with pytest.raises(lc.LancetFormatError, match="TotalsunAgCon"):
        lc.parse_work_hours(edited)


@pytest.mark.snapshot
def test_inconsistent_heatwave_row_is_refused():
    raw = _current_bytes(SOURCE, lc.HEATWAVE.artifact_id)
    # One more observed day in 2020 breaks Observed = Counterfactual + Attributable_to_CC.
    edited = _replaced(raw, lc.HEATWAVE_SHEET, 2020, 16.1167785054611, 17.1167785054611)
    with pytest.raises(lc.LancetFormatError, match="2020 Observed"):
        lc.parse_heatwave(edited)

"""IRENA renewable capacity (energy/irena_capacity.py) and generation costs (energy/irena_costs.py).

Neither source has a fixture: the capacity statistics are a 1.7 MB PDF that cannot be cut into a byte-exact slice
that is still a PDF, and the cost data file's registry entry does not allow re-hosting the raw file
(mirror_raw: false, because two sheets are based on BNEF data). Their parsing is tested against the real snapshots
(-m snapshot, which needs pipeline/.snapshots populated by envdash fetch).
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, discover, run_checks, validate
from envdash.transforms.energy import irena_capacity as cap
from envdash.transforms.energy import irena_costs as costs

CAP_IDS = (
    "capacity.irena.renewables-world",
    "capacity.irena.renewables-by-technology-world",
    "capacity.irena.renewable-share-world",
)
LCOE_ID = "lcoe.irena.by-technology-world"


def test_specs():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    for tid in CAP_IDS:
        assert ts[tid].inputs == (cap.PDF, cap.HIGHLIGHTS)
        assert ts[tid].spec.geo_coverage == "global-only"
    assert ts[CAP_IDS[0]].spec.unit.code == "GW"
    assert [v.id for v in ts[CAP_IDS[1]].spec.dimensions[0].values] == [
        "hydropower",
        "marine",
        "onshore-wind",
        "offshore-wind",
        "solar-pv",
        "csp",
        "bioenergy",
        "geothermal",
    ]
    t = ts[LCOE_ID]
    assert t.inputs == (costs.DATA, costs.SUMMARY)
    assert t.spec.unit.code == "USD2025/MWh" and dict(t.spec.headline_dims) == {"technology": "solar-pv"}
    assert {c.vintage for c in t.checks} == {costs.VINTAGE}


def test_capacity_checks_quote_the_highlights():
    for c in (*cap.CHECKS_TOTAL, *cap.CHECKS_TECH, *cap.CHECKS_SHARE):
        assert c.url == cap.HIGHLIGHTS_URL and c.stated.replace(".", "") in c.quote.replace(" ", "").replace(".", "")


# --- full snapshot ------------------------------------------------------------------------------------------------


def _files(*inputs) -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in inputs:
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, cur[i.key]), snap)
    return out


@pytest.mark.snapshot
def test_capacity_world_rows_and_sums():
    files = _files(cap.PDF)
    rows = cap.world_rows(list(cap._layout_pages(files[cap.PDF.key].path)))
    cap.check_sums(rows)
    # Page 14, "Total renewable energy", World: 2 020 792 (2016) ... 5 149 280 (2025).
    assert rows[cap.TOTAL].page == 14
    assert rows[cap.TOTAL].values["2016"] == 2020792 and rows[cap.TOTAL].values["2025"] == 5149280
    assert rows["Pumped hydro"].values["2025"] == 159822
    assert rows["Solar photovoltaic"].values["2025"] == 2383162
    assert str(rows[cap.SHARE].values["2025"]) == "49.4"


@pytest.mark.snapshot
def test_capacity_refuses_a_total_that_is_not_the_sum():
    rows = cap.world_rows(list(cap._layout_pages(_files(cap.PDF)[cap.PDF.key].path)))
    bad = dict(rows)
    tot = rows[cap.TOTAL]
    bad[cap.TOTAL] = cap.WorldRow(tot.title, tot.page, {**tot.values, "2025": tot.values["2025"] + 10})
    with pytest.raises(cap.IrenaFormatError, match="Total renewable energy 2025"):
        cap.check_sums(bad)


@pytest.mark.snapshot
def test_capacity_transforms_and_publisher_checks():
    files = _files(cap.PDF, cap.HIGHLIGHTS)
    ts = {t.spec.id: t for t in discover(Paths.default())}
    for tid in CAP_IDS:
        t = ts[tid]
        res = t.run(files)
        validate(t, res.observations)
        assert res.vintage == cap.VINTAGE
        outcomes = run_checks(t, {cap.SOURCE: res.vintage}, res.observations)
        assert outcomes and {o.status for o in outcomes} == {"pass"}
    res = ts[CAP_IDS[0]].run(files)
    assert {o.period: o.value for o in res.observations}["2025"] == 5149.28
    assert res.changes == "converted from megawatts to gigawatts."


@pytest.mark.snapshot
def test_costs_reads_figure_s2_and_never_a_third_party_sheet():
    w = costs.read_workbook(_files(costs.DATA)[costs.DATA.key].path)
    costs.check_workbook(w)
    assert w.third_party == {
        "Fig. 9.5": "Based on BNEF data",
        "Fig. 9.7": "Based on BNEF data",
        "Fig. 9.8": "Based on Carbon Limiting Technologies",
    }
    # Sheet "Fig S.2": Solar photovoltaic 2010 and 2025, Onshore wind 2025; geothermal 2011 is empty.
    assert float(w.lcoe["Solar photovoltaic"][2010]) == 407.7145886667587
    assert float(w.lcoe["Solar photovoltaic"][2025]) == 43.5389566578384
    assert float(w.lcoe["Onshore wind"][2025]) == 32.949986439398714
    assert w.lcoe["Geothermal"][2011] is None
    assert w.whole == [("Solar photovoltaic", 2024)]


@pytest.mark.snapshot
def test_costs_refuses_a_summary_that_disagrees():
    w = costs.read_workbook(_files(costs.DATA)[costs.DATA.key].path)
    bad = costs.Workbook(
        w.lcoe, w.whole, {**w.summary_2025, "Bioenergy": w.summary_2025["Bioenergy"] + 1}, w.third_party, w.cited
    )
    with pytest.raises(costs.IrenaCostsFormatError, match="Bioenergy"):
        costs.check_workbook(bad)
    labelled = costs.Workbook(w.lcoe, w.whole, w.summary_2025, {**w.third_party, costs.SHEET: "Based on X"}, w.cited)
    with pytest.raises(costs.IrenaCostsFormatError, match="labelled"):
        costs.check_workbook(labelled)


@pytest.mark.snapshot
def test_costs_transform_and_publisher_checks():
    files = _files(costs.DATA, costs.SUMMARY)
    t = next(t for t in discover(Paths.default()) if t.spec.id == LCOE_ID)
    res = t.run(files)
    validate(t, res.observations)
    assert res.vintage == "2026-07-02" and res.changes is None
    outcomes = run_checks(t, {costs.SOURCE: res.vintage}, res.observations)
    assert len(outcomes) == 7 and {o.status for o in outcomes} == {"pass"}
    geo_2011 = next(o for o in res.observations if o.dims["technology"] == "geothermal" and o.period == "2011")
    assert geo_2011.value is None and geo_2011.missing_reason

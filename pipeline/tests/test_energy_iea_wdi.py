"""IEA EV sales share (energy/iea_evs.py) and World Bank access to electricity (energy/wdi_access.py).

No fixtures: the IEA file may not be re-hosted (mirror_raw: false, its car price rows are S&P Global Mobility data),
and the WDI response is a single 3 MB JSON line, which a line slice cannot cut. Their parsing is tested against the
real snapshots (-m snapshot, which needs pipeline/.snapshots populated by envdash fetch).
"""

from __future__ import annotations

import pytest

from envdash import geo, snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, discover, run_checks, validate
from envdash.transforms.energy import iea_evs as iea
from envdash.transforms.energy import wdi_access as wdi


def test_specs():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    ev = ts["ev.iea.sales-share"]
    assert ev.inputs == (iea.EVS, iea.REPORT) and dict(ev.spec.headline_dims) == {"mode": "cars"}
    assert ev.spec.geo_coverage == "country"
    acc = ts["access.wb-wdi.electricity"]
    assert acc.inputs == (wdi.ACCESS, wdi.COUNTRIES) and acc.spec.unit.label == "percent of population"


def test_single_precision_values_are_written_shortest():
    # Values as stored in the IEA file (World cars 2010 and 2025, United Arab Emirates cars 2012).
    assert str(iea.shortest_single("0.012000000104308128")) == "0.012"
    assert str(iea.shortest_single("25")) == "25"
    assert str(iea.shortest_single("0.06499999761581421")) == "0.065"
    with pytest.raises(iea.IeaFormatError, match="not a single-precision number"):
        iea.shortest_single("0.1")


def test_region_names_resolve_explicitly():
    assert iea.entity_of("Korea") == "KOR" and iea.entity_of("USA") == "USA" and iea.entity_of("China") == "CHN"
    assert iea.entity_of("European Union") is None
    with pytest.raises(geo.UnknownEntity):
        iea.entity_of("Rest of Europe")
    assert wdi.entity_of("XKX", "Kosovo") == "KOS" and wdi.entity_of("CHI", "Channel Islands") is None


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
def test_ev_sales_share_full_run():
    files = _files(iea.EVS, iea.REPORT)
    t = next(t for t in discover(Paths.default()) if t.spec.id == "ev.iea.sales-share")
    res = t.run(files)
    validate(t, res.observations)
    by = {(o.entity, o.dims["mode"], o.period): o for o in res.observations}
    assert by[("WLD", "cars", "2025")].value == 25 and by[("WLD", "cars", "2010")].value == 0.012
    assert by[("NOR", "cars", "2025")].value is not None
    # The United Arab Emirates' van shares of 200% to 310% are withheld, not published.
    assert [k for k, o in by.items() if o.value is None] == [("ARE", "vans", y) for y in map(str, range(2021, 2026))]
    assert "310%" in (by[("ARE", "vans", "2023")].missing_reason or "")
    assert res.vintage == iea.VINTAGE and res.changes  # an adaptation: the IEA derived-work disclaimer applies
    assert "26,007 car price rows" in res.steps[1]
    outcomes = run_checks(t, {iea.SOURCE: res.vintage}, res.observations)
    assert [o.status for o in outcomes] == ["pass"]


@pytest.mark.snapshot
def test_ev_never_reads_price_rows():
    df = iea.read_table(_files(iea.EVS)[iea.EVS.key].path.read_bytes())
    rows = iea.sales_share_rows(df)
    assert set(rows["parameter"].unique()) == {iea.PARAMETER}
    assert iea.third_party_count(df) == 26007


@pytest.mark.snapshot
def test_access_to_electricity_full_run():
    files = _files(wdi.ACCESS, wdi.COUNTRIES)
    t = next(t for t in discover(Paths.default()) if t.spec.id == "access.wb-wdi.electricity")
    res = t.run(files)
    validate(t, res.observations)
    by = {(o.entity, o.period): o.value for o in res.observations}
    # api.worldbank.org EG.ELC.ACCS.ZS, countryiso3code WLD, date 2024.
    assert by[("WLD", "2024")] == 91.9264843853681
    assert min(p for e, p in by if e == "WLD") == "1998"
    assert res.vintage == "2026-07-13"
    assert "Channel Islands" in res.steps[1]

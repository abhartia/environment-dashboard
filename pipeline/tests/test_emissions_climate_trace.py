"""Climate TRACE V5.10.0 (climate-trace): emissions by subsector, grouped into Gates's five activities, and their
shares.

Fixtures are byte-exact slices of the real snapshots (tests/fixtures/climate-trace/, cut with make_fixture.py
--first 24 --last 12): the header and the rows of the first two codes (ABW, AFG) and the last one (ZWE), 2015-2026,
of every artifact the transform reads. The fixture tests run the real reading, checks, grouping and share code on
those three codes (expected_codes=3); the world values they form are sums of three codes only, so the world totals
of the real release are pinned in the snapshot-marked tests, which read the full snapshots from the local cache.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from envdash import geo, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.emissions import climate_trace as ct

from support import fixture

IDS = {
    "ghg.climate-trace.by-subsector",
    "ghg.climate-trace.by-activity",
    "ghg.climate-trace.by-activity-share",
    "ghg.climate-trace.five-activities-total",
}
EDGAR = {
    "other-energy-use",
    "railways",
    "other-transport",
    "other-onsite-fuel-usage",
    "other-solid-fuels",
    "other-fossil-fuel-operations",
    "solid-waste-disposal",
    "biological-treatment-of-solid-waste-and-biogenic",
    "incineration-and-open-burning-of-waste",
    "cropland-fires",
}


def _sub(slug: str) -> ct.Sub:
    return next(s for s in ct.MAPPING if s.slug == slug)


def _fixture_bytes(sub: ct.Sub) -> dict[str, bytes]:
    return {g: fixture(ct.SOURCE, sub.artifact(g))[0].read_bytes() for g in sub.gases}


def _series(slug: str) -> ct.SubSeries:
    sub = _sub(slug)
    return ct.subsector_series(sub, _fixture_bytes(sub), expected_codes=3)


@pytest.fixture(scope="module")
def all_series() -> tuple[ct.SubSeries, ...]:
    return tuple(ct.subsector_series(s, _fixture_bytes(s), expected_codes=3) for s in ct.MAPPING)


# --- registry and mapping (no data) --------------------------------------------------------------------------------


def test_registry_entry_is_open_and_never_registers_iea_edgar_co2():
    src = load_registry(Paths.default()).sources[ct.SOURCE]
    assert src.licence_class == "open" and src.licence.spdx == "CC-BY-4.0"
    assert str(src.evidence.terms_url) == "https://climatetrace.org/terms"
    assert "with the exception of external datasets listed below" in src.evidence.licence_quote
    arts = {a.id: a for a in src.artifacts}
    expected = {(s.artifact(g), s.member(g), s.zip_name) for s in ct.MAPPING for g in s.gases}
    assert {(a.id, a.zip_member, str(a.url).split("/files/")[1].removesuffix("/content")) for a in arts.values()} == {
        (i, m, z) for i, m, z in expected
    }
    for a in arts.values():
        assert str(a.url).startswith(f"https://zenodo.org/api/records/{ct.ZENODO_RECORD}/files/")
        assert a.zip_member.endswith(f"_country_emissions_{ct.FILE_VERSION}.csv")
        # The carbon dioxide of an EDGAR subsector (IEA-EDGAR CO2) is never fetched, nor any co2 file at all.
        assert not a.zip_member.startswith("co2/")
        slug = a.zip_member.split("/DATA/")[1].removesuffix(f"_country_emissions_{ct.FILE_VERSION}.csv")
        assert slug not in ct.EXCLUDED
        if slug in EDGAR:
            assert a.zip_member.split("/")[0] in ("ch4", "n2o")


def test_mapping_covers_every_subsector_once():
    slugs = [s.slug for s in ct.MAPPING]
    assert len(slugs) == len(set(slugs)) == 68
    # Zenodo record 22919723 has 69 subsector zips: these 68 and other-manufacturing.
    assert set(ct.EXCLUDED) == {"other-manufacturing"}
    assert {s.slug for s in ct.MAPPING if s.basis == "edgar-non-co2"} == EDGAR
    assert all((s.gwp_ch4 is not None) == (s.basis == "edgar-non-co2") for s in ct.MAPPING)
    assert {s.group for s in ct.MAPPING} == set(ct.GROUPS)
    assert all(s.reason.endswith(".") for s in ct.MAPPING)
    # Rhodium's grouping: fuel supply under making things, waste with growing things, F-gases with buildings,
    # forest fires and natural uptake outside the five.
    assert _sub("oil-and-gas-production").group == "making-things"
    assert _sub("solid-waste-disposal").group == "growing-things"
    assert _sub("fluorinated-gases").group == "keeping-warm-and-cool"
    assert _sub("forest-land-fires").group == "wildfires"
    assert _sub("removals").group == "land-uptake"
    assert _sub("forest-land-clearing").group == "growing-things"


def test_every_indicator_is_declared_with_its_scope():
    ts = ct.transforms(Paths.default())
    assert {t.spec.id for t in ts} == IDS
    for t in ts:
        assert {i.source_id for i in t.inputs} == {ct.SOURCE}
        assert len(t.inputs) == 78
        sc = t.spec.scope
        assert (sc.gwp, sc.lulucf, sc.bunkers) == ("AR6-GWP100", "included", "included")
        assert "IEA-EDGAR CO2" in sc.basis and "World Energy Balances" in sc.basis


def test_climate_trace_codes():
    assert geo.resolve("XKX", ct.SOURCE) == "KOS"
    assert geo.resolve("ZNC", ct.SOURCE) == "CYN"
    assert ct.entity_of("UNK") is None
    with pytest.raises(geo.UnknownEntity):
        geo.resolve("UNK", ct.SOURCE)


# --- fixtures: real rows of three codes ----------------------------------------------------------------------------


def test_reads_and_checks_a_country_file():
    sub = _sub("electricity-generation")
    f = ct.read_country_file(_fixture_bytes(sub)[ct.CO2E], sub, ct.CO2E, expected_codes=3)
    assert f.codes == {"ABW", "AFG", "ZWE"}
    assert len(f.values) == 36
    with pytest.raises(ct.ClimateTraceError, match="codes"):
        ct.read_country_file(_fixture_bytes(sub)[ct.CO2E], sub, ct.CO2E)
    with pytest.raises(ct.ClimateTraceError, match="is power/electricity-generation"):
        ct.read_country_file(_fixture_bytes(sub)[ct.CO2E], _sub("heat-plants"), ct.CO2E, expected_codes=3)


def test_edgar_subsectors_are_methane_and_nitrous_oxide_at_climate_traces_gwps():
    s = _series("other-energy-use")
    sub = s.sub
    raw = {g: ct.read_country_file(_fixture_bytes(sub)[g], sub, g, expected_codes=3) for g in sub.gases}
    k = ("ABW", 2015)
    assert s.tonnes[k] == raw[ct.CH4].values[k] * Decimal("29.8") + raw[ct.N2O].values[k] * 273
    # Climate TRACE's own co2e_100yr for Aruba 2015 in this subsector is 675.4185879091251 t and its co2 is 0
    # (V5.10.0 files read on 2026-10-08 for research; neither is snapshotted, as the co2 part is IEA-EDGAR CO2).
    assert abs(s.tonnes[k] - Decimal("675.4185879091251")) < Decimal("1e-9")
    assert _sub("solid-waste-disposal").gwp_ch4 == Decimal("27.0")


def test_not_estimated_zero_years_are_missing_never_zero(monkeypatch):
    s = _series("removals")
    assert all(s.tonnes[(c, 2025)] is None for c in s.codes)
    assert "not yet estimated" in s.missing[("AFG", 2025)]
    assert all(s.tonnes[(c, 2024)] is not None for c in s.codes)
    assert s.tonnes[("ZWE", 2024)] < 0
    sub = _sub("removals")
    monkeypatch.setattr(ct, "NOT_ESTIMATED", {})
    with pytest.raises(ct.ClimateTraceError, match="every country is 0"):
        ct.subsector_series(sub, _fixture_bytes(sub), expected_codes=3, full_release=True)
    monkeypatch.setattr(ct, "NOT_ESTIMATED", {"removals": (2024,)})
    with pytest.raises(ct.ClimateTraceError, match="declared not estimated"):
        _series("removals")


def test_repeated_years_are_flagged():
    # Other animals' enteric fermentation (FAOSTAT) repeats 2023 in 2024 and 2025; on these three codes, whose
    # rows are not all zero, exactly those years repeat.
    assert _series("enteric-fermentation-other").repeated == (2024, 2025)
    assert _series("electricity-generation").repeated == ()


def test_negative_values_only_in_net_subsectors():
    sub = _sub("electricity-generation")
    data = _fixture_bytes(_sub("removals"))[ct.CO2E].replace(
        b"forestry-and-land-use,removals", b"power,electricity-generation"
    )
    with pytest.raises(ct.ClimateTraceError, match="below zero"):
        ct.read_country_file(data, sub, ct.CO2E, expected_codes=3)


def test_groups_are_sums_of_their_subsectors_or_missing(all_series):
    groups = ct.group_tonnes(all_series)
    per = {s.sub.slug: ct.tonnes_by_entity(s) for s in all_series}
    for g in ct.GROUPS:
        members = [s.slug for s in ct.MAPPING if s.group == g]
        for (e, y), (v, why) in groups[g].items():
            parts = [per[m][(e, y)][0] for m in members]
            if any(p is None for p in parts):
                assert v is None and "partial sum is never published" in why
            else:
                assert v == sum(parts, Decimal(0))
    # Growing things has no 2015 (cropland soil carbon not estimated); land uptake has no 2025.
    assert groups["growing-things"][("AFG", 2015)][0] is None
    assert groups["growing-things"][("AFG", 2016)][0] is not None
    assert groups["land-uptake"][("AFG", 2025)][0] is None
    assert groups["making-things"][("AFG", 2025)][0] is not None


def test_shares_of_the_five_add_up_to_100(all_series):
    obs, steps = ct.by_activity_share(all_series)
    by = {(o.entity, o.period, o.dims["activity"]): o for o in obs}
    for e in ("AFG", "ZWE"):
        for y in range(2016, 2026):
            five = [by[(e, str(y), a)].value for a in ct.ACTIVITIES]
            assert all(v is not None for v in five)
            assert abs(sum(five) - 100) < 1e-9
        assert by[(e, "2015", "making-things")].value is None
    assert by[("AFG", "2025", "land-uptake")].value is None
    assert any("not part of the 100" in s for s in steps)


def test_world_is_the_sum_of_every_code(all_series):
    s = next(x for x in all_series if x.sub.slug == "electricity-generation")
    vals = ct.tonnes_by_entity(s)
    for y in ct.YEARS:
        assert vals[("WLD", y)][0] == sum(s.tonnes[(c, y)] for c in s.codes)
    assert 2026 not in {y for _, y in vals}


# --- the real snapshots (local cache) ------------------------------------------------------------------------------


def _files() -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in ct.INPUTS:
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    return out


@pytest.fixture(scope="module")
def built() -> dict[str, dict]:
    files = _files()
    out = {}
    for t in ct.transforms(Paths.default()):
        r = t.run(files)
        validate(t, r.observations)
        assert r.vintage == "5.10.0" and r.date_published == "2026-08-27"
        out[t.spec.id] = r.observations
    return out


def _world(obs, year: str, dim: str) -> dict[str, float | None]:
    return {o.dims[dim]: o.value for o in obs if o.entity == "WLD" and o.period == year}


@pytest.mark.snapshot
def test_world_by_activity_golden(built):
    w = _world(built["ghg.climate-trace.by-activity"], "2024", "activity")
    expected = WORLD_2024_ACTIVITY_MT
    assert {k: round(v, 1) for k, v in w.items()} == expected
    share = _world(built["ghg.climate-trace.by-activity-share"], "2024", "activity")
    assert {k: round(v, 1) for k, v in share.items() if k in ct.ACTIVITIES} == WORLD_2024_SHARE
    assert abs(sum(v for k, v in share.items() if k in ct.ACTIVITIES) - 100) < 1e-9
    w25 = _world(built["ghg.climate-trace.by-activity"], "2025", "activity")
    assert w25["land-uptake"] is None and w25["making-things"] is not None
    total = next(
        o.value for o in built["ghg.climate-trace.five-activities-total"] if o.entity == "WLD" and o.period == "2024"
    )
    assert abs(total - sum(v for k, v in w.items() if k in ct.ACTIVITIES)) < 1e-6
    assert round(total) == 62711


@pytest.mark.snapshot
def test_world_by_subsector_golden(built):
    w = _world(built["ghg.climate-trace.by-subsector"], "2024", "subsector")
    assert len(w) == 68
    assert round(w["electricity-generation"], 1) == 13829.8
    assert round(w["road-transportation"], 1) == 6696.2
    assert round(w["removals"], 1) == -12286.8
    assert round(w["fluorinated-gases"], 1) == 1740.0
    assert _world(built["ghg.climate-trace.by-subsector"], "2025", "subsector")["removals"] is None
    assert {o.entity for o in built["ghg.climate-trace.by-subsector"]} == {"WLD"}
    entities = {o.entity for o in built["ghg.climate-trace.by-activity"]}
    assert len(entities) == 252 and "WLD" in entities and "KOS" in entities and "CYN" in entities
    heat = [o for o in built["ghg.climate-trace.by-subsector"] if o.dims["subsector"] == "heat-plants"]
    assert {o.period for o in heat if o.note} == {"2024", "2025"}
    # Each subsector carries the activity it is grouped into, and its world values add up to that activity's.
    groups = {s.slug: s.group for s in ct.MAPPING}
    assert all(o.dims["activity"] == groups[o.dims["subsector"]] for o in built["ghg.climate-trace.by-subsector"])
    by_group: dict[str, float] = {}
    for sub, v in w.items():
        by_group[groups[sub]] = by_group.get(groups[sub], 0.0) + v
    activity = _world(built["ghg.climate-trace.by-activity"], "2024", "activity")
    assert all(abs(by_group[g] - activity[g]) < 1e-6 for g in activity)


WORLD_2024_ACTIVITY_MT = {
    "making-things": 18198.0,
    "plugging-in": 14065.2,
    "growing-things": 15833.0,
    "getting-around": 9043.1,
    "keeping-warm-and-cool": 5572.0,
    "wildfires": 7989.6,
    "land-uptake": -8293.0,
    "reservoirs": 106.0,
}
"""World 2024 in V5.10.0 as built on 2026-10-08 (million tonnes CO2e), IEA-EDGAR CO2 and other manufacturing left
out."""
WORLD_2024_SHARE = {
    "making-things": 29.0,
    "plugging-in": 22.4,
    "growing-things": 25.2,
    "getting-around": 14.4,
    "keeping-warm-and-cool": 8.9,
}

"""FAOSTAT greenhouse gas emissions from all sectors (faostat-all-sectors): sectors, total, gases, per person, food's
share and methane by sector.

The source is noncommercial (its energy, industry, waste and other items are PRIMAP-hist v2.7, CC BY-NC-SA 4.0), so
no fixture is cut from it: the data tests read the real snapshots from the local cache and are marked snapshot. Tests
that need a few rows take them, byte for byte, from the cached snapshot. The tests that need no data check the
declared metadata against the registry and the area crosswalk.
"""

from __future__ import annotations

import zipfile
from collections import defaultdict
from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.emissions import faostat_all_sectors as fas
from envdash.transforms.food.faostat_bulk import FaostatBulkError, area_entity

IDS = {
    "ghg.faostat.by-sector",
    "ghg.faostat.total",
    "ghg.faostat.by-gas",
    "ghg.faostat.per-capita",
    "food.faostat.agrifood-emissions-world.share",
    "ghg.faostat.ch4-share-by-sector",
}


def _transform(indicator_id: str):
    return next(t for t in fas.transforms(Paths.default()) if t.spec.id == indicator_id)


# --- metadata (no data) --------------------------------------------------------------------------------------------


def test_registry_entry_is_noncommercial_and_quotes_primap():
    src = load_registry(Paths.default()).sources[fas.SOURCE]
    assert src.licence_class == "noncommercial"
    assert src.licence.spdx == "CC-BY-NC-SA-4.0"
    assert str(src.evidence.terms_url) == "https://zenodo.org/records/17090760"
    assert "non-commercial license" in src.evidence.licence_quote
    assert "time series (1750-2024) v2.7" in src.obligations.attribution and "FAOSTAT" in src.obligations.attribution
    assert src.obligations.notice is not None and "CC BY-NC-SA 4.0" in src.obligations.notice
    urls = {a.id: str(a.url) for a in src.artifacts}
    assert urls == {
        "emissions-totals": "https://bulks-faostat.fao.org/production/Emissions_Totals_E_All_Data_(Normalized).zip",
        "emissions-indicators": "https://bulks-faostat.fao.org/production/"
        "Climate_change_Emissions_indicators_E_All_Data_(Normalized).zip",
        "datasets-catalogue": "https://bulks-faostat.fao.org/production/datasets_E.json",
    }
    # The same GT file as the open faostat entry: one set of bytes, two registry entries.
    faostat = load_registry(Paths.default()).sources["faostat"]
    assert urls["emissions-totals"] == next(str(a.url) for a in faostat.artifacts if a.id == "emissions-totals")


def test_every_indicator_is_declared_once_with_its_scope():
    ts = fas.transforms(Paths.default())
    assert {t.spec.id for t in ts} == IDS
    for t in ts:
        assert {i.source_id for i in t.inputs} == {fas.SOURCE}, t.spec.id
        sc = t.spec.scope
        assert (sc.lulucf, sc.bunkers) == ("included", "excluded"), t.spec.id
        if t.spec.id != "ghg.faostat.ch4-share-by-sector":  # shares of methane by mass: no GWP involved
            assert sc.gwp == "AR5-GWP100", t.spec.id
        assert sc.basis, t.spec.id


def test_sector_and_gas_dimensions():
    by_sector = _transform("ghg.faostat.by-sector").spec
    assert [v.id for v in by_sector.dimensions[0].values] == [
        "energy",
        "industry",
        "agriculture",
        "land-use",
        "waste",
        "other",
    ]
    assert [p.fao.code for p in fas.SECTORS] == ["6821", "6817", "1711", "1707", "6818", "6819"]
    by_gas = _transform("ghg.faostat.by-gas").spec
    assert [v.id for v in by_gas.dimensions[0].values] == ["co2", "ch4", "n2o", "f-gases"]
    assert [g.fao.code for g in fas.GASES] == ["7273", "724413", "724313", "717815"]


def test_labels_say_what_is_and_is_not_counted():
    per_capita = _transform("ghg.faostat.per-capita").spec
    assert "divided by its population" in per_capita.description
    assert "not one person's footprint" in per_capita.description
    assert "divided by its population" in per_capita.title
    share = _transform("food.faostat.agrifood-emissions-world.share").spec
    assert share.kind == "series"
    assert "FAO's own total of all sectors" in share.description and "land use" in share.description
    assert "not a sector of their own" in share.description
    by_sector = _transform("ghg.faostat.by-sector").spec
    assert "Food is not a seventh sector" in by_sector.description
    assert "never set to zero" in by_sector.description
    assert "Tokelau, Nauru and Tuvalu" in by_sector.description
    assert "carbon dioxide counts as itself" in _transform("ghg.faostat.by-gas").spec.description


def test_china_group_is_never_an_entity():
    # FAO's "China" (351) is the sum of mainland China, Hong Kong, Macao and Taiwan, which are published separately.
    assert area_entity("351", "'159") is None
    assert [area_entity(c, m) for c, m in (("41", "'156"), ("96", "'344"), ("128", "'446"), ("214", "'158"))] == [
        "CHN",
        "HKG",
        "MAC",
        "TWN",
    ]
    with pytest.raises(FaostatBulkError, match="M49"):
        area_entity("41", "'159")


# --- the real snapshots (local cache) ------------------------------------------------------------------------------


def _files() -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in (fas.TOTALS, fas.INDICATORS, fas.CATALOGUE):
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    return out


@pytest.fixture(scope="module")
def built() -> dict[str, list]:
    files = _files()
    out = {}
    for t in fas.transforms(Paths.default()):
        r = t.run(files)
        validate(t, r.observations)
        assert r.vintage == "2025-10-28" and r.year == "2025"
        assert {c.status for c in run_checks(t, {fas.SOURCE: r.vintage}, r.observations)} <= {"pass"}
        out[t.spec.id] = r.observations
    return out


def _by(obs, dim: str | None = None) -> dict[tuple, float]:
    if dim is None:
        return {(o.entity, o.period): o.value for o in obs}
    return {(o.entity, o.period, o.dims[dim]): o.value for o in obs}


@pytest.mark.snapshot
def test_snapshots_are_the_researched_files():
    files = _files()
    assert files[fas.TOTALS.key].snapshot.sha256 == "d2c47e116553711f7c2fd6b62437db511038fd9bd9ec77815fa69ff7a18a89a9"
    assert files[fas.INDICATORS.key].snapshot.sha256 == (
        "d48bf98589ccfd3ffc2aae314091088d3a989cb58d3f149fdc26856178d6da34"
    )


@pytest.mark.snapshot
def test_world_2023_golden(built):
    """The release of 28 October 2025, World 2023, as printed by FAO (kt / 1,000,000 for GT values)."""
    sectors = _by(built["ghg.faostat.by-sector"], "sector")
    assert {s: sectors[("WLD", "2023", s)] for s in ("energy", "industry", "agriculture", "land-use", "waste")} == {
        "energy": 38.7879500023,
        "industry": 4.4300306688,
        "agriculture": 6.2414060925,
        "land-use": 0.4667261003,
        "waste": 1.9800279476,
    }
    assert sectors[("WLD", "2023", "other")] == 0.1995933362
    assert _by(built["ghg.faostat.total"])[("WLD", "2023")] == 52.1057341478
    gases = _by(built["ghg.faostat.by-gas"], "gas")
    assert [gases[("WLD", "2023", g)] for g in ("co2", "ch4", "n2o", "f-gases")] == [
        38.2742946684,
        9.4304923036,
        2.9530126919,
        1.4479344839,
    ]
    per_capita = _by(built["ghg.faostat.per-capita"])
    assert (per_capita[("WLD", "2023")], per_capita[("USA", "2023")], per_capita[("IND", "2023")]) == (
        6.44,
        16.52,
        2.96,
    )
    share = _by(built["food.faostat.agrifood-emissions-world.share"])
    assert (share[("WLD", "2023")], share[("WLD", "2001")]) == (31.73, 38.37)
    assert {o.entity for o in built["food.faostat.agrifood-emissions-world.share"]} == {"WLD"}
    ch4 = _by(built["ghg.faostat.ch4-share-by-sector"], "sector")
    assert [ch4[("WLD", "2023", p.id)] for p in fas.SECTORS] == [35.12, 0.25, 43.52, 1.63, 19.43, 0.04]


@pytest.mark.snapshot
def test_world_land_use_goes_below_zero(built):
    land = {
        o.period: o.value
        for o in built["ghg.faostat.by-sector"]
        if o.entity == "WLD" and o.dims["sector"] == "land-use"
    }
    assert land["2013"] < 0 and land["2023"] > 0
    assert _by(built["ghg.faostat.by-sector"], "sector")[("CHN", "2023", "land-use")] == -0.8343455971


@pytest.mark.snapshot
def test_sectors_add_up_to_the_published_total(built):
    totals = _by(built["ghg.faostat.total"])
    parts: dict[tuple, Decimal] = defaultdict(Decimal)
    for o in built["ghg.faostat.by-sector"]:
        parts[(o.entity, o.period)] += Decimal(repr(o.value))
    assert set(parts) == set(totals)
    worst = max(abs(parts[k] - Decimal(repr(v))) for k, v in totals.items())
    assert worst <= Decimal("0.000000001")  # 0.001 kt in billion tonnes
    assert min(int(o.period) for o in built["ghg.faostat.by-sector"]) == 1990


@pytest.mark.snapshot
def test_gases_add_up_to_the_published_total(built):
    totals = _by(built["ghg.faostat.total"])
    parts: dict[tuple, Decimal] = defaultdict(Decimal)
    for o in built["ghg.faostat.by-gas"]:
        parts[(o.entity, o.period)] += Decimal(repr(o.value))
    assert set(parts) == set(totals)
    assert max(abs(parts[k] - Decimal(repr(v))) for k, v in totals.items()) <= Decimal("0.000000001")


@pytest.mark.snapshot
def test_absent_items_stay_absent(built):
    sectors = defaultdict(set)
    for o in built["ghg.faostat.by-sector"]:
        if o.period == "2023":
            sectors[o.entity].add(o.dims["sector"])
    afolu_only = {e for e, s in sectors.items() if s == {"agriculture", "land-use"}}
    assert len(afolu_only) == 28
    assert {"BMU", "GRL", "FRO", "PSE", "PRI", "MYT"} <= afolu_only
    assert sectors["TKL"] == {"industry", "agriculture", "land-use", "waste"}
    assert sectors["NRU"] == sectors["TUV"] == {"energy", "industry", "agriculture", "land-use", "waste"}
    assert all(len(s) == 6 for e, s in sectors.items() if e not in afolu_only | {"TKL", "NRU", "TUV"})
    # Their total is the sum of the sectors FAO publishes, never padded.
    total = _by(built["ghg.faostat.total"])
    by = _by(built["ghg.faostat.by-sector"], "sector")
    assert abs(total[("BMU", "2023")] - by[("BMU", "2023", "agriculture")] - by[("BMU", "2023", "land-use")]) < 1e-9
    # The parent country carries the territory's energy (PRIMAP-hist), not its agriculture.
    assert ("GBR", "2023", "energy") in by and ("BMU", "2023", "energy") not in by


@pytest.mark.snapshot
def test_china_parts_are_published_and_the_group_is_not(built):
    total = _by(built["ghg.faostat.total"])
    assert {e for e, _ in total} >= {"CHN", "HKG", "MAC", "TWN", "WLD", "EU27"}
    # 13,934,287.xxxx kt for mainland China (41); the FAO group 351 (14,267,864 kt) is not an entity.
    assert round(total[("CHN", "2023")], 3) == 13.934
    p = Paths.default()
    table, _ = fas.read_zip(snapshots.cache_path(p, snapshots.read_current(p)[fas.TOTALS.key]), "GT")
    assert "351" in table.left_out


@pytest.mark.snapshot
def test_methane_shares_mean_what_the_element_says_and_add_up(built):
    """EM element 7265 is each sector's methane as a percentage of the area's all-sector methane: it matches GT's
    CO2-equivalent methane of the sector over that of item 6825, and the six add up to 100 where all are published."""
    p = Paths.default()
    gt_path = snapshots.cache_path(p, snapshots.read_current(p)[fas.TOTALS.key])
    wanted = {(c, "724413"): (n, "Emissions (CO2eq) from CH4 (AR5)", "kt") for c, n in _ITEMS}
    with zipfile.ZipFile(gt_path) as z, z.open(fas.GT.data_member) as f:
        gt = fas.scan(f, fas.GT, wanted)
    ch4 = {(r.entity, str(r.year), r.item): r.value for r in gt.rows}
    shares = _by(built["ghg.faostat.ch4-share-by-sector"], "sector")
    code = {pt.id: pt.fao.code for pt in fas.SECTORS}
    world = {s: ch4[("WLD", "2023", code[s])] / ch4[("WLD", "2023", "6825")] * 100 for s in code}
    for s, v in world.items():
        assert abs(Decimal(repr(shares[("WLD", "2023", s)])) - v) <= Decimal("0.005"), s
    # Everywhere, a share without a GT methane row (or the reverse) never happens in EM's area-years.
    em_keys = {(e, y) for e, y, _ in shares}
    for e, y, s in shares:
        assert (e, y, code[s]) in ch4
    for e, y, item in ch4:
        if (e, y) in em_keys and item != "6825":
            assert (e, y, next(s for s, c in code.items() if c == item)) in shares
    # Sums: every area-year with all six adds up to 100 within rounding; Niue's published shares are the only ones off.
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    n: dict[tuple, int] = defaultdict(int)
    for (e, y, _), v in shares.items():
        sums[(e, y)] += Decimal(repr(v))
        n[(e, y)] += 1
    off = {k for k, v in sums.items() if abs(v - 100) > Decimal("0.03")}
    assert {e for e, _ in off} == {"NIU"} and all(n[k] < 6 for k in off)


_ITEMS = [
    ("6821", "Energy"),
    ("6817", "IPPU"),
    ("1711", "IPCC Agriculture"),
    ("1707", "LULUCF"),
    ("6818", "Waste"),
    ("6819", "Other"),
    ("6825", "All sectors with LULUCF"),
]


def _real_lines(domain: fas.Domain, path, areas: set[bytes]) -> list[bytes]:
    """The header and every line of the cached CSV whose Area Code is one of `areas`, byte for byte."""
    with zipfile.ZipFile(path) as z, z.open(domain.data_member) as f:
        header = f.readline()
        return [header, *(ln for ln in f if any(ln.startswith(b'"' + a + b'",') for a in areas))]


@pytest.fixture(scope="module")
def world_gt() -> list[bytes]:
    p = Paths.default()
    return _real_lines(fas.GT, snapshots.cache_path(p, snapshots.read_current(p)[fas.TOTALS.key]), {b"5000"})


@pytest.mark.snapshot
def test_refuses_a_broken_identity(world_gt):
    flags = {"E": "Estimated value"}
    table = fas.scan(world_gt, fas.GT, fas._wanted_gt())
    fas.by_sector(table, flags)
    fas.by_gas(table, flags)
    energy_2023 = next(ln for ln in world_gt if b'"6821","Energy","723113"' in ln and b'"2023","2023"' in ln)
    broken = [ln.replace(b'"38787950.002300"', b'"38787960.002300"') if ln == energy_2023 else ln for ln in world_gt]
    assert broken != world_gt
    with pytest.raises(FaostatBulkError, match="sectors add up"):
        fas.by_sector(fas.scan(broken, fas.GT, fas._wanted_gt()), flags)
    no_ch4 = [ln for ln in world_gt if not (b'"6825"' in ln and b'"724413"' in ln and b'"2023","2023"' in ln)]
    with pytest.raises(FaostatBulkError, match="gases add up"):
        fas.by_gas(fas.scan(no_ch4, fas.GT, fas._wanted_gt()), flags)


@pytest.mark.snapshot
def test_refuses_renamed_items_units_and_duplicates(world_gt):
    renamed = [ln.replace(b'"IPCC Agriculture"', b'"Agriculture"') for ln in world_gt]
    with pytest.raises(FaostatBulkError, match="named"):
        fas.scan(renamed, fas.GT, fas._wanted_gt())
    unit = [ln.replace(b'"FAO TIER 1","kt"', b'"FAO TIER 1","Mt"') for ln in world_gt]
    with pytest.raises(FaostatBulkError, match="unit"):
        fas.scan(unit, fas.GT, fas._wanted_gt())
    dup = next(ln for ln in world_gt if b'"6825"' in ln and b'"723113"' in ln and b'"FAO TIER 1"' in ln)
    with pytest.raises(FaostatBulkError, match="more than one"):
        fas.scan([*world_gt, dup], fas.GT, fas._wanted_gt())
    with pytest.raises(FaostatBulkError, match="columns"):
        fas.scan([world_gt[0].replace(b",Note", b""), *world_gt[1:]], fas.GT, fas._wanted_gt())


@pytest.mark.snapshot
def test_vintage_needs_the_catalogue_to_describe_this_file():
    files = _files()
    p = Paths.default()
    table, _ = fas.read_zip(snapshots.cache_path(p, snapshots.read_current(p)[fas.INDICATORS.key]), "EM")
    assert table.data_rows == 678_370
    updated, step = fas.vintage(files, fas.INDICATORS, fas.EM, table.data_rows)
    assert updated.isoformat() == "2025-10-28" and "FileRows 678,370" in step
    with pytest.raises(FaostatBulkError, match="describes another file"):
        fas.vintage(files, fas.INDICATORS, fas.EM, table.data_rows - 1)


@pytest.mark.snapshot
def test_publisher_checks_apply_only_to_their_vintage(built):
    for tid in ("ghg.faostat.total", "food.faostat.agrifood-emissions-world.share"):
        t = _transform(tid)
        now = run_checks(t, {fas.SOURCE: "2025-10-28"}, built[tid])
        assert now and {o.status for o in now} == {"pass"}, [o.detail for o in now]
        later = run_checks(t, {fas.SOURCE: "2026-10-30"}, built[tid])
        assert {o.status for o in later} == {"not-applicable"}

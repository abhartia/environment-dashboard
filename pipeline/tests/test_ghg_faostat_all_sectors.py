"""FAOSTAT greenhouse gas emissions from all sectors (faostat-all-sectors): sectors, total, gases, per person, food's
share and methane by sector.

The source is noncommercial (its energy, industry, waste and other items are PRIMAP-hist v2.8, CC BY-NC-SA 4.0), so
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
from envdash.transforms.food.faostat_bulk import FaostatBulkError, area_entity, not_collected_step

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
    assert str(src.evidence.terms_url) == "https://zenodo.org/records/22876287"
    assert "Since v2.8" in src.evidence.licence_quote and "non-commercial license" in src.evidence.licence_quote
    assert "time series v2.8 (1750-2025)" in src.obligations.attribution and "FAOSTAT" in src.obligations.attribution
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
        # From the release of 6 November 2026 the World's total (and EM's World shares) counts international bunkers.
        assert (sc.lulucf, sc.bunkers) == ("included", "included"), t.spec.id
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
        "bunkers",
    ]
    assert [p.fao.code for p in fas.SECTORS] == ["6821", "6817", "1711", "1707", "6818", "6819"]
    assert [p.fao.code for p in fas.PARTS] == ["6821", "6817", "1711", "1707", "6818", "6819", "6820"]
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
    # The share's unit and title, shown next to the big number, name the denominator.
    assert share.unit.label == "percent of FAO's all-sector total (net land use, with international transport)"
    assert "FAO's all-sector" in share.title and "global" not in share.title
    assert "not a share of gross global emissions" in share.description
    by_sector = _transform("ghg.faostat.by-sector").spec
    assert "Food is not a further sector" in by_sector.description
    assert "never set to zero" in by_sector.description
    assert "Tokelau and Nauru in part" in by_sector.description
    assert "no country's does" in by_sector.description
    total = _transform("ghg.faostat.total").spec
    for spec in (by_sector, total):
        assert "agriculture plus land use only" in spec.description
        assert fas.ZERO_TOTALS in spec.description and "not comparable with countries'" in spec.description
    by_gas = _transform("ghg.faostat.by-gas").spec
    assert "carbon dioxide counts as itself" in by_gas.description
    assert "net carbon dioxide of land use" in by_gas.description and "below zero" in by_gas.description
    per_capita_words = (
        "Mayotte has no energy, industry, waste or other emissions, Tokelau no energy or other, and Nauru no other"
    )
    assert per_capita_words in per_capita.description and "201 of the values" in per_capita.description


def test_methane_land_use_is_fires_not_net():
    ch4 = _transform("ghg.faostat.ch4-share-by-sector").spec
    labels = {v.id: v.label for v in ch4.dimensions[0].values}
    assert labels["land-use"] == "Land use (fires)"
    assert "(net" not in ch4.scope.basis and "can be negative" not in ch4.scope.basis
    # The CO2-equivalent indicators keep the net label and say it can be negative.
    co2e = _transform("ghg.faostat.by-sector").spec
    assert {v.id: v.label for v in co2e.dimensions[0].values}["land-use"].endswith("(net)")
    assert "can be negative" in co2e.scope.basis


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
def results() -> dict:
    files = _files()
    out = {}
    for t in fas.transforms(Paths.default()):
        r = t.run(files)
        validate(t, r.observations)
        assert r.vintage == "2026-11-06" and r.year == "2026"
        # The publisher checks (Analytical Brief 115) are for the release of 28 October 2025; FAO has published no
        # brief for this release yet, so none applies to it.
        assert {c.status for c in run_checks(t, {fas.SOURCE: r.vintage}, r.observations)} <= {"not-applicable"}
        out[t.spec.id] = r
    return out


@pytest.fixture(scope="module")
def built(results) -> dict[str, list]:
    return {i: r.observations for i, r in results.items()}


def _by(obs, dim: str | None = None) -> dict[tuple, float]:
    if dim is None:
        return {(o.entity, o.period): o.value for o in obs}
    return {(o.entity, o.period, o.dims[dim]): o.value for o in obs}


@pytest.mark.snapshot
def test_snapshots_are_the_researched_files():
    files = _files()
    # The release of 6 November 2026 (data to 2024), fetched 2026-11-08 and 2026-11-15.
    assert files[fas.TOTALS.key].snapshot.sha256 == "b048ba37ed06d5f78543a458645a30882473af91c387ec5378e76d92c8f79233"
    assert files[fas.INDICATORS.key].snapshot.sha256 == (
        "f49d3fded1ee57ce38ef030f617bb3092a5ba142f76624ad444e2f663df52aec"
    )


@pytest.mark.snapshot
def test_world_2023_golden(built):
    """The release of 6 November 2026, World 2023, as printed by FAO (kt / 1,000,000 for GT values)."""
    sectors = _by(built["ghg.faostat.by-sector"], "sector")
    assert {s: sectors[("WLD", "2023", s)] for s in ("energy", "industry", "agriculture", "land-use", "waste")} == {
        "energy": 39.5784965578,
        "industry": 4.451763207,
        "agriculture": 6.2705356143,
        "land-use": -0.7109187689,
        "waste": 1.8026128723,
    }
    assert sectors[("WLD", "2023", "other")] == 0.208048738
    assert sectors[("WLD", "2023", "bunkers")] == 1.330160385
    assert _by(built["ghg.faostat.total"])[("WLD", "2023")] == 52.9306986056
    gases = _by(built["ghg.faostat.by-gas"], "gas")
    assert [gases[("WLD", "2023", g)] for g in ("co2", "ch4", "n2o", "f-gases")] == [
        39.2553995735,
        9.2115119648,
        3.0128671834,
        1.4509198839,
    ]
    per_capita = _by(built["ghg.faostat.per-capita"])
    assert (per_capita[("WLD", "2023")], per_capita[("USA", "2023")], per_capita[("IND", "2023")]) == (
        6.5413,
        15.9189,
        3.0669,
    )
    share = _by(built["food.faostat.agrifood-emissions-world.share"])
    assert (share[("WLD", "2023")], share[("WLD", "2001")]) == (35.2317, 44.7449)
    assert {o.entity for o in built["food.faostat.agrifood-emissions-world.share"]} == {"WLD"}
    ch4 = _by(built["ghg.faostat.ch4-share-by-sector"], "sector")
    assert [ch4[("WLD", "2023", p.id)] for p in fas.PARTS] == [
        35.3171,
        0.1852,
        44.7446,
        1.6697,
        17.8937,
        0.0458,
        0.144,
    ]


@pytest.mark.snapshot
def test_bunkers_are_a_part_of_the_world_only(built):
    by = _by(built["ghg.faostat.by-sector"], "sector")
    years = {p for e, p, s in by if s == "bunkers" and e == "WLD"}
    assert years == {str(y) for y in range(1990, 2025)}
    assert {e for e, _, s in by if s == "bunkers"} == {"WLD"}
    ch4 = _by(built["ghg.faostat.ch4-share-by-sector"], "sector")
    assert {e for e, _, s in ch4 if s == "bunkers"} == {"WLD"}


@pytest.mark.snapshot
def test_world_land_use_goes_below_zero(built):
    land = {
        o.period: o.value
        for o in built["ghg.faostat.by-sector"]
        if o.entity == "WLD" and o.dims["sector"] == "land-use"
    }
    assert land["2013"] < 0 and land["2023"] < 0
    assert _by(built["ghg.faostat.by-sector"], "sector")[("CHN", "2023", "land-use")] == -1.3797496792


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
    assert len(afolu_only) == 26
    assert {"BMU", "GRL", "FRO", "PSE", "PRI", "MYT"} <= afolu_only
    # Svalbard and Jan Mayen has land use only, so with the 26 it makes the description's 27 territories.
    assert sectors["SJM"] == {"land-use"}
    assert sectors["TKL"] == {"industry", "agriculture", "land-use", "waste"}
    assert sectors["NRU"] == {"energy", "industry", "agriculture", "land-use", "waste"}
    assert len(sectors["WLD"]) == 7 and "bunkers" in sectors["WLD"]
    assert all(len(s) == 6 for e, s in sectors.items() if e not in afolu_only | {"SJM", "TKL", "NRU", "WLD"})
    # Their total is the sum of the sectors FAO publishes, never padded.
    total = _by(built["ghg.faostat.total"])
    by = _by(built["ghg.faostat.by-sector"], "sector")
    assert abs(total[("BMU", "2023")] - by[("BMU", "2023", "agriculture")] - by[("BMU", "2023", "land-use")]) < 1e-9
    # The parent country carries the territory's energy (PRIMAP-hist), not its agriculture.
    assert ("GBR", "2023", "energy") in by and ("BMU", "2023", "energy") not in by


@pytest.mark.snapshot
def test_zero_totals_negative_values_and_gaps_match_the_descriptions(built, results):
    """The counts and lists the descriptions give for the November 2026 release, from the snapshot."""
    total = _by(built["ghg.faostat.total"])
    zeros = {e for (e, _), v in total.items() if v == 0}
    assert zeros == {"ASM", "GIB", "GRL", "GUM", "MNP", "NFK", "PCN", "SJM"}
    assert sum(1 for v in total.values() if v == 0) == 202
    names = {e: n for e, n in (("ASM", "American Samoa"), ("GIB", "Gibraltar"), ("SJM", "Svalbard and Jan Mayen"))}
    assert all(n in fas.ZERO_TOTALS for n in names.values())
    for i in ("ghg.faostat.total", "ghg.faostat.by-sector"):
        assert any(
            s.startswith(f'FAO prints a "{fas.ALL_SECTORS.name}" total of exactly 0 kt') and "202" in s
            for s in results[i].steps
        ), i
    per_capita = _by(built["ghg.faostat.per-capita"])
    assert sum(1 for v in per_capita.values() if v < 0) == 201
    assert any(
        s.startswith("201 published per-person values are below zero") for s in results["ghg.faostat.per-capita"].steps
    )
    # F-gases: the by-gas description's 61 countries and territories without a fluorinated-gas row.
    gases = defaultdict(set)
    for o in built["ghg.faostat.by-gas"]:
        gases[o.entity].add(o.dims["gas"])
    assert sum(1 for g in gases.values() if "f-gases" not in g) == 61
    # The per-person gaps the description names: of the EM entities, only these lack sectors in GT.
    sectors = defaultdict(set)
    for o in built["ghg.faostat.by-sector"]:
        if o.period == "2023":
            sectors[o.entity].add(o.dims["sector"])
    em = {e for e, _ in per_capita}
    gaps = {
        e: {"energy", "industry", "agriculture", "land-use", "waste", "other"} - sectors[e] for e in em if e in sectors
    }
    assert {e: g for e, g in gaps.items() if g} == {
        "MYT": {"energy", "industry", "waste", "other"},
        "TKL": {"energy", "other"},
        "NRU": {"other"},
    }


@pytest.mark.snapshot
def test_em_indicators_name_the_em_page(results):
    for i, r in results.items():
        if any(inp == fas.INDICATORS for inp in _transform(i).inputs):
            assert {k: m.url_main for k, m in r.origin_meta.items()} == {
                fas.INDICATORS.key: fas.EM_PAGE,
                fas.CATALOGUE.key: fas.EM_PAGE,
            }, i
        else:
            assert r.origin_meta == {}, i


@pytest.mark.snapshot
def test_china_parts_are_published_and_the_group_is_not(built):
    total = _by(built["ghg.faostat.total"])
    assert {e for e, _ in total} >= {"CHN", "HKG", "MAC", "TWN", "WLD", "EU27"}
    # 14,037,501.xxxx kt for mainland China (41); the FAO group 351 is not an entity.
    assert round(total[("CHN", "2023")], 3) == 14.038
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
    code = {pt.id: pt.fao.code for pt in fas.PARTS}
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
    # Sums: every area-year with all six sectors adds up to 100 within rounding, except the one declared in
    # CH4_SHARES_OVER_100 (Tuvalu 2000); the other area-years off are ones with fewer than six sectors.
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    n: dict[tuple, int] = defaultdict(int)
    for (e, y, s), v in shares.items():
        sums[(e, y)] += Decimal(repr(v))
        n[(e, y)] += s != "bunkers"
    off = {k for k, v in sums.items() if abs(v - 100) > Decimal("0.03")}
    assert {k for k in off if n[k] == 6} == {("TUV", "2000")}
    assert {e for e, _ in off} == {"NIU", "NRU", "SHN", "TUV"}


_ITEMS = [
    ("6821", "Energy"),
    ("6817", "IPPU"),
    ("1711", "IPCC Agriculture"),
    ("1707", "LULUCF"),
    ("6818", "Waste"),
    ("6819", "Other"),
    ("6820", "International bunkers"),
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
    assert b'"39578496.557800"' in energy_2023
    broken = [ln.replace(b'"39578496.557800"', b'"39578506.557800"') if ln == energy_2023 else ln for ln in world_gt]
    assert broken != world_gt
    with pytest.raises(FaostatBulkError, match="sectors add up"):
        fas.by_sector(fas.scan(broken, fas.GT, fas._wanted_gt()), flags)
    no_ch4 = [ln for ln in world_gt if not (b'"6825"' in ln and b'"724413"' in ln and b'"2023","2023"' in ln)]
    with pytest.raises(FaostatBulkError, match="gases add up"):
        fas.by_gas(fas.scan(no_ch4, fas.GT, fas._wanted_gt()), flags)
    # Without its bunkers rows, the World's sectors no longer make up its total.
    no_bunkers = [ln for ln in world_gt if b'"6820","International bunkers"' not in ln]
    with pytest.raises(FaostatBulkError, match="sectors add up"):
        fas.by_sector(fas.scan(no_bunkers, fas.GT, fas._wanted_gt()), flags)


@pytest.mark.snapshot
def test_rows_flagged_l_are_left_out_and_other_empty_values_stop():
    """Nicaragua 2023-2024 in EM: FAO prints these rows with no value and flag L, which the codebook defines as
    "Missing value; data exist but were not collected"."""
    p = Paths.default()
    lines = _real_lines(fas.EM, snapshots.cache_path(p, snapshots.read_current(p)[fas.INDICATORS.key]), {b"157"})
    table = fas.scan(lines, fas.EM, fas._wanted_em())
    assert table.not_collected == {("Nicaragua", 2023), ("Nicaragua", 2024)}
    assert not any(r.year >= 2023 for r in table.rows)
    flags = {"E": "Estimated value", "L": "Missing value; data exist but were not collected"}
    (step,) = not_collected_step(table.not_collected, flags, fas.EM.flags_member)
    assert "Nicaragua 2023, 2024" in step and "nothing is filled in" in step
    with pytest.raises(FaostatBulkError, match="flag L"):
        not_collected_step(table.not_collected, {"L": "Low reliability"}, fas.EM.flags_member)
    empty_e = [ln.replace(b',,"L"', b',,"E"') for ln in lines]
    assert empty_e != lines
    with pytest.raises(FaostatBulkError, match="empty Value with flag 'E'"):
        fas.scan(empty_e, fas.EM, fas._wanted_em())


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
    assert table.data_rows == 744_060
    updated, step = fas.vintage(files, fas.INDICATORS, fas.EM, table.data_rows)
    assert updated.isoformat() == "2026-11-06" and "FileRows 744,060" in step
    with pytest.raises(FaostatBulkError, match="describes another file"):
        fas.vintage(files, fas.INDICATORS, fas.EM, table.data_rows - 1)


@pytest.mark.snapshot
def test_publisher_checks_apply_only_to_their_vintage(built):
    # The checks quote Analytical Brief 115 for the release of 28 October 2025 (they passed on that release's files
    # until 2026-11-15); on the release of 6 November 2026, FAO's revised values no longer match the brief, which is
    # why each check names its vintage.
    for tid in ("ghg.faostat.total", "food.faostat.agrifood-emissions-world.share"):
        t = _transform(tid)
        assert all(c.vintage == fas.VINTAGE_2023 for c in t.checks)
        later = run_checks(t, {fas.SOURCE: "2026-11-06"}, built[tid])
        assert later and {o.status for o in later} == {"not-applicable"}

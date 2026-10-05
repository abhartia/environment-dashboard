"""FAOSTAT Emissions totals (GT): world agrifood emissions, their share, livestock methane.

Fixtures are byte-exact slices of the real GT snapshot (the World rows of three item/element pairs from the CSV inside
the zip, and the whole flag codebook) and the whole datasets_E.json catalogue, cut by
tests/fixtures/faostat/make_zip_fixture.py. They sit one directory lower than make_fixture.py's, so the two sidecar
checks of test_fixtures_provenance.py are repeated here with the zip-aware cutter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from envdash import canonical
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import run_checks
from envdash.transforms.food.faostat_emissions import (
    AGRIFOOD,
    CO2EQ_AR5,
    FaostatFormatError,
    agrifood_share,
    agrifood_total,
    catalogue_entry,
    livestock_ch4,
    read_flags,
    scan,
    series,
    transforms,
)

FIXTURES = Path(__file__).parent / "fixtures" / "faostat"
SIDECARS = sorted(FIXTURES.glob("*/*.provenance.json"))
GT_URL = "https://bulks-faostat.fao.org/production/Emissions_Totals_E_All_Data_(Normalized).zip"


def _fixture(name: str) -> Path:
    # Copied from support.fixture's idea: the fixture is the sidecar's name without .provenance.json.
    return next(s for s in SIDECARS if s.name == name + ".provenance.json").with_name(name)


def _lines() -> list[bytes]:
    return _fixture("d2c47e116553.csv").read_bytes().splitlines(keepends=True)


def _scan():
    return scan(_lines())


def _flags():
    return read_flags(_fixture("d2c47e116553.flags.csv").read_bytes())


def _by(obs):
    return {o.period: o for o in obs}


def _transform(indicator_id: str):
    return next(t for t in transforms(Paths.default()) if t.spec.id == indicator_id)


# --- fixtures ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == "faostat"
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes"):
        assert meta[k]
    assert load_registry(Paths.default()).sources[meta["source_id"]].licence_class == "open"


@pytest.mark.snapshot
@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(FIXTURES))
    from make_zip_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    artifact, member, area, pairs = parse_command(meta["command"])
    assert artifact == meta["artifact_id"]
    sliced, _ = cut(raw, member, area, pairs)
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]


# --- parsing -------------------------------------------------------------------------------------------------------


def test_scan_keeps_world_rows_and_counts_all():
    s = _scan()
    assert s.data_rows == 133 and len(s.world) == 133
    assert {r["Area"] for r in s.world} == {"World"}


def test_agrifood_total_in_billion_tonnes():
    obs, steps = agrifood_total(_scan(), _flags())
    by = _by(obs)
    assert obs[0].period == "1990" and obs[-1].period == "2023" and len(obs) == 34
    # 16,535,072.373700 kt in the file.
    assert by["2023"].value == 16.5350723737
    assert by["2001"].value == 13.6147531515
    assert all(o.entity == "WLD" and o.note is None and o.status == "final" for o in obs)
    assert any('flag E, which the file\'s codebook defines as "Estimated value"' in s for s in steps)


def test_share_uses_the_with_lulucf_total():
    obs, _ = agrifood_share(_scan(), _flags())
    by = _by(obs)
    # 16,535,072.3737 / 52,105,734.1478 and 13,614,753.1515 / 35,481,364.4588, exact decimals.
    assert round(by["2023"].value, 6) == 31.73369
    assert round(by["2001"].value, 6) == 38.37156
    assert len(obs) == 34


def test_livestock_methane_leaves_out_projections():
    obs, steps = livestock_ch4(_scan(), _flags())
    by = _by(obs)
    assert obs[0].period == "1961" and obs[-1].period == "2023" and len(obs) == 63
    assert by["2023"].value == 115.21126 and by["1961"].value == 72.517492
    assert "2030" not in by and "2050" not in by
    assert any("projections for 2030 and 2050" in s for s in steps)


def test_publisher_checks_pass_for_their_vintage_only():
    s, flags = _scan(), _flags()
    for tid, compute in (
        ("food.faostat.agrifood-emissions-world", agrifood_total),
        ("food.faostat.agrifood-emissions-world.share", agrifood_share),
    ):
        t = _transform(tid)
        obs, _ = compute(s, flags)
        outcomes = run_checks(t, {"faostat": "2025-10-28"}, obs)
        assert outcomes and {o.status for o in outcomes} == {"pass"}, [o.detail for o in outcomes]
        later = run_checks(t, {"faostat": "2026-10-30"}, obs)
        assert {o.status for o in later} == {"not-applicable"}


def test_share_check_would_fail_with_the_without_lulucf_total():
    # The 2001 check is what pins the denominator: FAO prints 38, and the without-LULUCF total gives 38.57.
    t = _transform("food.faostat.agrifood-emissions-world.share")
    obs, _ = agrifood_share(_scan(), _flags())
    shifted = [o.model_copy(update={"value": 38.57}) if o.period == "2001" else o for o in obs]
    out = {o.check.period: o.status for o in run_checks(t, {"faostat": "2025-10-28"}, shifted)}
    assert out == {"2001": "fail", "2023": "pass"}


# --- refusals ------------------------------------------------------------------------------------------------------


def test_refuses_mismatched_years_between_numerator_and_denominator():
    lines = [ln for ln in _lines() if not (b'"6825"' in ln and b'"2023","2023"' in ln)]
    with pytest.raises(FaostatFormatError, match="covers"):
        agrifood_share(scan(lines), _flags())


def test_refuses_a_duplicated_year():
    lines = _lines()
    dup = next(ln for ln in lines if b'"6518"' in ln and b'"2023","2023"' in ln)
    with pytest.raises(FaostatFormatError, match="more than one"):
        series(scan([*lines, dup]), AGRIFOOD, CO2EQ_AR5)


def test_refuses_renamed_item_and_changed_columns():
    lines = _lines()
    renamed = [ln.replace(b'"Agrifood systems"', b'"Agrifood system"') for ln in lines]
    with pytest.raises(FaostatFormatError, match="named"):
        agrifood_total(scan(renamed), _flags())
    with pytest.raises(FaostatFormatError, match="columns"):
        scan([lines[0].replace(b",Note", b""), *lines[1:]])


def test_refuses_a_flag_missing_from_the_codebook():
    flags = {k: v for k, v in _flags().items() if k != "E"}
    with pytest.raises(FaostatFormatError, match="not in"):
        agrifood_total(_scan(), flags)


# --- vintage -------------------------------------------------------------------------------------------------------


def test_vintage_from_catalogue_entry_for_this_file():
    raw = _fixture("54b055217bee.json").read_bytes()
    updated, rows = catalogue_entry(raw, GT_URL)
    assert updated.isoformat() == "2025-10-28"
    # The data rows of the full CSV member, recorded in the fixture's sidecar by the cutter.
    meta = json.loads((FIXTURES / "emissions-totals" / "d2c47e116553.csv.provenance.json").read_text())
    assert rows == meta["data_rows_total"] == 2_500_090
    with pytest.raises(FaostatFormatError, match="not"):
        catalogue_entry(raw, GT_URL.replace("Totals", "totals"))


@pytest.mark.snapshot
def test_full_snapshot_builds_all_three():
    from envdash import snapshots
    from envdash.transform import InputFile

    p = Paths.default()
    cur = snapshots.read_current(p)
    files = {}
    for key in ("faostat/emissions-totals", "faostat/datasets-catalogue"):
        snap = snapshots.read_manifest(p, cur[key])
        assert snap is not None
        files[key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    for t in transforms(p):
        r = t.run(files)
        assert r.vintage == "2025-10-28" and r.year == "2025"
        assert {o.status for o in run_checks(t, {"faostat": r.vintage}, r.observations)} <= {"pass"}


@pytest.mark.snapshot
def test_full_snapshot_scope_identities():
    """What the share's scope says: the with-LULUCF total is the IPCC sectors without international bunkers, and the
    agrifood land-use change is net forest conversion and fires, without the forest sink, in every World year."""
    from decimal import Decimal

    from envdash import snapshots
    from envdash.transforms.food.faostat_emissions import CO2EQ_AR5, _read_zip, series

    p = Paths.default()
    s, _ = _read_zip(snapshots.cache_path(p, snapshots.read_current(p)["faostat/emissions-totals"]))

    def by_year(code: str, name: str) -> dict[int, Decimal]:
        pts, _ = series(s, (code, name), CO2EQ_AR5)
        return {pt.year: pt.value for pt in pts}

    total = by_year("6825", "All sectors with LULUCF")
    sectors = [
        by_year(c, n)
        for c, n in (
            ("6821", "Energy"),
            ("6817", "IPPU"),
            ("6818", "Waste"),
            ("6819", "Other"),
            ("1711", "IPCC Agriculture"),
            ("1707", "LULUCF"),
        )
    ]
    bunkers = by_year("6820", "International bunkers")
    rounding = Decimal("0.0003")  # six values printed to 0.0001 kt
    assert len(total) == 34
    for y, v in total.items():
        parts = sum((sec[y] for sec in sectors), Decimal(0))
        assert abs(parts - v) <= rounding, y
        assert abs(parts + bunkers[y] - v) > 1000, y  # adding bunkers (over 650,000 kt) would not match
    luc = by_year("6516", "Land-use change")
    luc_parts = [
        by_year(c, n)
        for c, n in (
            ("6750", "Net Forest conversion"),
            ("69921", "Fires in humid tropical forests"),
            ("6993", "Fires in organic soils"),
        )
    ]
    forest = by_year("6751", "Forestland")
    for y, v in luc.items():
        assert sum((x[y] for x in luc_parts), Decimal(0)) == v, y
        assert forest[y] < 0, y  # a net removal, and not part of the item


def test_share_scope_states_bunkers_and_agrifood_land_use_change():
    share = next(t for t in transforms(Paths.default()) if t.spec.id == "food.faostat.agrifood-emissions-world.share")
    sc = share.spec.scope
    assert (sc.gwp, sc.lulucf, sc.bunkers) == ("AR5-GWP100", "included", "excluded")
    assert sc.basis is not None
    assert "only what FAO attributes to agriculture" in sc.basis and '"Forestland"' in sc.basis
    assert '"International bunkers"' in sc.basis


def test_gcb_published_values_carry_their_scope():
    reg = load_registry(Paths.default())
    lit = reg.literature
    for lid in ("gcb-2025-essd-fossil-2025", "gcb-2025-essd-fossil-growth-2025"):
        assert (lit[lid].scope.lulucf, lit[lid].scope.bunkers) == ("excluded", "included"), lid
    budget = lit["gcb-2025-essd-remaining-budget-1-5c"]
    assert (budget.scope.lulucf, budget.scope.bunkers) == ("included", "included")
    assert "from the start of 2026" in budget.title

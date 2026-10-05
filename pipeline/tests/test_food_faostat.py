"""FAOSTAT country-level transforms: land use (RL), SDG 12.3.1a food loss (SDGB), agrifood emissions by country (GT),
and the shared area table.

Fixtures are byte-exact slices of the real snapshots, cut by tests/fixtures/faostat/make_zip_fixture.py: rows of one
area (World, Nicaragua, the USSR, Brazil, FAO's "China" group, Sub-Saharan Africa) for the item/element pairs used, and
the whole flag codebooks. Their sidecars are checked by test_faostat_emissions.py (every tests/fixtures/faostat/*/
sidecar). Slices hold fewer rows than the full files, so FileRows is checked against each sidecar's data_rows_total.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from envdash import geo
from envdash.paths import Paths
from envdash.transforms.food import faostat_country_emissions as gt
from envdash.transforms.food import faostat_food_loss as sdg
from envdash.transforms.food import faostat_land_use as rl
from envdash.transforms.food.faostat_bulk import (
    AREAS,
    FAO_GROUPS,
    FORMER,
    NO_ENTITY,
    FaostatBulkError,
    area_entity,
    catalogue_entry,
    read_flags,
)

FIXTURES = Path(__file__).parent / "fixtures" / "faostat"
CATALOGUE = FIXTURES / "datasets-catalogue" / "54b055217bee.json"


def _lines(artifact: str, *names: str) -> list[bytes]:
    """The header of the first fixture, then the data lines of each, in order."""
    out: list[bytes] = []
    for i, name in enumerate(names):
        lines = (FIXTURES / artifact / name).read_bytes().splitlines(keepends=True)
        out += lines if i == 0 else lines[1:]
    return out


def _total_rows(artifact: str, name: str) -> int:
    return json.loads((FIXTURES / artifact / f"{name}.provenance.json").read_text())["data_rows_total"]


def _flags(artifact: str, name: str, member: str) -> dict[str, str]:
    return read_flags((FIXTURES / artifact / name).read_bytes(), member)


# --- area table ----------------------------------------------------------------------------------------------------


def test_area_tables_are_disjoint_and_every_code_resolves():
    tables = [set(AREAS), set(FORMER), set(NO_ENTITY), set(FAO_GROUPS)]
    assert sum(len(t) for t in tables) == len(set().union(*tables))
    ours = [code for _, code in AREAS.values()]
    assert len(ours) == len(set(ours)), "two FAO areas map to one entity"
    for code in ours:
        assert geo.resolve(code, "iso3") == code


def test_area_entity_checks_m49_and_refuses_unknown_codes():
    assert area_entity("41", "'156") == "CHN"
    assert area_entity("5000", "'001") == "WLD"
    assert area_entity("228", "'810") is None  # USSR
    # Territories and Serbia and Montenegro, published since envdash/geo.py declares them; Sark is still left out.
    assert area_entity("69", "'254") == "GUF" and area_entity("259", "'830") == "CHI"
    assert area_entity("186", "'891") == "SRB_MNE" and area_entity("285", "'680") is None
    with pytest.raises(FaostatBulkError, match="M49"):
        area_entity("41", "'159")
    with pytest.raises(FaostatBulkError, match="not declared"):
        area_entity("99999", "'999")


# --- land use ------------------------------------------------------------------------------------------------------


def _rl_obs(element):
    lines = _lines("land-use", "39b739fbfb69.csv", "39b739fbfb69.nicaragua.csv", "39b739fbfb69.ussr.csv")
    table = rl.read(lines, element)
    flags = _flags("land-use", "39b739fbfb69.flags.csv", rl.FLAGS_MEMBER)
    return table, rl.observations(table, element, flags)


def test_land_use_area_world_and_country():
    _, (obs, steps) = _rl_obs(rl.AREA)
    by = {(o.entity, o.dims["category"], o.period): o for o in obs}
    # As printed in the file: World agricultural land 2024, 4,689,511.95 thousand ha (flag E).
    assert by[("WLD", "agricultural-land", "2024")].value == 4689511.95
    assert by[("WLD", "agricultural-land", "2024")].note == "FAO flag E: Estimated value."
    assert ("WLD", "forest-land", "1989") not in by and ("WLD", "forest-land", "1990") in by
    assert {o.entity for o in obs} == {"WLD", "NIC"}
    # Nicaragua 2023-2024 are empty in the file with flag L: published as null with FAO's words.
    nic = by[("NIC", "agricultural-land", "2024")]
    assert nic.value is None and nic.missing_reason == 'FAO flag L: "Missing value; data exist but were not collected".'
    assert any("USSR" in s for s in steps)


def test_land_use_share_world():
    _, (obs, steps) = _rl_obs(rl.SHARE)
    by = {(o.entity, o.dims["category"], o.period): o for o in obs}
    assert by[("WLD", "agricultural-land", "2024")].value == 36.03
    assert by[("WLD", "forest-land", "2024")].value == 31.85
    # Only flag E among the values: stated once, not on each value.
    assert by[("WLD", "forest-land", "2024")].note is None
    assert any('flag E, which the file\'s codebook defines as "Estimated value"' in s for s in steps)


def test_land_use_refuses_renamed_item_and_unknown_area():
    lines = _lines("land-use", "39b739fbfb69.csv")
    flags = _flags("land-use", "39b739fbfb69.flags.csv", rl.FLAGS_MEMBER)
    renamed = [ln.replace(b'"Cropland"', b'"Crop land"') for ln in lines]
    with pytest.raises(FaostatBulkError, match="named"):
        rl.observations(rl.read(renamed, rl.AREA), rl.AREA, flags)
    moved = [ln.replace(b'"5000","\'001"', b'"5999","\'001"') for ln in lines]
    with pytest.raises(FaostatBulkError, match="not declared"):
        rl.observations(rl.read(moved, rl.AREA), rl.AREA, flags)


def test_land_use_vintage_from_catalogue():
    updated, rows = catalogue_entry(CATALOGUE.read_bytes(), rl.DATASET_CODE, str(_url("land-use")))
    assert updated.isoformat() == "2026-10-02"
    assert rows == _total_rows("land-use", "39b739fbfb69.csv") == 421_850


def _url(artifact: str) -> str:
    side = next((FIXTURES / artifact).glob("*.provenance.json"))
    return json.loads(side.read_text())["url"]


# --- food loss -----------------------------------------------------------------------------------------------------


def test_food_loss_world_total_and_groups():
    lines = _lines("sdg-indicators", "ef0358f2cc8c.csv", "ef0358f2cc8c.ssa.csv")
    flags = _flags("sdg-indicators", "ef0358f2cc8c.flags.csv", sdg.FLAGS_MEMBER)
    obs, steps = sdg.observations(sdg.read(lines), flags)
    by = {(o.dims["commodity"], o.period): o.value for o in obs}
    assert len(obs) == 50 and {o.entity for o in obs} == {"WLD"}
    assert by[("total", "2015")] == 13.0 and by[("total", "2024")] == 13.4
    assert by[("fruits-and-vegetables", "2024")] == 26.4
    assert any("Sub-Saharan Africa" in s for s in steps)
    assert any("AG_FLS_IDX" in s for s in steps)


def test_food_loss_refuses_an_unknown_note_and_item():
    lines = _lines("sdg-indicators", "ef0358f2cc8c.csv")
    flags = _flags("sdg-indicators", "ef0358f2cc8c.flags.csv", sdg.FLAGS_MEMBER)
    noted = [ln.replace(b"Non-relevant | FAO", b"Revised | FAO") for ln in lines]
    with pytest.raises(FaostatBulkError, match="Note"):
        sdg.observations(sdg.read(noted), flags)
    renamed = [ln.replace(b'"24044-AGGS3001"', b'"24044-AGGS3009"') for ln in lines]
    with pytest.raises(FaostatBulkError, match="unknown"):
        sdg.observations(sdg.read(renamed), flags)


def test_food_loss_vintage_from_catalogue():
    updated, rows = catalogue_entry(CATALOGUE.read_bytes(), sdg.DATASET_CODE, _url("sdg-indicators"))
    assert updated.isoformat() == "2026-09-29"
    assert rows == _total_rows("sdg-indicators", "ef0358f2cc8c.csv")


# --- agrifood emissions by country ---------------------------------------------------------------------------------


def _gt():
    lines = _lines("emissions-totals", "d2c47e116553.csv", "d2c47e116553.brazil.csv", "d2c47e116553.china-group.csv")
    flags = _flags("emissions-totals", "d2c47e116553.flags.csv", gt.FLAGS_MEMBER)
    return gt.observations(gt.read(lines), flags)


def test_country_emissions_in_million_tonnes():
    obs, steps = _gt()
    by = {(o.entity, o.period): o.value for o in obs}
    assert {o.entity for o in obs} == {"WLD", "BRA"}
    # World 2023: 16,535,072.3737 kt in the file, the same value as the world indicator in Gt.
    assert by[("WLD", "2023")] == 16535.0723737
    assert len([o for o in obs if o.entity == "BRA"]) == 34
    assert any("China" in s and "FAO regional" in s for s in steps)
    assert Counter(o.note for o in obs) == Counter({None: len(obs)})


def test_country_emissions_scope_is_explicit():
    t = gt.transforms(Paths.default())[0]
    s = t.spec.scope
    assert (s.gwp, s.lulucf, s.bunkers) == ("AR5-GWP100", "included", "excluded")


@pytest.mark.snapshot
def test_agrifood_item_is_the_sum_of_its_three_parts():
    """The scope's bunkers="excluded" rests on this: in every FAO TIER 1 row of the release of 28 October 2025,
    Agrifood systems (6518) = Farm gate (6996) + Land-use change (6516) + Pre- and post-production (6517)."""
    import zipfile
    from decimal import Decimal

    from envdash import snapshots
    from envdash.transforms.food.faostat_bulk import read_member

    p = Paths.default()
    path = snapshots.cache_path(p, snapshots.read_current(p)["faostat/emissions-totals"])
    parts = {"6518", "6996", "6516", "6517"}
    with zipfile.ZipFile(path) as z, z.open(gt.DATA_MEMBER) as f:
        table = read_member(
            f,
            gt.DATA_MEMBER,
            gt.COLUMNS,
            lambda r: (
                r["Item Code"] in parts
                and r["Element Code"] == "723113"
                and r["Source"] == "FAO TIER 1"
                and r["Flag"] != "F"
            ),
            b'"723113"',
        )
    v: dict[tuple[str, str], dict[str, Decimal]] = {}
    for r in table.rows:
        v.setdefault((r["Area Code"], r["Year"]), {})[r["Item Code"]] = Decimal(r["Value"])
    checked = 0
    for d in v.values():
        if "6518" in d:
            assert abs(d["6518"] - sum(d.get(i, Decimal(0)) for i in ("6996", "6516", "6517"))) <= Decimal("0.0001")
            checked += 1
    assert checked == 9174


@pytest.mark.snapshot
def test_full_snapshots_build_all_faostat_country_indicators():
    from envdash import snapshots
    from envdash.transform import InputFile, validate

    p = Paths.default()
    cur = snapshots.read_current(p)
    for mod, ids in (
        (rl, {"land-use.faostat.area", "land-use.faostat.share-of-land-area"}),
        (sdg, {"food-loss.faostat.sdg-12-3-1a"}),
        (gt, {"food.faostat.agrifood-emissions-by-country"}),
    ):
        for t in mod.transforms(p):
            assert t.spec.id in ids
            files = {}
            for i in t.inputs:
                snap = snapshots.read_manifest(p, cur[i.key])
                assert snap is not None
                files[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
            r = t.run(files)
            validate(t, r.observations)
            assert r.vintage in {"2025-10-28", "2026-10-02", "2026-09-29"}

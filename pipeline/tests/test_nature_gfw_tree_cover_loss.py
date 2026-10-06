"""Tree cover loss from the Global Forest Watch Data API (envdash/transforms/nature/gfw_tree_cover_loss.py).

Fixtures are byte-exact slices of the four real downloads of 2026-10-06 (tests/fixtures/gfw-tree-cover-loss/, cut by
make_fixture.py; the world file is whole). The checks that need every row (countries adding up to the world, the codes
left out) read the full snapshots and are marked `snapshot`.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import geo, snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.nature import gfw_tree_cover_loss as gfw

FIXTURES = Path(__file__).parent / "fixtures" / "gfw-tree-cover-loss"
GLOBAL = FIXTURES / "79b791bcb241.csv"
COUNTRY = FIXTURES / "d2356e4f4d7a.csv"
DRIVERS = FIXTURES / "2e9dfe9bb94e.csv"
PRIMARY = FIXTURES / "ddb6c3ad59a6.csv"


def test_every_input_is_a_registered_artifact_with_its_key_header():
    src = load_registry(Paths.default()).sources[gfw.SOURCE]
    assert {a.id for a in src.artifacts} == {k.split("/")[1] for k in gfw.HEADERS}
    assert src.licence_class == "open"
    for a in src.artifacts:
        assert "umd_tree_cover_density_2000__threshold%20%3D%2030" in str(a.url)
        assert "v20260424" in str(a.url)


def test_world_file_reads_every_year_in_order():
    world = gfw.read_global(GLOBAL.read_bytes())
    assert list(world) == list(range(2001, 2026))
    loss, fire = world[2025]
    assert loss == Decimal("25528555.508701269910367848")
    assert fire == Decimal("10751917.898464413614003740")
    assert world[2024][0] == Decimal("29592479.103587252170925648")


def test_a_changed_header_stops_the_transform():
    raw = GLOBAL.read_bytes().replace(b'"umd_tree_cover_loss__ha"', b'"tree_cover_loss_ha"', 1)
    with pytest.raises(gfw.GfwFormatError, match="header"):
        gfw.read_global(raw)


def test_country_rows_keep_only_years_with_a_row():
    values, left, _ = gfw.read_country(COUNTRY.read_bytes(), gfw.COUNTRY.key, 2025, geo.table())
    assert left == {}
    # Aruba's first rows in the file are 2002, 2003 and 2006: 2001, 2004 and 2005 have no row and stay absent.
    aruba = sorted(y for e, d, y in values if e == "ABW" and d == "all")
    assert aruba[:3] == [2002, 2003, 2006]
    assert values[("ABW", "fire", 2006)] == Decimal("0.0")
    assert values[("ZWE", "all", 2025)] == Decimal("8528.51320080113098320")


def test_drivers_are_wris_eight_classes():
    values, _, _ = gfw.read_country(DRIVERS.read_bytes(), gfw.DRIVERS.key, 2025, geo.table())
    assert {d for _, d, _ in values} <= {d for d, _ in gfw.DRIVER_CLASSES}
    assert values[("ZWE", "wildfire", 2025)] == Decimal("778.00820498603105471")
    raw = DRIVERS.read_bytes().replace(b'"Wildfire"', b'"Wild fire"', 1)
    with pytest.raises(gfw.GfwFormatError, match="driver class"):
        gfw.read_country(raw, gfw.DRIVERS.key, 2025, geo.table())


def test_gadm_codes_resolve_through_the_alias_table():
    assert geo.resolve("XKO", gfw.SOURCE) == "KOS"
    assert geo.resolve("ZNC", gfw.SOURCE) == "CYN"
    with pytest.raises(geo.UnknownEntity):
        geo.resolve("Z01", gfw.SOURCE)


def test_a_year_after_the_world_file_stops_the_transform():
    with pytest.raises(gfw.GfwFormatError, match="outside"):
        gfw.read_country(PRIMARY.read_bytes(), gfw.PRIMARY.key, 2024, geo.table())


# --- full real downloads (snapshot cache) -------------------------------------------------------------------------


@pytest.mark.snapshot
def test_built_from_the_current_snapshots(tmp_paths):
    paths = Paths.default()
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{gfw.SOURCE}.yaml", tmp_paths.sources / f"{gfw.SOURCE}.yaml")
    for key in gfw.HEADERS:
        sha = snapshots.read_current(paths)[key]
        snap = snapshots.read_manifest(paths, sha)
        assert snap is not None
        rec, _ = snapshots.record(
            tmp_paths,
            data=snapshots.cache_path(paths, sha).read_bytes(),
            source_id=gfw.SOURCE,
            artifact_id=key.split("/")[1],
            url=str(snap.url),
            acquisition="automatic",
            today=snap.date_accessed,
        )
        snapshots.set_current(tmp_paths, {key: rec.sha256})
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id.startswith("forest.gfw.")]
    outs = {o.indicator.id: o for o in build_and_export(tmp_paths, reg, ts).outcomes if o.state == "built"}
    assert set(outs) == {
        "forest.gfw.tree-cover-loss",
        "forest.gfw.primary-forest-loss",
        "forest.gfw.tree-cover-loss-by-driver",
    }

    loss = outs["forest.gfw.tree-cover-loss"].indicator
    by = {(o.entity, o.period, o.dims["part"]): o.value for o in loss.observations}
    # The verified research figures (pipeline/sources/gfw-tree-cover-loss.yaml).
    assert round(by[("WLD", "2025", "all")], 1) == 25528555.5
    assert round(by[("WLD", "2025", "fire")], 1) == 10751917.9
    assert round(by[("WLD", "2024", "all")], 1) == 29592479.1
    assert ("KOS", "2025", "all") in by and ("CYN", "2025", "all") in by
    assert not {e for e, _, _ in by} & gfw.LEFT_OUT
    assert any("Z07" in p.description for p in loss.processing)

    primary = outs["forest.gfw.primary-forest-loss"].indicator
    assert round({o.period: o.value for o in primary.observations if o.entity == "WLD"}["2025"], 1) == 4286331.3

    drivers = outs["forest.gfw.tree-cover-loss-by-driver"].indicator
    total = {}
    for o in drivers.observations:
        if o.entity == "WLD":
            total[o.dims["driver"]] = total.get(o.dims["driver"], 0.0) + o.value
    # 2001-2025 totals by driver, in million hectares (research figures): permanent agriculture 172.3, wildfire 162.7.
    assert round(total["permanent-agriculture"] / 1e6, 1) == 172.3
    assert round(total["wildfire"] / 1e6, 1) == 162.7
    assert round(sum(total.values()) / 1e6, 1) == 542.8

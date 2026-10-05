"""Territorial and consumption-based fossil CO2 by country (gcb-2025-national, Global Carbon Budget 2025 v1.0).

The fixture tests/fixtures/gcb-2025-national/968097cacb1a.xlsx is the whole workbook (an xlsx is a zip archive, so no
line slice of it is a readable workbook); its sidecar records that the fixture sha256 equals the snapshot's.
"""

from __future__ import annotations

import io
import shutil
from decimal import Decimal

import openpyxl
import pytest

from envdash import geo, snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover
from envdash.transforms.emissions import gcb_national as gcb
from envdash.transforms.emissions import gcp_fossil_national as gcp
from envdash.validate import validate_all

from support import exported, fixture, load_fixture_snapshot

ID = "emissions.gcb-2025.territorial-vs-consumption"


def _raw() -> bytes:
    return fixture(gcb.SOURCE, "national-fossil")[0].read_bytes()


@pytest.fixture(scope="module")
def sheets() -> dict[str, gcb.Sheet]:
    return gcb.read_national(_raw())


def test_reads_both_sheets(sheets):
    ter, con = sheets[gcb.TERRITORIAL], sheets[gcb.CONSUMPTION]
    assert ter.years == tuple(range(1850, 2025))
    assert con.years == tuple(range(1990, 2025))
    codes = [c.entity for c in ter.columns if c is not None]
    assert len(codes) == 218  # 214 countries and territories, EU27, two bunker entities, the world
    assert {"EU27", "WLD", "INTL_SEA", "INTL_AIR", "KOS", "TWN", "PSE"} <= set(codes)
    skipped = [i for i, c in enumerate(ter.columns) if c is None]
    assert len(skipped) == len(gcb.NOT_ENTITIES)
    # 2024 world territorial, in MtC as stored (the same as the Global Carbon Budget's gross fossil value).
    assert round(ter.values[("WLD", 2024)], 4) == Decimal("10534.5464")
    # Country consumption values end in 2023; the world and international transport continue to 2024.
    assert ("USA", 2024) not in con.values and ("USA", 2023) in con.values
    assert ("WLD", 2024) in con.values and ("INTL_SEA", 2024) in con.values


def test_world_matches_the_fossil_dataset(sheets):
    """GCB's national file and the GCP flat file are the same national series (to the flat file's six decimals)."""
    flat = gcp.read_flat(fixture(gcp.SOURCE, "mtco2-flat")[0].read_bytes())
    world = {r.year: r.cells["Total"] for r in flat if r.entity == "WLD"}
    obs = {(o.entity, o.period, o.dims["accounting"]): o.value for o in gcb.observations(sheets)}
    for y in (1990, 2000, 2023, 2024):
        assert obs[("WLD", str(y), "territorial")] == pytest.approx(float(world[y]), abs=5e-7)
    for code in ("ALB", "ARG", "ARM", "INTL_SEA", "INTL_AIR"):
        flat_2023 = next(r.cells["Total"] for r in flat if r.entity == code and r.year == 2023)
        assert obs[(code, "2023", "territorial")] == pytest.approx(float(flat_2023), abs=5e-7)


def test_shares_match_the_global_carbon_budget_paper(sheets):
    """ESSD 18, 3211-3288 (2026), p. 23: 'In 2024, the largest absolute contributions to global fossil CO2 emissions
    were from China (32 %), the USA (13 %), India (8 %), and the EU27 (6 %).' and '... international aviation and
    marine bunker fuels (3 % of the total).' A regression test of our reading of the territorial sheet."""
    ter = sheets[gcb.TERRITORIAL].values
    world = ter[("WLD", 2024)]
    pct = {c: ter[(c, 2024)] / world * 100 for c in ("CHN", "USA", "IND", "EU27")}
    assert {c: round(v) for c, v in pct.items()} == {"CHN": 32, "USA": 13, "IND": 8, "EU27": 6}
    assert round((ter[("INTL_SEA", 2024)] + ter[("INTL_AIR", 2024)]) / world * 100) == 3


def test_observations_convert_with_the_sheet_factor(sheets):
    obs = gcb.observations(sheets)
    by = {(o.entity, o.period, o.dims["accounting"]): o for o in obs}
    con = sheets[gcb.CONSUMPTION].values
    assert by[("USA", "2023", "consumption")].value == float(con[("USA", 2023)] * Decimal("3.664"))
    assert round(by[("USA", "2023", "consumption")].value, 3) == 5431.659
    assert round(by[("USA", "2023", "territorial")].value, 3) == 4918.407
    assert {o.period for o in obs} == {str(y) for y in range(1990, 2025)}
    assert by[("FRA", "2023", "territorial")].note == "The file's column header reads 'FRANCE (INCLUDING MONACO)'."
    assert by[("ITA", "2023", "consumption")].note == ("The file's column header reads 'ITALY (INCLUDING SAN MARINO)'.")
    # Panama's consumption-based emissions are negative in some years in the file; they are published as stated.
    assert by[("PAN", "2006", "consumption")].value < 0
    # Empty cells are not published: Afghanistan has no consumption-based values.
    assert not any(e == "AFG" and a == "consumption" for e, _, a in by)
    assert len(obs) == 11_807


def test_transfers_sheet_has_the_opposite_sign_to_the_paper():
    """The module text says why transfers are not published; this pins the counts it states."""
    wb = openpyxl.load_workbook(io.BytesIO(_raw()), read_only=True)
    ter, con, tra = (gcb._rows(wb, s) for s in (gcb.TERRITORIAL, gcb.CONSUMPTION, "Emissions Transfers"))
    names = ter[11]
    width = max(i for i, n in enumerate(names) if n is not None) + 1
    t_rows = {r[0]: r for r in ter if isinstance(r[0], int)}
    counts = {"territorial-minus-consumption": 0, "neither": 0}
    for row in (r for r in tra if isinstance(r[0], int)):
        y = row[0]
        c_row = next(r for r in con if r[0] == y)
        for i in range(1, width):
            if names[i] in gcb.NOT_ENTITIES:
                continue
            a, b, c = t_rows[y][i], c_row[i], row[i]
            if a is None or b is None or c is None:
                continue
            A, B, C = (Decimal(repr(x)) for x in (a, b, c))
            key = "territorial-minus-consumption" if abs(A - B - C) < Decimal("1e-6") else "neither"
            counts[key] += 1
    assert counts == {"territorial-minus-consumption": 4202, "neither": 3}


def test_eu27_must_be_the_27_member_states():
    wb = openpyxl.load_workbook(io.BytesIO(_raw()), read_only=True)
    rows = gcb._rows(wb, gcb.REGIONS)
    assert gcb.read_eu27(rows, None) == geo.EU27_MEMBERS
    eu_row = next(r for r in rows if r[0] == "EU27")
    shorter = [(r[0], eu_row[1].replace("Austria, ", "")) if r[0] == "EU27" else r for r in rows]
    assert gcb.read_eu27(shorter, None) != geo.EU27_MEMBERS


def test_aliases_point_at_entities_and_never_contradict_the_name_column():
    t = geo.table()
    for name, code in gcb.ALIASES.items():
        assert geo.entity(code, entities=t)
        try:
            by_name = geo.resolve(name, "name", entities=t)
        except geo.UnknownEntity:
            continue
        assert by_name == code, name  # "World" is declared although the name column has it too
    assert not set(gcb.ALIASES) & gcb.NOT_ENTITIES


def _paths(tmp_paths: Paths) -> Paths:
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{gcb.SOURCE}.yaml", tmp_paths.sources)
    load_fixture_snapshot(tmp_paths, gcb.SOURCE, "national-fossil")
    return tmp_paths


def test_build_exports_a_valid_indicator(tmp_paths):
    paths = _paths(tmp_paths)
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id == ID]
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"], [o.reason for o in report.outcomes]
    ind = exported(paths.public_indicators / f"{ID}.json")
    assert ind["vintage"] == "2025 v1.0"
    assert ind["latest"]["dims"] == {"accounting": "territorial"} and ind["latest"]["period"] == "2024"
    assert [v["id"] for v in ind["dimensions"][0]["values"]] == ["territorial", "consumption"]
    assert ind["scope"]["lulucf"] == "excluded" and ind["scope"]["bunkers"] == "excluded"
    assert "Changes: converted from million tonnes of carbon" in ind["attribution"]
    assert "Peters, Davis and Andrew (2012)" in ind["notice"]
    assert validate_all(paths, reg) == []


def test_unpinned_object_is_refused(tmp_paths):
    paths = _paths(tmp_paths)
    sha = snapshots.read_current(paths)[gcb.NATIONAL.key]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    other = snap.model_copy(update={"url": "https://data.icos-cp.eu/objects/AnotherObjectId"})
    (t,) = [t for t in discover(paths) if t.spec.id == ID]
    with pytest.raises(gcb.GcbNationalFormatError, match="not a pinned"):
        t.run({gcb.NATIONAL.key: InputFile(snapshots.cache_path(paths, sha), other)})


def test_pinned_object_is_the_registered_artifact():
    src = load_registry(Paths.default()).sources[gcb.SOURCE]
    assert set(gcb.PINNED) <= {str(a.url) for a in src.artifacts}
    assert src.licence_class == "open"


@pytest.mark.snapshot
def test_names_resolve_to_the_same_entities_as_the_fossil_dataset():
    """Every country column of the national file maps to the entity the flat file's ISO code maps to."""
    paths = Paths.default()
    current = snapshots.read_current(paths)
    flat = gcp.read_flat(snapshots.cache_path(paths, current[gcp.FLAT.key]).read_bytes())
    by_name = {r.country: r.entity for r in flat}
    sheets = gcb.read_national(snapshots.cache_path(paths, current[gcb.NATIONAL.key]).read_bytes())
    checked = 0
    for col in sheets[gcb.TERRITORIAL].columns:
        if col is not None and col.name in by_name:
            assert col.entity == by_name[col.name], col
            checked += 1
    assert checked == 216  # every column but EU27 and World, whose flat-file names differ ("Global")

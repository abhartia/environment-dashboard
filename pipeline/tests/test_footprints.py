"""Personal (consumption) footprints as their producers publish them: Naturvårdsverket's per-person footprint for
Sweden by consumption area (envdash/transforms/footprints/naturvardsverket.py) and Defra's UK carbon footprint
(envdash/transforms/footprints/defra_uk.py).

Fixtures:
- Defra: the whole UK dataset ODS (98,019 bytes, OGL v3), cut with make_fixture.py --whole, so the full build runs in
  CI.
- Naturvårdsverket: only the bytes of the chart's data.csv inside the page snapshot (881 bytes), cut by
  tests/fixtures/naturvardsverket-consumption-footprint/make_payload_fixture.py. The page itself is not committed
  (mirror_raw false: the open terms cover the statistics, not the page's prose), so tests of the whole page read the
  snapshot cache and are marked snapshot.
"""

from __future__ import annotations

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import canonical, snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.footprints import defra_uk as defra
from envdash.transforms.footprints import naturvardsverket as nv
from envdash.validate import validate_all

from support import exported, fixture, load_fixture_snapshot

NV_FIXTURES = Path(__file__).parent / "fixtures" / nv.SOURCE
NV_SIDECARS = sorted(NV_FIXTURES.glob("*/*.provenance.json"))
DEFRA_IDS = ("footprint.defra.by-end-use", "footprint.defra.households-by-product", "footprint.defra.per-capita")
NV_IDS = ("footprint.naturvardsverket.per-person-by-area", "footprint.naturvardsverket.per-person-total")


def _defra_raw() -> bytes:
    path, _ = fixture(defra.SOURCE, "uk-dataset")
    return path.read_bytes()


def _nv_csv() -> str:
    sys.path.insert(0, str(NV_FIXTURES))
    from make_payload_fixture import decode

    (side,) = NV_SIDECARS
    return decode(side.with_name(side.name.removesuffix(".provenance.json")).read_bytes())


def _current_file(source_id: str, artifact_id: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[snapshots.key(source_id, artifact_id)]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(p, sha), snap)


# --- Naturvårdsverket fixture ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", NV_SIDECARS, ids=lambda p: p.name)
def test_nv_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == nv.SOURCE
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes", "byte_range"):
        assert meta[k]
    start, end = meta["byte_range"]
    assert end - start == meta["fixture_bytes"]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    # Open data; the page is not re-hosted (mirror_raw false), so the fixture holds the data payload only.
    assert src.licence_class == "open" and not src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", NV_SIDECARS, ids=lambda p: p.name)
def test_nv_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(NV_FIXTURES))
    from make_payload_fixture import cut, decode, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    assert parse_command(meta["command"]) == meta["artifact_id"]
    sliced, info = cut(raw)
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]
    assert info["byte_range"] == meta["byte_range"] and raw[slice(*meta["byte_range"])] == sliced
    # The payload is exactly what the transform reads from the whole page.
    assert decode(sliced) == nv.chart(nv.page_model(raw)).csv


# --- Naturvårdsverket: parsing and additivity --------------------------------------------------------------------


def test_nv_csv_reads_every_year_as_printed():
    rows = nv.read_csv(_nv_csv())
    assert list(rows) == list(range(2008, 2024))
    r = rows[2023]
    assert [r[sv] for _, sv, _ in nv.AREAS] == [Decimal(x) for x in ("1.37", "1.35", "1", "0.98", "0.83", "2.09")]
    assert r[nv.TOTAL] == Decimal("7.62")
    assert rows[2008][nv.TOTAL] == Decimal("11.92")


def test_nv_parts_add_to_the_published_total_within_rounding():
    rows = nv.read_csv(_nv_csv())
    diffs = nv.rounding_years(rows)
    # Exact in 11 of 16 years; the producer's two-decimal rounding leaves 0.01 t in the other five.
    assert diffs == {
        2009: Decimal("0.01"),
        2010: Decimal("0.01"),
        2020: Decimal("0.01"),
        2021: Decimal("-0.01"),
        2022: Decimal("-0.01"),
    }
    for year in (2008, 2023):
        assert sum(rows[year][sv] for _, sv, _ in nv.AREAS) == rows[year][nv.TOTAL]
    # Households' four areas and the two that are not personal choices, 2023 (the page: 'närmare fem ton').
    household = sum(rows[2023][sv] for aid, sv, _ in nv.AREAS[:4])
    assert household == Decimal("4.70")
    assert [aid for aid, _, _ in nv.AREAS[4:]] == ["public-consumption", "investment"]


def test_nv_parts_beyond_rounding_are_refused():
    text = _nv_csv().replace("2023;1.37;", "2023;1.47;")
    with pytest.raises(nv.NaturvardsverketFormatError, match="differ from Totalt"):
        nv.rounding_years(nv.read_csv(text))


def test_nv_changed_header_is_refused():
    with pytest.raises(nv.NaturvardsverketFormatError, match="CSV header"):
        nv.read_csv(_nv_csv().replace('"Livsmedel "', '"Mat "'))


def test_nv_transforms_declare_their_registered_input():
    ts = nv.transforms(Paths.default())
    assert tuple(t.spec.id for t in ts) == NV_IDS
    src = load_registry(Paths.default()).sources[nv.SOURCE]
    for t in ts:
        assert t.inputs == (nv.PAGE,) and nv.PAGE.artifact_id in {a.id for a in src.artifacts}
        assert t.spec.headline_entity == "SWE" and t.spec.scope.gwp is None
        assert "not stated" in (t.spec.scope.basis or "")
    by_area = ts[0].spec
    labels = {v.id: v.label for v in by_area.dimensions[0].values}
    for _, sv, _ in nv.AREAS:  # the Swedish original is kept in every label
        assert any(f"({sv})" in label for label in labels.values())
    assert "not personal choices" in by_area.description and "0.01 t" in by_area.description


@pytest.mark.snapshot
def test_nv_every_value_from_the_real_page():
    f = _current_file(nv.SOURCE, nv.PAGE.artifact_id)
    by_area, total = nv.transforms(Paths.default())
    r = by_area.run({nv.PAGE.key: f})
    validate(by_area, r.observations)
    assert len(r.observations) == 6 * 16
    assert r.vintage == "2008-2023 series, page reviewed 2025-10-28"
    got = {(o.dims["area"], o.period): o.value for o in r.observations}
    assert got[("food", "2023")] == 1.35 and got[("investment", "2008")] == 3.3
    r = total.run({nv.PAGE.key: f})
    validate(total, r.observations)
    assert {o.period: o.value for o in r.observations}["2023"] == 7.62
    assert r.changes is None


# --- Defra: parsing and additivity -----------------------------------------------------------------------------------


def test_defra_cover_sheet_states_the_licence_and_release():
    sheets = defra.read_sheets(_defra_raw())
    cover = defra.read_cover(sheets)
    assert cover.published == "30 June 2026"
    src = load_registry(Paths.default()).sources[defra.SOURCE]
    texts = {c.text for c in sheets["Cover_sheet"].values()}
    assert src.evidence.licence_quote in texts


def test_defra_per_capita_as_published():
    wb = defra.read_workbook(_defra_raw())
    assert (wb.first, wb.last) == (1990, 2023)
    col = "Greenhouse gases (tCO2e per capita)"
    assert wb.annual[2023][col] == Decimal("10.2034271610218")
    assert wb.annual[1990][col] == Decimal("16.093668607136319")


def test_defra_end_use_rows_add_to_the_total():
    wb = defra.read_workbook(_defra_raw())
    rows, total = defra.read_end_use(wb.sheets, 2023, wb.notes)
    assert [i for i, _, _ in rows] == [i for i, _ in defra.END_USES]
    assert dict(defra.END_USES)["recreation-and-communication"] == "Recreation and communication"
    kt = {i: v for i, v, _ in rows}
    assert kt["food-and-beverages"] == Decimal("74731.841880585023")
    assert kt["transportation"] == Decimal("150436.05758655776")
    assert total == Decimal("699201.91686335055")
    assert abs(sum(kt.values()) - total) < Decimal("1e-6")
    # The first eleven rows are households' part: they equal Households + Households direct.
    households = defra.read_final_demand(wb.sheets, 1990, 2023)[2023]
    assert abs(sum(v for _, v, _ in rows[:11]) - households) < Decimal("1e-6")
    notes = {i: n for i, _, n in rows}
    assert notes["health"] is not None and notes["health"].startswith("Defra note 3: For some product categories")
    assert notes["central-and-local-government"].count("Defra note") == 2
    assert notes["food-and-beverages"] is None


def test_defra_products_add_to_the_household_total():
    wb = defra.read_workbook(_defra_raw())
    values, totals, notes = defra.read_products(wb.sheets, 1990, 2023, wb.notes)
    households = defra.read_final_demand(wb.sheets, 1990, 2023)
    assert len(values) == 34 and all(len(v) == 34 for v in values.values())
    assert totals[2023] == Decimal("528626.10144782555")
    for y in values:
        assert abs(sum(values[y].values()) - totals[y]) < Decimal("1e-6")
        assert abs(totals[y] - households[y]) < Decimal("1e-6")
    # Food plus non-alcoholic beverages is exactly the end-use row 'Food and beverages' (2023), which therefore
    # excludes alcohol, tobacco and restaurants and hotels.
    rows, _ = defra.read_end_use(wb.sheets, 2023, wb.notes)
    end_use = {i: v for i, v, _ in rows}
    v = values[2023]
    assert abs(v["food"] + v["non-alcoholic-beverages"] - end_use["food-and-beverages"]) < Decimal("1e-6")
    assert abs(v["alcoholic-beverages"] + v["tobacco"] - end_use["alcohol-and-tobacco"]) < Decimal("1e-6")
    assert v["restaurants-and-hotels"] == end_use["hotels-and-restaurants"]
    assert notes["hospital-services"] is not None and notes["food"] is None


def test_defra_note_markers_split_from_labels():
    assert defra.split_label("Health [note 3]") == ("Health", ["note 3"])
    assert defra.split_label("Central and local government [notes 4 and 5]") == (
        "Central and local government",
        ["note 4", "note 5"],
    )
    assert defra.split_label("Food and beverages") == ("Food and beverages", [])


def test_defra_run_converts_to_million_tonnes_and_notes_early_years():
    f = InputFile(fixture(defra.SOURCE, "uk-dataset")[0], _defra_snapshot())
    per_capita, by_end_use, households = (
        next(t for t in defra.transforms(Paths.default()) if t.spec.id == i)
        for i in ("footprint.defra.per-capita", "footprint.defra.by-end-use", "footprint.defra.households-by-product")
    )
    r = per_capita.run({defra.DATASET.key: f})
    validate(per_capita, r.observations)
    pc = {o.period: o for o in r.observations}
    assert pc["2023"].value == 10.2034271610218 and pc["2023"].note is None
    assert all(pc[str(y)].note and "1990 to 1996" in pc[str(y)].note for y in range(1990, 1997))
    assert pc["1997"].note is None and r.changes is None
    r = by_end_use.run({defra.DATASET.key: f})
    validate(by_end_use, r.observations)
    assert {o.period for o in r.observations} == {"2023"}
    eu = {o.dims["end_use"]: o.value for o in r.observations}
    assert eu["food-and-beverages"] == float(Decimal("74731.841880585023") / 1000)
    assert r.changes and "million tonnes" in r.changes
    r = households.run({defra.DATASET.key: f})
    validate(households, r.observations)
    assert len(r.observations) == 34 * 34
    hp = {(o.dims["product"], o.period): o for o in r.observations}
    assert hp[("food", "2023")].value == float(Decimal("71054.595493222805") / 1000)
    assert "1990 to 1996" in (hp[("food", "1990")].note or "")


def _defra_snapshot():
    p = Paths.default()
    _, meta = fixture(defra.SOURCE, "uk-dataset")
    snap = snapshots.read_manifest(p, meta["full_sha256"])
    assert snap is not None
    return snap


def test_defra_changed_end_use_label_is_refused():
    wb = defra.read_workbook(_defra_raw())
    sheet = dict(wb.sheets["Summary_2023"])
    ((rc, cell),) = [(rc, c) for rc, c in sheet.items() if c.text == "Recreation and communication"]
    sheet[rc] = defra.Cell(cell.value, "Recreation")
    with pytest.raises(defra.DefraFormatError, match="Table 3 rows"):
        defra.read_end_use({**wb.sheets, "Summary_2023": sheet}, 2023, wb.notes)


def test_defra_build_exports_publicly(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{defra.SOURCE}.yaml", tmp_paths.sources)
    sha = load_fixture_snapshot(tmp_paths, defra.SOURCE, "uk-dataset")
    assert sha == fixture(defra.SOURCE, "uk-dataset")[1]["full_sha256"]  # the whole file
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id in DEFRA_IDS]
    report = build_and_export(tmp_paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"] * 3, [o.reason for o in report.outcomes]
    ind = exported(tmp_paths.public_indicators / "footprint.defra.by-end-use.json")
    assert ind["licence_class"] == "open" and ind["scope"]["gwp"] == "AR5-GWP100"
    assert ind["latest"]["dims"] == {"end_use": "food-and-beverages"} and ind["latest"]["period"] == "2023"
    assert "Open Government Licence v3.0" in ind["attribution"]
    assert "Changes: converted from thousand tonnes to million tonnes" in ind["attribution"]
    pc = exported(tmp_paths.public_indicators / "footprint.defra.per-capita.json")
    assert pc["latest"]["value"] == 10.2034271610218 and pc["vintage"].endswith("published 30 June 2026")
    assert validate_all(tmp_paths, reg) == []


@pytest.mark.snapshot
def test_nv_build_exports_publicly(tmp_paths):
    real = Paths.default()
    paths = tmp_paths.with_(cache=real.cache)
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{nv.SOURCE}.yaml", paths.sources)
    paths.snapshot_manifests.mkdir(parents=True)
    k = nv.PAGE.key
    sha = snapshots.read_current(real)[k]
    shutil.copy(snapshots.manifest_path(real, sha), snapshots.manifest_path(paths, sha))
    snapshots.set_current(paths, {k: sha})
    reg = load_registry(paths)
    report = build_and_export(paths, reg, [t for t in discover(paths) if t.spec.id in NV_IDS])
    assert [o.state for o in report.outcomes] == ["built"] * 2, [o.reason for o in report.outcomes]
    ind = exported(paths.public_indicators / "footprint.naturvardsverket.per-person-total.json")
    assert ind["latest"]["value"] == 7.62 and ind["latest"]["period"] == "2023"
    assert "Statistics Sweden (SCB)" in ind["attribution"]
    assert validate_all(paths, reg) == []

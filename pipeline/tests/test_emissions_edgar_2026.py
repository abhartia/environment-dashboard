"""EDGAR 2026 transforms (envdash/transforms/emissions/edgar_2026.py).

The source is class no-derivatives (IEA-EDGAR CO2 is CC BY-NC-ND 4.0), so no fixture may be cut from it (AGENTS.md
rule 9; tests/fixtures/make_fixture.py refuses other classes). The value tests read the full real booklet and report
from the snapshot cache and are marked `snapshot` (run with `uv run pytest -m snapshot`). The expected numbers are the
cells of the workbook as stored, and the report's own printed values for the same vintage.
"""

from __future__ import annotations

import io
import json
import shutil

import openpyxl
import pytest

from envdash import geo, snapshots, textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover
from envdash.transforms.emissions import edgar_2026 as ed
from envdash.validate import validate_all

from support import exported

SOURCE = "edgar-2026-ghg"
IDS = {
    "ghg.edgar-2026.total-by-country",
    "ghg-per-capita.edgar-2026.by-country",
    "ghg-gas-share.edgar-2026.global",
    "ghg-sector-change.edgar-2026.global",
}


def _current(artifact_id: str) -> tuple[bytes, InputFile]:
    p = Paths.default()
    sha = snapshots.read_current(p)[snapshots.key(SOURCE, artifact_id)]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    path = snapshots.cache_path(p, sha)
    return path.read_bytes(), InputFile(path, snap)


def _files() -> dict[str, InputFile]:
    return {ed.BOOKLET.key: _current("ghg-booklet")[1], ed.REPORT.key: _current("report-pdf")[1]}


def _transform(indicator_id: str):
    return next(t for t in ed.transforms(Paths.default()) if t.spec.id == indicator_id)


def _by(obs, entity: str) -> dict:
    return {o.period: o for o in obs if o.entity == entity}


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_transforms_declare_registered_inputs_and_scopes():
    paths = Paths.default()
    ts = {t.spec.id: t for t in ed.transforms(paths)}
    assert set(ts) == IDS
    src = load_registry(paths).sources[SOURCE]
    assert src.licence_class == "no-derivatives" and not src.obligations.mirror_raw
    urls = {a.id: str(a.url) for a in src.artifacts}
    assert urls["ghg-booklet"] == ed.BOOKLET_URL and urls["report-pdf"] == ed.REPORT_URL
    for t in ts.values():
        assert {i.source_id for i in t.inputs} == {SOURCE}
        assert {i.artifact_id for i in t.inputs} <= set(urls)
        s = t.spec.scope
        assert (s.gwp, s.lulucf, s.bunkers) == ("AR5-GWP100", "excluded", "included"), t.spec.id
    for t in (ts["ghg.edgar-2026.total-by-country"], ts["ghg-per-capita.edgar-2026.by-country"]):
        assert [c.vintage for c in t.checks] == [ed.VINTAGE] * 4
        assert all(c.url == ed.REPORT_URL for c in t.checks)


def test_entity_tables_match_the_crosswalk():
    for code, (_, ours) in ed.ALIASES.items():
        assert geo.resolve(ours, "iso3") == ours, code
    for code in ed.COMBINED:
        assert geo.entity(code).kind == "country"
    assert not set(ed.ALIASES) & set(ed.COMBINED)
    # Rows once withheld for want of an entity: published since envdash/geo.py declares one.
    years = (1.0,) * (ed.LAST_YEAR - ed.FIRST_YEAR + 1)
    assert ed.entity_for(ed.Row("SCG", "Serbia and Montenegro", years)) == ("SRB_MNE", None)
    assert ed.entity_for(ed.Row("GUF", "French Guiana", years)) == ("GUF", None)
    assert ed.entity_for(ed.Row("REU", "Réunion", years)) == ("REU", None)


def test_undeclared_code_is_refused():
    row = ed.Row("XYZ", "Nowhere", (1.0,) * (ed.LAST_YEAR - ed.FIRST_YEAR + 1))
    with pytest.raises(geo.UnknownEntity):
        ed.entity_for(row)
    renamed = ed.Row("FRA", "France", row.values)
    with pytest.raises(ed.EdgarFormatError, match="not 'France and Monaco'"):
        ed.entity_for(renamed)


# --- full real files (snapshot cache) -----------------------------------------------------------------------------


@pytest.mark.snapshot
def test_totals_are_the_cells_unchanged():
    result = _transform("ghg.edgar-2026.total-by-country").run(_files())
    obs = result.observations
    assert result.vintage == ed.VINTAGE
    wld, chn = _by(obs, "WLD"), _by(obs, "CHN")
    assert len(wld) == 56 and min(wld) == "1970" and max(wld) == "2025"
    assert wld["2025"].value == 54149.174008064
    assert wld["1970"].value == 23146.134487022
    assert chn["2025"].value == 15980.974040899
    assert _by(obs, "INTL_AIR")["1970"].value == 172.47606465851
    assert _by(obs, "CUW")["2025"].value is not None
    assert wld["2025"].status == "preliminary" and wld["2024"].status == "preliminary"
    assert wld["2023"].status == "final" and wld["2023"].note is None
    assert wld["2025"].note == ed.FAST_TRACK_NOTE
    fra = _by(obs, "FRA")
    assert fra["1990"].note == 'EDGAR reports this row as "France and Monaco": the value covers them together.'
    assert fra["2025"].note.endswith(ed.FAST_TRACK_NOTE)
    entities = {o.entity for o in obs}
    assert {"SRB_MNE", "GUF", "REU"} <= entities and not entities & {"SCG", "SRB", "MNE"}
    # Every one of the 212 coded rows; 56 years each.
    assert len(entities) == 212 and len(obs) == 212 * 56
    assert any('SCG "Serbia and Montenegro" is SRB_MNE' in s for s in result.steps)


@pytest.mark.snapshot
def test_the_world_row_is_the_sum_of_the_others_as_published():
    # Not used to publish anything (no sums of ours): it shows that GLOBAL TOTAL includes international aviation and
    # shipping, as the report says.
    raw, _ = _current("ghg-booklet")
    rows = ed.read_sheet(ed._cells(raw, (ed.TOTALS_SHEET,))[ed.TOTALS_SHEET], ed.TOTALS_SHEET)
    world = next(r for r in rows if r.code == "GLOBAL TOTAL")
    parts = [r for r in rows if r.code not in ("GLOBAL TOTAL", "EU27")]
    assert sum(r.values[-1] for r in parts) == pytest.approx(world.values[-1], abs=1e-6)


@pytest.mark.snapshot
def test_per_capita_cells_unchanged():
    obs = _transform("ghg-per-capita.edgar-2026.by-country").run(_files()).observations
    assert _by(obs, "WLD")["2025"].value == 6.6157426936634
    assert _by(obs, "USA")["2025"].value == 17.533032996426
    assert not {o.entity for o in obs} & {"INTL_AIR", "INTL_SEA"}
    # SRB_MNE, GUF and REU included.
    assert len({o.entity for o in obs}) == 210


@pytest.mark.snapshot
def test_publisher_checks_are_printed_on_their_profile_pages():
    raw, _ = _current("report-pdf")
    pages = ed.report_pages(raw, {page for *_, page in ed.PROFILE_ROWS})
    for entity, period, total, per_capita, row, page in ed.PROFILE_ROWS:
        assert textmatch.contains(pages[page], row), (entity, row)
        assert row.split()[:3] == [period, total, per_capita]
    t = _transform("ghg.edgar-2026.total-by-country")
    assert [c.quote for c in t.checks] == [r[4] for r in ed.PROFILE_ROWS]


@pytest.mark.snapshot
def test_gas_shares_quoted_and_confirmed_on_the_world_profile():
    result = _transform("ghg-gas-share.edgar-2026.global").run(_files())
    shares = {o.dims["gas"]: o.value for o in result.observations}
    assert shares == {"fossil-co2": 73.8, "ch4": 17.6, "n2o": 5.3, "f-gases": 3.3}
    assert all(o.period == "2025" and o.status == "preliminary" for o in result.observations)
    assert result.published_value is not None and result.published_value.quote == ed.GAS_QUOTE.text


@pytest.mark.snapshot
def test_gas_share_disagreement_is_refused():
    raw, _ = _current("report-pdf")
    pages = ed.report_pages(raw, {11, ed.WORLD_PROFILE_PAGE})
    pages[ed.WORLD_PROFILE_PAGE] = pages[ed.WORLD_PROFILE_PAGE].replace("CH4 17.6", "CH4 17.5")
    with pytest.raises(ed.EdgarFormatError, match="CH4"):
        ed.gas_shares(pages)


@pytest.mark.snapshot
def test_sector_changes_as_printed():
    result = _transform("ghg-sector-change.edgar-2026.global").run(_files())
    ch = {(o.dims["sector"], o.dims["since"]): o.value for o in result.observations}
    assert len(ch) == 24
    assert ch[("all-sectors", "1990")] == 68 and ch[("all-sectors", "2005")] == 33 and ch[("all-sectors", "2024")] == 1
    assert ch[("power-industry", "1990")] == 106 and ch[("power-industry", "2024")] == 0
    assert ch[("buildings", "1990")] == -4 and ch[("buildings", "2005")] == -2
    assert ch[("transport", "1990")] == 86
    assert result.published_value is not None
    assert result.published_value.quote.startswith("2025 vs 1990 2025 vs 2005 2025 vs 2024 Power Industry +106%")


@pytest.mark.snapshot
def test_a_changed_unit_statement_is_refused():
    raw, _ = _current("ghg-booklet")
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    cells = [c for r in wb["info"].iter_rows() for c in r if isinstance(c.value, str) and "Mt CO2eq/yr" in c.value]
    assert len(cells) == 3
    for c in cells:
        c.value = c.value.replace("Mt CO2eq/yr", "kt CO2eq/yr")
    out = io.BytesIO()
    wb.save(out)
    sheets = ed._cells(out.getvalue(), (ed.TOTALS_SHEET,))
    with pytest.raises(ed.EdgarFormatError, match="info sheet no longer says"):
        ed.check_statements(sheets)


@pytest.mark.snapshot
def test_another_file_is_refused():
    files = _files()
    snap = files[ed.BOOKLET.key].snapshot
    other = snap.model_copy(update={"url": "https://edgar.jrc.ec.europa.eu/booklet/EDGAR_2027_GHG_booklet_2027.xlsx"})
    files[ed.BOOKLET.key] = InputFile(files[ed.BOOKLET.key].path, other)
    with pytest.raises(ed.EdgarFormatError, match="not the EDGAR 2026 file"):
        _transform("ghg.edgar-2026.total-by-country").run(files)


@pytest.mark.snapshot
def test_build_exports_privately_with_passing_checks(tmp_paths):
    real = Paths.default()
    paths = tmp_paths.with_(cache=real.cache)
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{SOURCE}.yaml", paths.sources)
    paths.snapshot_manifests.mkdir(parents=True)
    pointers = {}
    for art in ("ghg-booklet", "report-pdf"):
        k = snapshots.key(SOURCE, art)
        sha = snapshots.read_current(real)[k]
        shutil.copy(snapshots.manifest_path(real, sha), snapshots.manifest_path(paths, sha))
        pointers[k] = sha
    snapshots.set_current(paths, pointers)
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id in IDS]
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"] * 4, [o.reason for o in report.outcomes]
    assert {c.status for o in report.outcomes for c in o.checks} == {"pass"}
    for i in IDS:
        assert (paths.private_indicators / f"{i}.json").exists()
        assert not (paths.public_indicators / f"{i}.json").exists()
        assert not (paths.public_indicators / f"{i}.csv").exists()
    total = exported(paths.private_indicators / "ghg.edgar-2026.total-by-country.json")
    assert total["licence_class"] == "no-derivatives"
    assert total["latest"] == {"entity": "WLD", "period": "2025", "value": 54149.174008064, "status": "preliminary",
                               "dims": {}, "age_bp": None}  # fmt: skip
    assert "Changes:" not in total["attribution"]
    catalog = json.loads((paths.data / "v1" / "catalog.json").read_text())
    assert all(e["latest"] is None and not e["downloadable"] for e in catalog["indicators"] if e["id"] in IDS)
    assert validate_all(paths, reg) == []

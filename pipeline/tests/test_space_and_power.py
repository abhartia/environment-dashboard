"""How much space, and how much power: land per unit of electricity (Lovering et al. 2022), power density (Nøland et
al. 2022), and the power scale from a home to the world (EIA RECS 2020, DESNZ subnational electricity, EIA FAQ 207,
Ember yearly demand, EIA international primary energy).

Fixtures (each with its .provenance.json sidecar, all cut from the snapshots of 2026-10-08 or the registered ones):
- lovering-2022: the whole article XML and the whole article PDF;
- noland-2022: the whole article PDF;
- eia-recs-2020: the whole Table CE2.1 workbook and the whole consumption technical documentation PDF;
- eia-faq-nuclear-plants: lines 147-153 of the FAQ page (the answer);
- desnz-subnational-electricity/workbook: five whole members of the workbook zip (workbook.xml, its relationships,
  sharedStrings.xml, the cover sheet and the 2024 sheet), cut by zip_member_fixture.py; their sidecars sit one level
  down, so their checks run here;
- the existing ember-yearly and eia-international fixtures.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from envdash import canonical, power, snapshots, textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover, validate
from envdash.transforms.energy import desnz_subnational as desnz
from envdash.transforms.energy import eia_faq_nuclear as faq
from envdash.transforms.energy import eia_international as eia
from envdash.transforms.energy import eia_recs as recs
from envdash.transforms.energy import ember_demand as ember
from envdash.transforms.energy import lovering_2022 as lov
from envdash.transforms.energy import noland_2022 as nol
from envdash.validate import validate_all

from support import FIXTURES, exported, fixture

DESNZ_SIDECARS = sorted((FIXTURES / "desnz-subnational-electricity" / "workbook").glob("*.provenance.json"))


def _bytes(source: str, artifact: str) -> bytes:
    path, _ = fixture(source, artifact)
    return path.read_bytes()


def _by(obs, **dims):
    (o,) = [o for o in obs if all(o.dims.get(k) == v for k, v in dims.items())]
    return o


# --- power conversion ----------------------------------------------------------------------------------------------


def test_hours_come_from_the_calendar():
    assert power.year_hours(2024) == 8784 and power.year_hours(2025) == 8760 and power.year_hours(1900) == 8760
    assert power.hours_between(date(2024, 2, 1), date(2025, 2, 1)) == 8784
    assert power.hours_between(date(2023, 2, 1), date(2024, 2, 1)) == 8760
    with pytest.raises(ValueError):
        power.hours_between(date(2024, 1, 1), date(2024, 1, 1))


def test_btu_definition_is_eias_heat_content_of_a_kilowatt_hour():
    # EIA's 3,412.14 Btu per kWh (checked in eia_international) is the International Table Btu.
    assert round(Decimal(3_600_000) / power.BTU_JOULES, 2) == eia.BTU_PER_KWH
    assert power.quad_btu_to_twh(Decimal(1)) == Decimal("1055.05585262") * Decimal(10) ** 15 / Decimal("3.6e15")


# --- Lovering et al. 2022 ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lovering() -> tuple[bytes, list[str]]:
    xml = _bytes("lovering-2022", "article-xml")
    return xml, textmatch.pdf_pages_text(_bytes("lovering-2022", "article-pdf"))


def test_lovering_table_1_as_printed(lovering):
    xml, pages = lovering
    rows = lov.read_table(xml)
    lov.verify(xml, pages, rows)
    obs = lov.observations(rows)
    assert len(obs) == 37
    assert _by(obs, source="nuclear", statistic="median").value == 7.1
    assert _by(obs, source="dedicated-biomass", statistic="median").value == 58_000.0
    assert _by(obs, source="wind", area="spacing", statistic="median").value == 12_000.0
    assert _by(obs, source="wind", area="footprint", statistic="median").value == 130.0
    assert _by(obs, source="hydro", statistic="iqr").value == 2_300.0
    assert _by(obs, source="ground-pv", statistic="mean").value == 2_100.0
    # The IQR is a width, never a pair of bounds.
    assert all(o.lower is None and o.upper is None for o in obs)
    rooftop = _by(obs, source="rooftop-pv")
    assert rooftop.value == 0.0 and rooftop.dims["statistic"] == "assigned" and "assumption" in rooftop.note
    assert "n = 952 observations" in _by(obs, source="hydro", statistic="median").note


def test_lovering_refuses_a_cell_the_printed_table_does_not_show(lovering):
    xml, pages = lovering
    changed = xml.replace(b'<td align="center">2,300</td>', b'<td align="center">2,400</td>', 1)
    assert changed != xml
    with pytest.raises(lov.LoveringFormatError, match="is not printed on PDF page 8"):
        lov.verify(changed, pages, lov.read_table(changed))


def test_lovering_refuses_a_missing_row_or_heading(lovering):
    xml, _ = lovering
    with pytest.raises(lov.LoveringFormatError, match="rows"):
        lov.read_table(xml.replace(b"<bold>Residue biomass</bold>", b"<bold>Crop residues</bold>"))
    with pytest.raises(lov.LoveringFormatError, match="headings"):
        lov.read_table(xml.replace(b">LUIE IQR<", b">LUIE Q1<"))


def test_lovering_rooftop_sentence_is_required(lovering, monkeypatch):
    xml, pages = lovering
    rows = lov.read_table(xml)
    gone = lov.Statement(lov.ROOFTOP.locator, 6, lov.ROOFTOP.text.replace("zero", "one"))
    monkeypatch.setattr(lov, "STATEMENTS", (gone, *lov.STATEMENTS[1:]))
    with pytest.raises(lov.LoveringFormatError, match="not in the XML"):
        lov.verify(xml, pages, rows)


# --- Nøland et al. 2022 --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def noland_pages() -> list[str]:
    return textmatch.pdf_pages_text(_bytes("noland-2022", "article-pdf"))


def test_noland_table_16_without_the_iea_derived_and_third_party_rows(noland_pages):
    rows = nol.read_table(noland_pages)
    nol.verify(noland_pages, rows)
    obs = nol.observations(rows)
    assert len(obs) == 30 and {o.dims["source"] for o in obs} == set(nol.SOURCES)
    assert _by(obs, source="wind-offshore", statistic="median").value == 3.84
    assert _by(obs, source="wind-onshore", statistic="median").value == 1.49
    assert _by(obs, source="rooftop-pv", statistic="median").value == 4.17
    assert _by(obs, source="nuclear", statistic="mean").value == 764.69
    assert _by(obs, source="hydro", statistic="standard-deviation").value == 157.28
    assert "natural-gas" not in nol.SOURCES and "biomass" not in nol.SOURCES
    assert "n = 40" in _by(obs, source="rooftop-pv", statistic="median").note


def test_noland_refuses_tables_that_disagree(noland_pages):
    rows = nol.read_table(noland_pages)
    pages = list(noland_pages)
    pages[13] = pages[13].replace("Offshore 3.84", "Offshore 3.85")
    with pytest.raises(nol.NolandFormatError, match="wind-offshore"):
        nol.verify(pages, rows)


def test_noland_gas_stays_out_only_while_it_rests_on_the_iea(noland_pages):
    rows = nol.read_table(noland_pages)
    pages = list(noland_pages)
    pages[23] = pages[23].replace("World Energy Outlook 2022", "Statistical Yearbook 2022")
    with pytest.raises(nol.NolandFormatError, match="re-read the article"):
        nol.verify(pages, rows)


# --- EIA RECS 2020 -------------------------------------------------------------------------------------------------


def test_recs_average_home_and_its_average_power():
    a = recs.read(_bytes("eia-recs-2020", "table-ce2-1"))
    assert (a.kwh, a.homes_million, a.total_billion_kwh, a.rse_percent) == (
        Decimal(10566),
        Decimal("123.53"),
        Decimal(1305),
        Decimal("0.38"),
    )
    recs.require_period(_bytes("eia-recs-2020", "ce-technical-documentation"))
    assert power.hours_between(recs.START, recs.END) == 8784
    assert power.average_power(a.kwh, 8784) == Decimal(10566) / Decimal(8784)


def test_recs_refuses_an_average_that_is_not_over_all_homes():
    a = recs.read(_bytes("eia-recs-2020", "table-ce2-1"))
    with pytest.raises(recs.RecsFormatError, match="no longer be over all homes"):
        recs.check_average(recs.Average(a.kwh, Decimal("100.00"), a.total_billion_kwh, a.rse_percent))


# --- DESNZ subnational electricity ---------------------------------------------------------------------------------


@pytest.mark.parametrize("side", DESNZ_SIDECARS, ids=lambda p: p.name)
def test_desnz_member_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"] == meta["member_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == desnz.SOURCE
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes", "member"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open" and src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", DESNZ_SIDECARS, ids=lambda p: p.name)
def test_desnz_member_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(FIXTURES))
    from zip_member_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    source, artifact, member, ranges = parse_command(meta["command"])
    assert (source, artifact, member) == (meta["source_id"], meta["artifact_id"], meta["member"])
    assert canonical.sha256_bytes(cut(raw, member, ranges)[0]) == meta["fixture_sha256"]


def _desnz_members() -> dict[str, bytes]:
    out = {}
    for side in DESNZ_SIDECARS:
        meta = json.loads(side.read_text())
        out[meta["member"]] = side.with_name(side.name.removesuffix(".provenance.json")).read_bytes()
    return out


def test_desnz_values_are_the_stored_decimals():
    members = _desnz_members()
    assert set(members) == {
        desnz.WORKBOOK_XML,
        desnz.WORKBOOK_RELS,
        desnz.SHARED_STRINGS,
        "xl/worksheets/sheet1.xml",
        "xl/worksheets/sheet21.xml",
    }
    v = desnz.values_from(members)
    assert v == desnz.Values(Decimal("3463.4084152009368"), Decimal("34800.715594371497"))
    assert desnz.household_hours() == desnz.all_meter_hours() == 8784


def test_desnz_refuses_a_changed_electricity_year():
    members = _desnz_members()
    members[desnz.SHARED_STRINGS] = members[desnz.SHARED_STRINGS].replace(
        b"February 2024 to January 2025", b"April 2024 to March 2025"
    )
    with pytest.raises(desnz.DesnzFormatError, match="cover sheet no longer says"):
        desnz.values_from(members)


def test_desnz_refuses_a_moved_column():
    members = _desnz_members()
    members[desnz.SHARED_STRINGS] = members[desnz.SHARED_STRINGS].replace(b"(kWh per household)", b"(kWh per home)")
    with pytest.raises(desnz.DesnzFormatError, match="headings"):
        desnz.values_from(members)


# --- EIA FAQ 207 (Vogtle) ------------------------------------------------------------------------------------------


def _faq_text(raw: bytes | None = None) -> str:
    _, meta = fixture("eia-faq-nuclear-plants", "faq-207")
    return faq.page_text(raw if raw is not None else _bytes("eia-faq-nuclear-plants", "faq-207"), None, meta["url"])


def test_vogtle_net_summer_capacity_and_its_date():
    period, summer, nameplate, passage = faq.read(_faq_text())
    assert (period, summer, nameplate) == ("2026-03", "4,530", "4,658")
    assert passage.startswith("The Alvin W. Vogtle Electric Generating Plant in Georgia is the largest")


def test_vogtle_refuses_a_changed_answer():
    raw = _bytes("eia-faq-nuclear-plants", "faq-207")
    with pytest.raises(faq.FaqFormatError, match="re-read the FAQ"):
        faq.read(_faq_text(raw.replace(b"is the largest U.S. nuclear power plant", b"is a large U.S. plant")))


# --- Ember world demand and EIA world primary energy as average power ----------------------------------------------


def _ember_df() -> pl.DataFrame:
    return pl.read_csv(_bytes("ember-yearly", "generation-yearly-global"), infer_schema=False)


def test_ember_world_demand_and_average_power():
    df = _ember_df()
    demand = {o.period: o for o in ember.demand_observations(df)}
    tw = {o.period: o for o in ember.power_observations(df)}
    assert len(demand) == len(tw) == 26
    assert demand["2025"].value == 31820.135 and demand["2025"].status == "preliminary"
    assert tw["2025"].value == float(Decimal("31820.135") / 8760)
    assert tw["2024"].value == float(Decimal("30990.182") / 8784)
    assert tw["2025"].status == "preliminary" and tw["2025"].note == demand["2025"].note
    ts = {t.spec.id: t for t in discover(Paths.default())}
    validate(ts["electricity-demand.ember.world"], list(demand.values()))
    validate(ts["power-scale.ember.world-electricity"], list(tw.values()))


def test_ember_refuses_world_demand_that_is_not_world_generation():
    df = _ember_df().with_columns(
        pl.when((pl.col("Area") == "World") & (pl.col("Electricity source") == "Demand") & (pl.col("Year") == "2020"))
        .then(pl.lit("26000.000"))
        .otherwise(pl.col("Generation (TWh)"))
        .alias("Generation (TWh)")
    )
    with pytest.raises(ember.EmberDemandError, match="World 2020"):
        ember.world_demand(df)


def test_eia_world_primary_energy_as_average_power():
    (side,) = sorted((FIXTURES / "eia-international" / "intl-bulk").glob("*.provenance.json"))
    text = side.with_name(side.name.removesuffix(".provenance.json")).read_bytes()
    table = eia.consumption(eia.read_series(text))
    obs = {o.period: o for o in eia.world_power_observations(table)}
    q2024 = table.by_entity["WLD"]["44"]["2024"]
    assert isinstance(q2024, Decimal)
    expected = q2024 * Decimal(10) ** 15 * Decimal("1055.05585262") / Decimal("3.6e15") / Decimal(8784)
    assert obs["2024"].value == float(expected)
    assert 20.0 < obs["2024"].value < 20.5
    q2023 = table.by_entity["WLD"]["44"]["2023"]
    assert isinstance(q2023, Decimal)
    assert obs["2023"].value == float(power.quad_btu_to_twh(q2023) / 8760)
    assert all(o.entity == "WLD" for o in obs.values())


# --- end to end ----------------------------------------------------------------------------------------------------


def _tmp_paths(tmp_path: Path, *source_ids: str) -> Paths:
    (tmp_path / "literature").mkdir()
    (tmp_path / "sources").mkdir()
    for sid in source_ids:
        shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{sid}.yaml", tmp_path / "sources" / f"{sid}.yaml")
    return Paths.default().with_(
        sources=tmp_path / "sources",
        literature=tmp_path / "literature",
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )


def _record(paths: Paths, source: str, artifact: str, content_type: str | None = None) -> str:
    path, meta = fixture(source, artifact)
    snap, _ = snapshots.record(
        paths,
        data=path.read_bytes(),
        source_id=source,
        artifact_id=artifact,
        url=meta["url"],
        acquisition="automatic",
        today=date.fromisoformat(meta["date_accessed"]),
        content_type=content_type,
        note=f"test fixture: {meta['rows_kept']} of {meta['full_sha256']}",
    )
    return snap.sha256


def test_build_exports_land_power_and_capacity(tmp_path):
    paths = _tmp_paths(tmp_path, "lovering-2022", "noland-2022", "eia-recs-2020", "eia-faq-nuclear-plants")
    pointers = {}
    for source, artifact, ctype in (
        ("lovering-2022", "article-xml", "application/xml"),
        ("lovering-2022", "article-pdf", "application/pdf"),
        ("noland-2022", "article-pdf", "application/pdf"),
        ("eia-recs-2020", "table-ce2-1", None),
        ("eia-recs-2020", "ce-technical-documentation", "application/pdf"),
        ("eia-faq-nuclear-plants", "faq-207", "text/html"),
    ):
        pointers[snapshots.key(source, artifact)] = _record(paths, source, artifact, ctype)
    snapshots.set_current(paths, pointers)
    reg = load_registry(paths)
    ids = {
        lov.INDICATOR,
        nol.INDICATOR,
        "electricity-use.eia-recs-2020.us-household",
        "power-scale.eia-recs-2020.us-household",
        faq.INDICATOR,
    }
    ts = [t for t in discover(paths) if t.spec.id in ids]
    report = build_and_export(paths, reg, ts)
    assert {o.id: o.state for o in report.outcomes} == dict.fromkeys(ids, "built"), report.outcomes

    land = exported(paths.public_indicators / f"{lov.INDICATOR}.json")
    assert land["kind"] == "published-value" and land["licence_class"] == "open"
    assert land["latest"]["value"] == 7.1 and land["latest"]["dims"]["source"] == "nuclear"
    assert land["published_value"]["quote"].startswith("Nuclear had the lowest median LUIE at 7.1")
    assert {o["sha256"] for o in land["origins"]} == {
        pointers["lovering-2022/article-xml"],
        pointers["lovering-2022/article-pdf"],
    }

    density = exported(paths.public_indicators / f"{nol.INDICATOR}.json")
    assert density["latest"]["value"] == 3.84 and density["unit"]["short"] == "W/m²"

    kw = exported(paths.public_indicators / "power-scale.eia-recs-2020.us-household.json")
    assert kw["kind"] == "derived" and kw["latest"]["entity"] == "USA" and kw["latest"]["period"] == "2020"
    assert kw["latest"]["value"] == float(Decimal(10566) / 8784)
    assert kw["attribution"].startswith("Calculated by Environment Dashboard") and "Changes:" in kw["attribution"]
    assert any("8,784 hours (366 days)" in s["description"] for s in kw["processing"])

    vogtle = exported(paths.public_indicators / f"{faq.INDICATOR}.json")
    assert vogtle["latest"]["value"] == 4.53 and vogtle["latest"]["period"] == "2026-03"
    assert vogtle["unit"]["code"] == "GW"
    assert validate_all(paths, reg) == []

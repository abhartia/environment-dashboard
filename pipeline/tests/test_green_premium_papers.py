"""Green Premium studies (envdash/transforms/green_premium/): each study's conventional and lower-carbon costs, read
as printed from the real article files (whole-file fixtures: a PDF or a JATS XML cannot be cut and still be read)."""

from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from envdash import snapshots, textmatch
from envdash.export import build_and_export
from envdash.greenpremium import (
    Passage,
    PrintedValueError,
    check_passages,
    jats_root,
    jats_table,
    number_in,
    printed_number,
)
from envdash.models import Snapshot
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.green_premium import ammonia_arnaiz_del_pozo_2022 as ammonia
from envdash.transforms.green_premium import cars_furch_2022 as cars
from envdash.transforms.green_premium import heating_drawdown_explorer as dd_heat
from envdash.transforms.green_premium import heating_rosenow_2025 as heat
from envdash.transforms.green_premium import jet_fuel_sacchi_2023 as jet
from envdash.transforms.green_premium import meat_falkenberg_2023 as meat
from envdash.transforms.green_premium import meat_siegrist_2024 as subs
from envdash.transforms.green_premium import trucks_rajalehto_helo_2025 as trucks
from envdash.validate import validate_all

from support import exported, fixture


def _bytes(source: str, artifact: str) -> bytes:
    path, _ = fixture(source, artifact)
    return path.read_bytes()


def _pages(source: str) -> list[str]:
    return textmatch.pdf_pages_text(_bytes(source, "article-pdf"))


@pytest.fixture(scope="module")
def ammonia_pages() -> list[str]:
    return _pages(ammonia.SOURCE)


@pytest.fixture(scope="module")
def truck_pages() -> list[str]:
    return _pages(trucks.SOURCE)


@pytest.fixture(scope="module")
def siegrist_pages() -> list[str]:
    return _pages(subs.SOURCE)


def _by(obs, **dims):
    (o,) = [o for o in obs if all(o.dims.get(k) == v for k, v in dims.items())]
    return o


def _all_transforms() -> dict[str, object]:
    # The studies in envdash/transforms/green_premium/; the producers' quoted premiums (action/green_premium.py) have
    # their own tests.
    return {
        t.spec.id: t
        for t in discover(Paths.default())
        if t.spec.id.startswith("green-premium.") and t.run.__module__.startswith("envdash.transforms.green_premium.")
    }


# --- shared reading rules -----------------------------------------------------------------------------------------


def test_printed_numbers_are_read_exactly_or_refused():
    assert printed_number("£15,640", prefix="£") == 15640
    assert printed_number("2.13E4") == 21300
    assert printed_number("−1.9") == printed_number("-1.9")
    for bad in ("385.1–385.9", "15,640", "0,12", "±3.66", "12a"):
        with pytest.raises(PrintedValueError):
            printed_number(bad, prefix="£" if bad == "15,640" else "")
    assert number_in("569.3", "772.1, 569.3, and 484.7")
    assert not number_in("69.3", "772.1, 569.3, and 484.7")
    assert not number_in("385.1", "385.15")


def test_every_green_premium_indicator_pairs_two_sides_or_says_why():
    ts = _all_transforms()
    assert sorted(ts) == [
        "green-premium.arnaiz-del-pozo-2022.ammonia",
        "green-premium.drawdown-explorer.heating",
        "green-premium.falkenberg-2023.meat",
        "green-premium.furch-2022.cars-lifetime",
        "green-premium.furch-2022.cars-per-km",
        "green-premium.rajalehto-helo-2025.trucks",
        "green-premium.rosenow-2025.heating",
        "green-premium.sacchi-2023.jet-fuel",
        "green-premium.siegrist-2024.meat-substitutes",
    ]
    for tid, t in ts.items():
        assert t.spec.kind == "published-value"
        sides = {v.id for d in t.spec.dimensions if d.id == "side" for v in d.values}
        # Siegrist publishes the ratio itself, so it has no sides; every other indicator has both.
        assert sides == (
            set()
            if tid.endswith("meat-substitutes")
            else {"conventional", "low-carbon"} | ({"conventional-with-capture"} if "ammonia" in tid else set())
        )


# --- ammonia ------------------------------------------------------------------------------------------------------


def test_ammonia_values_are_the_printed_numbers(ammonia_pages):
    assert len(ammonia_pages) == 17
    check_passages(ammonia_pages, ammonia.PASSAGES)
    obs = ammonia.observations()
    assert len(obs) == 8 and all(o.period == "2050" and o.status == "projection" for o in obs)
    assert _by(obs, option="kbr-without-capture").value == 479.0
    assert _by(obs, option="kbr").value == 385.9
    assert _by(obs, option="lac").value == 385.1
    eur_gsr = _by(obs, option="gsr", setting="european-prices")
    assert (eur_gsr.entity, eur_gsr.value) == ("EUR_STUDY", 332.1)
    assert eur_gsr.note.count('"') == 4  # the summary and the abstract agree, both quoted
    assert _by(obs, option="gsr", setting="saudi-arabia").value == 192.7
    green = {o.entity: o.value for o in obs if o.dims["option"] == "green"}
    assert green == {"DEU": 772.1, "ESP": 569.3, "SAU": 484.7}


def test_ammonia_two_different_statements_publish_null():
    i = next(i for i, v in enumerate(ammonia.VALUES) if v.passage is ammonia.ABSTRACT and v.option == "gsr")
    values = list(ammonia.VALUES)
    abstract = replace(ammonia.ABSTRACT, text=ammonia.ABSTRACT.text.replace("of 332.1", "of 333.1"))
    values[i] = replace(values[i], passage=abstract, words=values[i].words.replace("332.1", "333.1"), printed="333.1")
    o = _by(ammonia.observations(tuple(values)), option="gsr", setting="european-prices")
    assert o.value is None and "333.1 in Abstract, p. 1" in o.missing_reason


def test_ammonia_a_changed_number_or_page_is_refused(ammonia_pages):
    changed = replace(ammonia.GREEN_P15, text=ammonia.GREEN_P15.text.replace("569.3", "596.3"))
    with pytest.raises(PrintedValueError, match="not found on PDF page 15"):
        check_passages(ammonia_pages, [changed])
    with pytest.raises(PrintedValueError, match="not found on PDF page 14"):
        check_passages(ammonia_pages, [replace(ammonia.GREEN_P15, page=14)])
    v = replace(ammonia.VALUES[0], printed="385.9")  # printed in the passage, but not in the value's words
    with pytest.raises(PrintedValueError, match="is not printed in"):
        ammonia.observations((v,))


def test_a_minus_sign_must_match(ammonia_pages):
    # The PDF prints "(-13.9%)" with a hyphen-minus; textmatch alone would accept a minus sign, this reading must not.
    p = replace(ammonia.BLUE_P15, text=ammonia.BLUE_P15.text.replace("(-13.9%)", "(−13.9%)"))
    assert textmatch.contains(ammonia_pages[14], p.text)
    with pytest.raises(PrintedValueError, match="not found"):
        check_passages(ammonia_pages, [p])


# --- heating, Rosenow et al. --------------------------------------------------------------------------------------


def test_heating_table_2_business_as_usual_rows():
    obs = heat.observations(_bytes(heat.SOURCE, "article-xml"))
    assert len(obs) == 10 and {o.entity for o in obs} == {"GBR"}
    assert _by(obs, option="gas-boiler", case="central").value == 15640
    assert _by(obs, option="heat-pump", case="central").value == 16861
    assert _by(obs, option="heat-pump", case="no-grant-cost-minus-25").value == 21339
    assert _by(obs, option="gas-boiler", case="discount-rate-7").value == 13495
    assert _by(obs, option="heat-pump", case="heat-pump-life-20").value == 15714


def test_heating_a_changed_caption_or_column_is_refused():
    root = jats_root(_bytes(heat.SOURCE, "article-xml"))
    with pytest.raises(PrintedValueError, match="caption"):
        jats_table(root, heat.LABEL, heat.CAPTION.replace("85%", "90%"))
    table = jats_table(root, heat.LABEL, heat.CAPTION)
    with pytest.raises(PrintedValueError, match="header"):
        table.cell(("", "Central case", *list(heat.CASES.values())[1:]), "BAU—heat pump", "Central case")
    with pytest.raises(PrintedValueError, match="no row"):
        table.cell(heat.HEADER, "BAU—heat pumps", "Central scenario")


# --- jet fuel, Sacchi et al. --------------------------------------------------------------------------------------


def test_jet_fuel_synthetic_costs_and_no_fossil_comparator():
    obs = jet.observations(_bytes(jet.SOURCE, "article-xml"))
    syn = {(o.dims["scenario"], o.period): o.value for o in obs if o.dims["side"] == "low-carbon"}
    assert syn == {("2c", "2030"): 3.1, ("2c", "2050"): 2.1, ("3-5c", "2030"): 3.8, ("3-5c", "2050"): 3.2}
    fossil = [o for o in obs if o.dims["side"] == "conventional"]
    assert len(fossil) == 4 and all(o.value is None for o in fossil)
    assert all(o.missing_reason.startswith("No fossil comparator") for o in fossil)
    assert "0.50 €/kg" in fossil[0].missing_reason and "Becattini" in fossil[0].missing_reason


def test_jet_fuel_reads_the_second_block_of_table_4():
    # Table 4 repeats the row labels "2 °C" and "3.5 °C" under two headers; the hydrogen block must not be read.
    table = jats_table(jats_root(_bytes(jet.SOURCE, "article-xml")), jet.LABEL, jet.CAPTION)
    assert table.cell(("Climate scenario", "LC H2 (€/kgH2) 2030", "LC H2 (€/kgH2) 2050"), "2 °C", "LC H2 (€/kgH2) 2030")
    assert table.cell(jet.HEADER, "2 °C", jet.YEARS["2030"]) == "3.1"


# --- cars, Furch et al. -------------------------------------------------------------------------------------------


def test_cars_per_km_and_lifetime():
    raw = _bytes(cars.SOURCE, "article-xml")
    per_km = {o.dims["option"]: o.value for o in cars.observations(raw, cars.PER_KM)}
    assert per_km == {"petrol": 0.185, "diesel": 0.177, "electric": 0.206}
    life = cars.observations(raw, cars.LIFETIME)
    assert {o.dims["option"]: o.value for o in life} == {"petrol": 74147, "diesel": 70985, "electric": 82423}
    assert "without battery replacement is €0.21" in _by(life, option="electric").note


# --- trucks, Rajalehto & Helo ---------------------------------------------------------------------------------------


def test_trucks_table_3_columns(truck_pages):
    check_passages(truck_pages, trucks.PASSAGES)
    obs = trucks.observations()
    mean = {o.dims["option"]: o.value for o in obs if o.dims["statistic"] == "mean"}
    assert mean == {"diesel": 21300, "lbg": 19700, "ev": 17600}
    lbg = _by(obs, option="lbg", statistic="median")
    assert (lbg.value, lbg.lower, lbg.upper, lbg.interval) == (19200, 15000, 39500, "range")
    assert {o.period for o in obs} == {"2023-01/2023-10"}


def test_trucks_a_swapped_column_is_refused(truck_pages):
    # The table text is built from the declared columns, so declaring LBG's values under Diesel changes the text.
    cols = list(trucks.OPTIONS.values())
    swapped = " ".join(" ".join(v) for v in (cols[1][3], cols[0][3], cols[2][3]))
    text = trucks.TABLE_3.text.split(" Standard Error ")[0] + " Standard Error " + swapped
    with pytest.raises(PrintedValueError, match="not found on PDF page 8"):
        check_passages(truck_pages, [replace(trucks.TABLE_3, text=text)])


# --- meat, Falkenberg et al. and Siegrist et al. --------------------------------------------------------------------


def test_meat_table_3():
    obs = meat.observations(_bytes(meat.SOURCE, "article-xml"))
    mean = {(o.dims["product"], o.dims["side"]): o.value for o in obs if o.dims["statistic"] == "mean"}
    assert mean == {
        ("mince", "conventional"): 11.40,
        ("mince", "low-carbon"): 16.32,
        ("sausages", "conventional"): 15.24,
        ("sausages", "low-carbon"): 19.72,
    }
    s = _by(obs, product="sausages", side="conventional", statistic="median")
    assert (s.value, s.lower, s.upper) == (15.00, 9.42, 31.87)


def test_meat_substitute_ratios(siegrist_pages):
    assert len(siegrist_pages) == 12
    check_passages(siegrist_pages, subs.PASSAGES)
    obs = subs.observations()
    assert {o.entity: o.value for o in obs} == {"DEU": 0.95, "ESP": 2.15}
    assert all("24 to 115 % more expensive" in o.note for o in obs)
    with pytest.raises(PrintedValueError, match="not found on PDF page 6"):
        check_passages(siegrist_pages, [Passage(6, subs.RATIOS.text.replace("2.15", "2.51"), "x")])


# --- the transforms end to end ------------------------------------------------------------------------------------

FIXTURED = {
    ammonia.INDICATOR: [(ammonia.SOURCE, "article-pdf")],
    heat.INDICATOR: [(heat.SOURCE, "article-xml")],
    jet.INDICATOR: [(jet.SOURCE, "article-xml")],
    cars.PER_KM: [(cars.SOURCE, "article-xml")],
    cars.LIFETIME: [(cars.SOURCE, "article-xml")],
    trucks.INDICATOR: [(trucks.SOURCE, "article-pdf")],
    meat.INDICATOR: [(meat.SOURCE, "article-xml")],
    subs.INDICATOR: [(subs.SOURCE, "article-pdf")],
}


@pytest.mark.parametrize("tid", sorted(FIXTURED))
def test_each_transform_runs_and_validates_on_its_fixture(tid):
    t = _all_transforms()[tid]
    files = {}
    for source, artifact in FIXTURED[tid]:
        path, meta = fixture(source, artifact)
        assert meta["fixture_sha256"] == meta["full_sha256"]  # whole files
        snap = Snapshot(
            sha256=meta["full_sha256"],
            bytes=meta["full_bytes"],
            source_id=source,
            artifact_id=artifact,
            url=meta["url"],
            date_accessed=meta["date_accessed"],
            acquisition="manual" if source == subs.SOURCE else "automatic",
        )
        files[f"{source}/{artifact}"] = InputFile(path, snap)
    result = t.run(files)
    validate(t, result.observations)
    assert result.published_value is not None and result.published_value.document == FIXTURED[tid][0][0]


def _tmp_paths(tmp_path: Path, *sources: str) -> Paths:
    (tmp_path / "literature").mkdir()
    (tmp_path / "sources").mkdir()
    for sid in sources:
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


def test_build_exports_open_published_values_side_by_side(tmp_path):
    paths = _tmp_paths(tmp_path, heat.SOURCE, jet.SOURCE)
    for source in (heat.SOURCE, jet.SOURCE):
        path, meta = fixture(source, "article-xml")
        snap, _ = snapshots.record(
            paths,
            data=path.read_bytes(),
            source_id=source,
            artifact_id="article-xml",
            url=meta["url"],
            acquisition="automatic",
            today=date.fromisoformat(meta["date_accessed"]),
            note="test fixture: the whole article XML",
        )
        snapshots.set_current(paths, {snapshots.key(source, "article-xml"): snap.sha256})
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id in (heat.INDICATOR, jet.INDICATOR)]
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built", "built"], [o.reason for o in report.outcomes]
    hp = exported(paths.public_indicators / f"{heat.INDICATOR}.json")
    assert hp["licence_class"] == "open" and hp["latest"]["value"] == 16861
    sides = {o["dims"]["side"]: o["value"] for o in hp["observations"] if o["dims"]["case"] == "central"}
    assert sides == {"conventional": 15640, "low-carbon": 16861}
    jf = exported(paths.public_indicators / f"{jet.INDICATOR}.json")
    assert jf["latest"]["value"] == 2.1 and jf["latest"]["period"] == "2050" and jf["latest"]["entity"] == "EUR_STUDY"
    assert any(o["value"] is None and o["missing_reason"].startswith("No fossil") for o in jf["observations"])
    assert validate_all(paths, reg) == []


# --- Drawdown (no fixture: the spreadsheets are not mirrored) ------------------------------------------------------


def _drawdown_files() -> dict[str, InputFile]:
    p = Paths.default()
    files = {}
    for i in (dd_heat.SPREADSHEET, dd_heat.METHODOLOGY):
        sha = snapshots.read_current(p)[i.key]
        files[i.key] = InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))
    return files


@pytest.mark.snapshot
def test_drawdown_heat_pump_costs_from_the_real_spreadsheet():
    (t,) = dd_heat.transforms(Paths.default())
    result = t.run(_drawdown_files())
    validate(t, result.observations)
    got = {(o.dims["option"], o.dims["cost"]): o.value for o in result.observations}
    assert got == {
        ("baseline", "net"): 1180,
        ("baseline", "operating"): 830,
        ("heat-pump", "net"): 990,
        ("heat-pump", "operating"): 540,
    }


@pytest.mark.snapshot
def test_drawdown_a_moved_label_is_refused():
    from envdash.transforms.action.drawdown_explorer import sheet_rows

    rows = sheet_rows(_drawdown_files()[dd_heat.SPREADSHEET.key].path.read_bytes(), dd_heat.SHEET)
    rows[25] = ("net cost per unit solution", *rows[25][1:])
    with pytest.raises(dd_heat.DrawdownCostError, match="row 26"):
        dd_heat.observations(rows)

"""Where food's emissions come from: FAOSTAT agrifood emissions by stage and process (GT), farm-gate emissions and
intensities of 14 products (EI), and livestock methane by animal (GLE).

Fixtures are byte-exact slices of the real snapshots, cut by tests/fixtures/faostat/make_zip_fixture.py (sidecars are
checked by test_faostat_emissions.py, which covers every tests/fixtures/faostat/*/ sidecar):
- emissions-totals: the 26 items used (Agrifood systems, its three stages and their 22 processes), element 723113,
  for the World, Ethiopia (no fertilizers manufacturing, food processing or food packaging rows) and Somalia
  (negative synthetic-fertilizer values), both sources and FAO's projections included;
- emissions-intensities: the World's 14 products (emissions, and intensity for three of them), India's cattle meat
  (intensity printed only to 1990), Mali's goat meat (negative as printed), FAO's "China" group, and the flag codebook;
- emissions-livestock: the 16 animals and All Animals (CH4) for the World and Iceland, the World's Cattle and Chickens
  CH4 and N2O (for the EI identity below), and the flag codebook.
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from envdash.paths import Paths
from envdash.transforms.food import faostat_agrifood_stages as gt
from envdash.transforms.food import faostat_commodity_emissions as ei
from envdash.transforms.food import faostat_livestock_by_animal as gle
from envdash.transforms.food.faostat_bulk import FaostatBulkError, catalogue_entry, fields, read_flags
from envdash.transforms.food.faostat_parts import entity_of, gather

FIXTURES = Path(__file__).parent / "fixtures" / "faostat"
CATALOGUE = FIXTURES / "datasets-catalogue" / "54b055217bee.json"


def _lines(artifact: str, *names: str) -> list[bytes]:
    """The header of the first fixture, then the data lines of each, in order."""
    out: list[bytes] = []
    for i, name in enumerate(names):
        lines = (FIXTURES / artifact / name).read_bytes().splitlines(keepends=True)
        out += lines if i == 0 else lines[1:]
    return out


def _meta(artifact: str, name: str) -> dict:
    return json.loads((FIXTURES / artifact / f"{name}.provenance.json").read_text())


def _rows(lines: list[bytes]) -> list[dict[str, str]]:
    """The fixture's rows as printed, read directly (not through the transforms), for independent checks."""
    header = fields(lines[0])
    return [dict(zip(header, fields(ln), strict=True)) for ln in lines[1:]]


def _printed(lines, element: str, source: str | None = "FAO TIER 1") -> dict[tuple[str, str, int], Decimal]:
    """(Area Code, Item Code, year) -> value as printed, for one element, without FAO's projections."""
    out = {}
    for r in _rows(lines):
        if r["Element Code"] == element and r["Flag"] != "F" and (source is None or r["Source"] == source):
            out[(r["Area Code"], r["Item Code"], int(r["Year"]))] = Decimal(r["Value"])
    return out


# --- agrifood emissions by stage and process (GT) ------------------------------------------------------------------

GT_NAMES = ("d2c47e116553.stages-world.csv", "d2c47e116553.stages-ethiopia.csv", "d2c47e116553.stages-somalia.csv")
GT_AREAS = {"5000": "WLD", "238": "ETH", "201": "SOM"}


def _gt_lines() -> list[bytes]:
    return _lines("emissions-totals", *GT_NAMES)


def _gt(level: str, lines=None):
    flags = read_flags((FIXTURES / "emissions-totals" / "d2c47e116553.flags.csv").read_bytes(), gt.FLAGS_MEMBER)
    return gt.observations(gt.read(lines or _gt_lines()), flags, level)


def test_stages_add_up_to_the_published_agrifood_total():
    obs, _ = _gt("stage")
    printed = _printed(_gt_lines(), gt.CO2EQ_AR5)
    sums: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for o in obs:
        sums[(o.entity, o.period)] += Decimal(str(o.value))
    totals = {(a, y): v for (a, i, y), v in printed.items() if i == gt.AGRIFOOD[0]}
    # Ethiopia is reported from 1993 (Ethiopia PDR before), the World and Somalia from 1990.
    assert len(totals) == 34 + 31 + 34
    for (code, year), total in totals.items():
        ours = sums.pop((GT_AREAS[code], f"{year}"))
        assert abs(ours - total / Decimal(1_000_000)) <= Decimal("0.00000001"), (code, year)
    assert not sums, "a published stage year without FAO's agrifood total"
    by = {(o.entity, o.dims["stage"], o.period): o.value for o in obs}
    # World 2023 as printed (kt): Farm gate 8,096,973.4689; Land-use change 3,190,127.728; Pre- and post-production
    # 5,247,971.1768; together FAO's Agrifood systems 16,535,072.3737.
    assert by[("WLD", "farm-gate", "2023")] == 8.0969734689
    assert by[("WLD", "land-use-change", "2023")] == 3.190127728
    assert by[("WLD", "pre-post-production", "2023")] == 5.2479711768
    assert {o.entity for o in obs} == {"WLD", "ETH", "SOM"}


def test_processes_add_up_to_each_published_stage():
    obs, _ = _gt("process")
    printed = _printed(_gt_lines(), gt.CO2EQ_AR5)
    sums: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for o in obs:
        sums[(o.entity, o.dims["stage"], o.period)] += Decimal(str(o.value))
    stage_code = {sid: code for code, (sid, _) in gt.STAGES.items()}
    stages = {(a, i, y): v for (a, i, y), v in printed.items() if i in gt.STAGES}
    assert len(stages) == 3 * (34 + 31 + 34)
    sid_of = {code: sid for sid, code in stage_code.items()}
    for (code, item, year), stage in stages.items():
        ours = sums.pop((GT_AREAS[code], sid_of[item], f"{year}"))
        assert abs(ours - stage / Decimal(1000)) <= Decimal("0.00001"), (code, item, year)
    assert not sums, "a published process year without FAO's stage total"
    assert len({o.dims["process"] for o in obs if o.entity == "WLD"}) == 22
    by = {(o.entity, o.dims["process"], o.period): o.value for o in obs}
    assert by[("WLD", "enteric-fermentation", "2023")] == 2947.2047472
    assert by[("WLD", "net-forest-conversion", "2023")] == 2814.0555454
    assert by[("WLD", "agrifood-systems-waste-disposal", "2023")] == 1452.7273298


def test_absent_processes_stay_absent_and_negatives_stay_as_printed():
    obs, _ = _gt("process")
    eth_2023 = {o.dims["process"] for o in obs if o.entity == "ETH" and o.period == "2023"}
    assert {"fertilizers-manufacturing", "food-processing", "food-packaging"}.isdisjoint(eth_2023)
    assert all(o.value is not None for o in obs)
    # Ethiopia's pre- and post-production 2023 (10,438.0876 kt) is the sum of the five rows FAO prints.
    pre_post = [
        o.value for o in obs if o.entity == "ETH" and o.period == "2023" and o.dims["stage"] == "pre-post-production"
    ]
    assert len(pre_post) == 5 and abs(sum(pre_post) - 10.4380876) < 1e-6
    by = {(o.entity, o.dims["process"], o.period): o.value for o in obs}
    # Somalia synthetic fertilizers 2011: -0.689000 kt in the file.
    assert by[("SOM", "synthetic-fertilizers", "2011")] == -0.000689


def test_stack_starts_in_1990_without_projections():
    for level in ("stage", "process"):
        obs, steps = _gt(level)
        periods = {o.period for o in obs}
        assert min(periods) == "1990" and max(periods) == "2023"
        assert "2030" not in periods and "2050" not in periods
        assert any("before 1990" in s for s in steps)
        assert any("2030 and 2050" in s for s in steps)
    # The fixture does hold pre-1990 farm rows (Somalia enteric fermentation from 1961) that are left out.
    assert ("201", "5058", 1961) in _printed(_gt_lines(), gt.CO2EQ_AR5)


def test_a_part_that_does_not_add_up_stops_the_transform():
    lines = _gt_lines()
    target = (
        b'"5000","\'001","World","5058","Enteric Fermentation","723113","Emissions (CO2eq) (AR5)","2023","2023","3050"'
    )
    (i,) = [n for n, ln in enumerate(lines) if ln.startswith(target)]
    lines[i] = lines[i].replace(b'"2947204.747200"', b'"2947304.747200"')
    with pytest.raises(FaostatBulkError, match="parts add up"):
        _gt("stage", lines)


def test_renamed_item_stops_the_transform():
    lines = [ln.replace(b'"Savanna fires"', b'"Savanna fire"') for ln in _gt_lines()]
    with pytest.raises(FaostatBulkError, match="named"):
        _gt("process", lines)


def test_gt_vintage_from_catalogue():
    name = "d2c47e116553.stages-world.csv"
    updated, rows = catalogue_entry(CATALOGUE.read_bytes(), gt.DATASET_CODE, _meta("emissions-totals", name)["url"])
    assert updated.isoformat() == "2025-10-28"
    assert rows == _meta("emissions-totals", name)["data_rows_total"]


def test_stage_scope_names_what_is_outside_the_total():
    by_id = {t.spec.id: t for t in gt.transforms(Paths.default())}
    for i in ("food.faostat.agrifood-emissions-by-stage", "food.faostat.agrifood-emissions-by-process"):
        s = by_id[i].spec.scope
        assert (s.gwp, s.lulucf, s.bunkers) == ("AR5-GWP100", "included", "excluded")
        assert "Forestland" in s.basis and "2001" in s.basis and "savanna fires" in s.basis


# --- farm-gate emissions and intensities of 14 products (EI) -------------------------------------------------------

EI_NAMES = (
    "1c2991089fec.world.csv",
    "1c2991089fec.india-cattle-meat.csv",
    "1c2991089fec.mali-goat-meat.csv",
    "1c2991089fec.china-group.csv",
)


def _ei_lines():
    return _lines("emissions-intensities", *EI_NAMES)


def _ei(element: str, lines=None):
    flags = read_flags((FIXTURES / "emissions-intensities" / "1c2991089fec.flags.csv").read_bytes(), ei.FLAGS_MEMBER)
    return ei.observations(ei.read(lines or _ei_lines()), flags, element)


def test_commodity_emissions_world_and_countries():
    obs, steps = _ei(ei.EMISSIONS)
    by = {(o.entity, o.dims["commodity"], o.period): o.value for o in obs}
    # World 2023 as printed (kt): cattle meat 2,113,655.572; rice 751,717.5581; hen eggs 49,582.4249.
    assert by[("WLD", "cattle-meat", "2023")] == 2113.655572
    assert by[("WLD", "rice", "2023")] == 751.7175581
    assert by[("WLD", "hen-eggs", "2023")] == 49.5824249
    assert len({o.dims["commodity"] for o in obs if o.entity == "WLD"}) == 14
    # Mali goat meat 2011 is negative in the file (FAO's milk-animal split) and is published as printed.
    assert by[("MLI", "goat-meat", "2011")] == -6.3167537
    # FAO's "China" group (351) is not published; India is.
    assert {o.entity for o in obs} == {"WLD", "IND", "MLI"}
    assert any("China" in s and "FAO regional" in s for s in steps)


def test_commodity_intensity_as_printed_and_absent_where_not_printed():
    obs, steps = _ei(ei.INTENSITY)
    by = {(o.entity, o.dims["commodity"], o.period): o.value for o in obs}
    assert by[("WLD", "cattle-meat", "2023")] == 30.4289
    assert by[("WLD", "chicken-meat", "2023")] == 0.5404
    # India's cattle-meat intensity is printed for 1961-1990 only, while its emissions run to 2023.
    ind = sorted(o.period for o in obs if o.entity == "IND")
    assert ind[0] == "1961" and ind[-1] == "1990" and len(ind) == 30
    emis, _ = _ei(ei.EMISSIONS)
    assert max(o.period for o in emis if o.entity == "IND") == "2023"
    assert all(o.value is not None for o in obs)
    assert any("absent here, not filled" in s for s in steps)


def test_ei_meat_and_milk_equal_the_gle_species_co2eq():
    """A test of reading, not a published value: FAO allocates non-dairy cattle to cattle meat and dairy cattle to
    cattle milk, so EI cattle meat + cattle milk = GLE Cattle CH4 x 28 + N2O x 265 (AR5), and likewise chicken meat +
    hen eggs = GLE Chickens, for every World year 1961-2023."""
    e = _printed(_ei_lines(), ei.EMISSIONS, source=None)
    gle_lines = _lines("emissions-livestock", "1eca81ff01c2.world.csv")
    ch4, n2o = _printed(gle_lines, "72441"), _printed(gle_lines, "72431")
    for items, animal in ((("867", "882"), "1757"), (("1058", "1062"), "1054")):
        for year in range(1961, 2024):
            ours = sum(e[("5000", i, year)] for i in items)
            gle_co2eq = ch4[("5000", animal, year)] * 28 + n2o[("5000", animal, year)] * 265
            assert abs(ours - gle_co2eq) <= Decimal("0.5"), (items, year, ours, gle_co2eq)


def test_ei_coverage_stated_in_the_description():
    """The descriptions say the 14 products cover 32 percent of FAO's agrifood systems emissions in 2023."""
    e = _printed(_ei_lines(), ei.EMISSIONS, source=None)
    products = sum(e[("5000", i, 2023)] for i in ei.COMMODITIES)
    agrifood = _printed(_gt_lines(), gt.CO2EQ_AR5)[("5000", gt.AGRIFOOD[0], 2023)]
    assert round(products / agrifood * 100) == 32
    for t in ei.transforms(Paths.default()):
        assert "32 percent in 2023" in t.spec.description
        assert "should not be compared" in t.spec.description
        assert "savanna fires" in t.spec.description and "land-use change" in t.spec.description


def test_ei_vintage_from_catalogue():
    name = "1c2991089fec.world.csv"
    updated, rows = catalogue_entry(
        CATALOGUE.read_bytes(), ei.DATASET_CODE, _meta("emissions-intensities", name)["url"]
    )
    assert updated.isoformat() == "2026-02-20"
    assert rows == _meta("emissions-intensities", name)["data_rows_total"] == 409_511


# --- livestock methane by animal (GLE) -----------------------------------------------------------------------------

GLE_NAMES = ("1eca81ff01c2.world.csv", "1eca81ff01c2.iceland.csv")


def _gle_lines():
    return _lines("emissions-livestock", *GLE_NAMES)


def _gle(lines=None):
    flags = read_flags((FIXTURES / "emissions-livestock" / "1eca81ff01c2.flags.csv").read_bytes(), gle.FLAGS_MEMBER)
    return gle.observations(gle.read(lines or _gle_lines()), flags)


def test_animals_add_up_to_all_animals():
    obs, steps = _gle()
    printed = _printed(_gle_lines(), gle.CH4_TOTAL)
    sums: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for o in obs:
        sums[(o.entity, o.period)] += Decimal(str(o.value))
    for code, entity in (("5000", "WLD"), ("99", "ISL")):
        for year in range(1961, 2024):
            total = printed[(code, gle.ALL_ANIMALS[0], year)] / Decimal(1000)
            assert abs(sums[(entity, f"{year}")] - total) <= Decimal("0.00001"), (entity, year)
    by = {(o.entity, o.dims["animal"], o.period): o.value for o in obs}
    # World 2023 as printed (kt CH4): non-dairy cattle 58,489.9138; dairy cattle 21,532.4326; All Animals 115,211.2597.
    assert by[("WLD", "cattle-non-dairy", "2023")] == 58.4899138
    assert by[("WLD", "cattle-dairy", "2023")] == 21.5324326
    assert len({o.dims["animal"] for o in obs if o.entity == "WLD"}) == 16
    periods = {o.period for o in obs}
    assert min(periods) == "1961" and max(periods) == "2023"
    assert any("2030 and 2050" in s for s in steps)


def test_animal_that_does_not_add_up_stops_the_transform():
    lines = _gle_lines()
    target = (
        b'"5000","\'001","World","1177","\'F1177","Llamas","72441","Livestock total (Emissions CH4)","2023","2023",'
        b'"3050"'
    )
    (i,) = [n for n, ln in enumerate(lines) if ln.startswith(target)]
    lines[i] = lines[i].replace(b'"266.155100"', b'"266.255100"')
    with pytest.raises(FaostatBulkError, match="parts add up"):
        _gle(lines)


def test_gle_vintage_ties_the_catalogue_entry_by_location_and_size():
    meta = _meta("emissions-livestock", "1eca81ff01c2.world.csv")
    updated, step = gle.catalogue_check(
        CATALOGUE.read_bytes(), meta["url"], meta["full_bytes"], meta["data_rows_total"]
    )
    assert updated.isoformat() == "2025-10-28"
    assert "54572KB" in step and "6,941,916" in step and "6,650,421" in step
    with pytest.raises(FaostatBulkError, match="FileSize"):
        gle.catalogue_check(CATALOGUE.read_bytes(), meta["url"], meta["full_bytes"] + 2048, meta["data_rows_total"])
    with pytest.raises(FaostatBulkError, match="not"):
        gle.catalogue_check(CATALOGUE.read_bytes(), meta["url"] + "x", meta["full_bytes"], meta["data_rows_total"])


def test_regions_are_left_out():
    g = gather(
        _rows(_lines("emissions-intensities", "1c2991089fec.china-group.csv")),
        items=ei.ITEMS,
        elements=ei.ELEMENTS,
        source=None,
        what="test",
    )
    left: set[str] = set()
    assert entity_of("351", g, left) is None and left == {"351"}
    g.m49["5707"] = "'097"
    assert entity_of("5707", g, left) is None and "5707" in left


# --- full snapshots ------------------------------------------------------------------------------------------------


@pytest.mark.snapshot
def test_full_snapshots_build_every_breakdown():
    from envdash import snapshots
    from envdash.transform import InputFile, validate

    p = Paths.default()
    cur = snapshots.read_current(p)
    built = {}
    for mod in (gt, ei, gle):
        for t in mod.transforms(p):
            files = {}
            for i in t.inputs:
                snap = snapshots.read_manifest(p, cur[i.key])
                assert snap is not None
                files[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
            r = t.run(files)
            validate(t, r.observations)
            built[t.spec.id] = {(o.entity, tuple(sorted(o.dims.items())), o.period): o.value for o in r.observations}
    stage = built["food.faostat.agrifood-emissions-by-stage"]
    assert stage[("WLD", (("stage", "farm-gate"),), "2023")] == 8.0969734689
    animals = built["food.faostat.livestock-ch4-by-animal"]
    assert abs(sum(v for (e, _, y), v in animals.items() if e == "WLD" and y == "2023") - 115.2112597) < 1e-6
    # FAO's "China" (351) is never published beside China, mainland (41 -> CHN).
    for rows in built.values():
        assert "CHN" in {e for e, _, _ in rows}

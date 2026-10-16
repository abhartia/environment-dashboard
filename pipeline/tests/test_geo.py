"""The entity crosswalk (pipeline/geo/entities.csv, envdash/geo.py)."""

from __future__ import annotations

import csv
import json

import pytest

from envdash import canonical, geo, snapshots
from envdash.models import ENTITY, Catalog
from envdash.paths import Paths

from support import fixture


@pytest.fixture(scope="module")
def table() -> geo.EntityTable:
    return geo.read_table(geo.entities_path(Paths.default()))


def test_columns_codes_and_kinds(table):
    header = geo.entities_path(Paths.default()).read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(geo.COLUMNS)
    codes = [e.iso3 for e in table.rows]
    assert len(codes) == len(set(codes)) and codes == sorted(codes)
    assert all(ENTITY.fullmatch(c) for c in codes)
    assert {e.kind for e in table.rows} == {"country", "territory", "aggregate", "station", "region"}
    assert not [c for c in codes if c.isdigit()]  # no UN M49 numeric codes
    for e in table.rows:
        if e.kind in ("aggregate", "station", "region"):
            assert e.ne_adm0_a3 == "" and e.ne_iso_a3_eh == ""
    kinds = {e.iso3: e.kind for e in table.rows}
    regions = [e for e in table.rows if e.kind == "region"]
    assert len(regions) == 3495
    assert all(len(e.member_of) == 1 and kinds[e.member_of[0]] in ("country", "territory") for e in regions)
    assert all(e.iso3.split(".")[0] == e.member_of[0] or e.iso3.startswith("KSV.") for e in regions)


def test_natural_earth_identifier_rules(table):
    e = {r.iso3: r for r in table.rows}
    # ISO_A3 is -99 for France and Norway in Natural Earth; ISO_A3_EH carries the code.
    assert (e["FRA"].ne_adm0_a3, e["FRA"].ne_iso_a3_eh, e["FRA"].kind) == ("FRA", "FRA", "country")
    assert (e["NOR"].ne_adm0_a3, e["NOR"].ne_iso_a3_eh) == ("NOR", "NOR")
    # ISO_A3_EH -99: the code is ADM0_A3.
    assert (e["KOS"].ne_adm0_a3, e["KOS"].ne_iso_a3_eh) == ("KOS", "")
    # One ISO_A3_EH (AUS) on three polygons: the polygon whose ADM0_A3 is AUS keeps it.
    assert e["AUS"].ne_adm0_a3 == "AUS"
    assert (e["IOA"].ne_iso_a3_eh, e["IOA"].kind) == ("AUS", "territory")
    assert e["ATC"].ne_iso_a3_eh == "AUS"
    # Tiny-country points with no polygon at 1:50m.
    assert (e["GLP"].ne_adm0_a3, e["GLP"].ne_iso_a3_eh, e["GLP"].kind) == ("", "GLP", "territory")
    assert (e["MLO"].kind, e["WLD"].kind, e["EU27"].kind) == ("station", "aggregate", "aggregate")
    eu = sorted(r.iso3 for r in table.rows if "EU27" in r.member_of)
    assert eu == sorted(geo.EU27_MEMBERS) and len(eu) == 27


def test_resolve_never_guesses(table):
    assert geo.resolve("FRA", "iso3", entities=table) == "FRA"
    assert geo.resolve("PSX", "ne_adm0_a3", entities=table) == "PSE"
    assert geo.resolve("France", "name", entities=table) == "FRA"
    for code, scheme in (("XXX", "iso3"), ("france", "name"), ("Fra", "iso3"), ("-99", "ne_iso_a3_eh")):
        with pytest.raises(geo.UnknownEntity):
            geo.resolve(code, scheme, entities=table)
    with pytest.raises(geo.UnknownEntity, match="names 3 entities"):
        geo.resolve("AUS", "ne_iso_a3_eh", entities=table)
    with pytest.raises(ValueError, match="unknown scheme"):
        geo.resolve("FRA", "m49", entities=table)


def test_source_alias_tables(table):
    assert geo.resolve("KSV", "gcp-fossil-co2-2025", entities=table) == "KOS"
    assert geo.resolve("XIA", "gcp-fossil-co2-2025", entities=table) == "INTL_AIR"
    assert geo.resolve("Kuwaiti Oil Fires", "gcp-fossil-co2-2025", entities=table) == "KWT_OILFIRES"
    assert geo.resolve("DEU", "gcp-fossil-co2-2025", entities=table) == "DEU"
    assert geo.resolve("GLOBAL", "jones-2025-national-contributions", entities=table) == "WLD"
    assert geo.resolve("EU27", "jones-2025-national-contributions", entities=table) == "EU27"
    with pytest.raises(geo.UnknownEntity, match="SOURCE_SCHEMES"):
        geo.resolve("ANNEXI", "jones-2025-national-contributions", entities=table)
    for scheme in geo.SOURCE_SCHEMES.values():
        for target in scheme.aliases.values():
            geo.entity(target, entities=table)


def test_every_published_entity_is_in_the_table(table):
    catalog = Catalog.model_validate_json((Paths.default().data / "v1" / "catalog.json").read_bytes())
    for entry in catalog.indicators:
        for code in entry.entities:
            geo.entity(code, entities=table)


def test_dbf_reader_on_real_tiny_countries_zip():
    path, _ = fixture("natural-earth", "admin-0-tiny-countries-50m")
    rows = geo.shapefile_records(path.read_bytes())
    assert len(rows) == 76
    smr = [r for r in rows if r["ADM0_A3"] == "SMR"]
    assert smr and smr[0]["TYPE"] == "Sovereign country" and smr[0]["ISO_A3_EH"] == "SMR"
    assert all("\x00" not in v for r in rows for v in r.values())


@pytest.mark.snapshot
def test_entities_csv_is_rebuilt_byte_identical_from_the_current_snapshots():
    paths = Paths.default()
    data, side = geo.build(paths)
    out = geo.entities_path(paths)
    assert data == out.read_bytes(), "run: uv run envdash geo build"
    committed = json.loads(out.with_name("entities.provenance.json").read_text())
    assert committed == side and committed["sha256"] == canonical.sha256_bytes(data)
    current = snapshots.read_current(paths)
    for k, sha in committed["inputs"].items():
        assert current[k] == sha


# --- CCKP regions -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cckp_names() -> dict[str, str]:
    path, _ = fixture("wb-cckp", "subnational-names")
    return geo.read_cckp_names(path.read_bytes())


@pytest.fixture(scope="module")
def places(table) -> list[geo.Entity]:
    return [e for e in table.rows if e.kind != "region"]


def test_entity_codes_take_cckp_region_codes():
    for code in ("IND", "EU27", "INTL_BUNKERS", "IND.11510", "CHN.147295898", "BES.7500175101", "KSV.750081"):
        assert ENTITY.fullmatch(code), code
    for code in ("IND.", "ind.11510", "IND.1234567890123", "INDI.1", "IN.115", "IND.115.1", "IND-11510"):
        assert not ENTITY.fullmatch(code), code


def test_cckp_regions_from_the_real_names_workbook(cckp_names, places, table):
    assert (sum("." not in c for c in cckp_names), sum("." in c for c in cckp_names)) == (246, 3530)
    rows = geo.cckp_regions(cckp_names, places)
    # 3,530 regions less the 32 DIS.* units and the three CCKP lists under China for Hong Kong, Macao and Taiwan.
    assert len(rows) == 3530 - 32 - 3 == 3495
    # The committed table holds exactly these rows.
    assert rows == [e for e in table.rows if e.kind == "region"]
    e = {r.iso3: r for r in rows}
    assert (e["IND.11510"].name, e["IND.11510"].member_of, e["IND.11510"].kind) == ("Delhi", ("IND",), "region")
    assert e["USA.2593224"].name == "Georgia" and e["KEN.13344"].name == "Turkana"
    # Kosovo's regions keep CCKP's prefix and belong to KOS.
    assert e["KSV.750081"].member_of == ("KOS",)
    # Placeholders and names that are codes are named by rule, never borrowed.
    assert e["AIA.9416"].name == "Unnamed region of Anguilla (AIA.9416)"
    assert e["BRA.37692"].name == "Unnamed region of Brazil (BRA.37692)"
    assert e["HKG.33364910"].name == "Unnamed region of Hong Kong S.A.R. (HKG.33364910)"
    assert sum(r.name.startswith("Unnamed region of ") for r in rows) == 68 + 3
    # CCKP's garbled Mexican names are named as the World Bank's boundaries name them; no other name is changed.
    assert (e["MEX.1625"].name, e["MEX.16224"].name) == ("Ciudad de México", "Yucatán")
    assert {
        r.iso3 for r in rows if r.name != cckp_names[r.iso3] and not r.name.startswith("Unnamed region of ")
    } == set(geo.GARBLED_NAMES)
    assert not [c for c in e if c.startswith("DIS.") or c in geo.CHINA_LISTED]
    assert {p: sum(c.startswith(f"{p}.") for c in e) for p in ("IND", "KEN", "BRA", "CHN")} == {
        "IND": 35,
        "KEN": 47,
        "BRA": 31,
        "CHN": 31,
    }
    assert all(r.ne_adm0_a3 == "" and r.ne_iso_a3_eh == "" and len(r.member_of) == 1 for r in rows)


def test_china_lists_hong_kong_macao_and_taiwan_only_as_declared(cckp_names, places):
    assert {c: cckp_names[c] for c in geo.CHINA_LISTED} == geo.CHINA_LISTED
    with pytest.raises(ValueError, match="under China for Hong Kong, Macao or Taiwan"):
        geo.cckp_regions({**cckp_names, "CHN.99": "Taiwan"}, places)
    renamed = {**cckp_names, "CHN.147295925": "Taiwan Province"}
    with pytest.raises(ValueError, match="under China for Hong Kong, Macao or Taiwan"):
        geo.cckp_regions(renamed, places)
    gone = {k: v for k, v in cckp_names.items() if k != "CHN.1491879"}
    with pytest.raises(ValueError, match="under China for Hong Kong, Macao or Taiwan"):
        geo.cckp_regions(gone, places)


def test_garbled_names_are_the_shapes_they_are_declared_to_match():
    declared = {
        r["cckp_code"]: r
        for r in csv.DictReader((Paths.default().repo / "pipeline/geo/cckp-adm1-declared.csv").open(encoding="utf-8"))
    }
    for code, (garbled, name) in geo.GARBLED_NAMES.items():
        assert declared[code]["decision"] == "accept" and declared[code]["v1_name"] == name, code
        assert f"({garbled} for {name})" in declared[code]["reason"], code


def test_a_garbled_name_that_changes_stops_the_build(cckp_names, places):
    with pytest.raises(ValueError, match="GARBLED_NAMES"):
        geo.cckp_regions({**cckp_names, "MEX.1625": "Ciudad de México"}, places)


def test_cckp_names_that_do_not_fit_the_declared_rules_stop_the_build(cckp_names, places):
    # A placeholder spelled differently, or one more or fewer.
    with pytest.raises(ValueError, match="placeholder region names"):
        geo.cckp_regions({**cckp_names, "BRA.37692": "Name unknown"}, places)
    with pytest.raises(ValueError, match="placeholder region names"):
        geo.cckp_regions({**cckp_names, "IND.11510": "Name Unknown"}, places)
    # A region named by its own code that is not declared.
    with pytest.raises(ValueError, match="named by their own code"):
        geo.cckp_regions({**cckp_names, "IND.11510": "IND.11510"}, places)
    # DIS.* units: exactly 32.
    with pytest.raises(ValueError, match="31 DIS"):
        geo.cckp_regions({k: v for k, v in cckp_names.items() if k != "DIS.990011"}, places)
    # A region whose prefix is not a country of the file.
    with pytest.raises(ValueError, match="prefix is not a country"):
        geo.cckp_regions({k: v for k, v in cckp_names.items() if k != "LUX"}, places)
    # A country of the file with no entity here.
    with pytest.raises(ValueError, match="'LUX' has no entity"):
        geo.cckp_regions(cckp_names, [p for p in places if p.iso3 != "LUX"])
    # Two regions of one country with one name.
    with pytest.raises(ValueError, match="both named 'Delhi'"):
        geo.cckp_regions({**cckp_names, "IND.11511": "Delhi"}, places)


def test_regions_never_make_a_name_ambiguous(table):
    # Georgia is a country and a US state; Luxembourg a country and one of its districts; Punjab a region of two.
    assert {e.iso3 for e in table.rows if e.name == "Georgia"} == {"GEO", "USA.2593224"}
    assert {e.iso3 for e in table.rows if e.name == "Luxembourg"} == {"LUX", "LUX.1481878"}
    assert geo.resolve("Georgia", "name", entities=table) == "GEO"
    assert geo.resolve("Luxembourg", "name", entities=table) == "LUX"
    with pytest.raises(geo.UnknownEntity):
        geo.resolve("Delhi", "name", entities=table)
    for column in ("name", "ne_adm0_a3", "ne_iso_a3_eh"):
        assert not [e for rows in table.by(column).values() for e in rows if e.kind == "region"], column
    assert geo.resolve("IND.11510", "iso3", entities=table) == "IND.11510"
    assert geo.entity("USA.2593224", entities=table).member_of == ("USA",)


def test_cckp_aliases_agree_with_the_transform():
    from envdash.transforms.country import cckp

    assert geo.SOURCE_SCHEMES["wb-cckp"].aliases == cckp.ALIASES

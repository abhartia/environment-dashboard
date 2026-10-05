"""The entity crosswalk (pipeline/geo/entities.csv, envdash/geo.py)."""

from __future__ import annotations

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
    assert {e.kind for e in table.rows} == {"country", "territory", "aggregate", "station"}
    assert not [c for c in codes if c.isdigit()]  # no UN M49 numeric codes
    for e in table.rows:
        if e.kind in ("aggregate", "station"):
            assert e.ne_adm0_a3 == "" and e.ne_iso_a3_eh == ""


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

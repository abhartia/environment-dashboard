"""CCKP's regions matched to World Bank Official Boundaries GAD V1 admin-1 shapes (envdash/geo_shapes.py).

The join reads the whole WB_GAD_ADM1.dbf (2,040,730 bytes) and CCKP's names workbook. A .dbf cannot be cut
byte-exactly (its header states the record count), and the file is over the whole-file fixture limit, so these
tests read the current snapshots from the cache and are marked `snapshot` (run with `uv run pytest -m snapshot`
after `envdash fetch -s wb-gad-v1 -s wb-cckp` or `envdash snapshots pull`), as for the other un-sliceable formats.
The per-country result is committed as tests/expected/cckp-join-by-country.csv, so any change in the files or the
rules shows as a diff of that table.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from collections import Counter
from pathlib import Path

import pytest

from envdash import geo
from envdash import geo_shapes as gs
from envdash.paths import Paths

pytestmark = pytest.mark.snapshot

EXPECTED = Path(__file__).parent / "expected" / "cckp-join-by-country.csv"
TABLE_COLUMNS = (
    "country",
    "cckp_regions",
    "shapes",
    "gaul",
    "adm1cd",
    "declared",
    "name",
    "unjoined",
    "shapeless",
    "unmatched",
    "name_rule",
)


@pytest.fixture(scope="module")
def m() -> gs.Matching:
    paths = Paths.default()
    inputs = gs.load_inputs(paths)
    return gs.matching(paths, inputs, gs.read_layers(inputs, ("adm0", "adm1", "ndlsa")))


@pytest.fixture(scope="module")
def j(m) -> gs.Join:
    return m.join()


def table(j: gs.Join) -> list[dict[str, str]]:
    rows = []
    for c in j.countries:
        rows.append(
            {
                "country": c.entity,
                "cckp_regions": str(c.cckp_regions),
                "shapes": str(c.shapes),
                **{k: str(c.joined.get(k, 0)) for k in ("gaul", "adm1cd", "declared", "name")},
                "unjoined": str(len(c.unjoined)),
                "shapeless": str(len(c.shapeless)),
                "unmatched": str(len(c.unmatched)),
                "name_rule": c.name_rule,
            }
        )
    return rows


def table_bytes(j: gs.Join) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, TABLE_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(table(j))
    return buf.getvalue().encode("utf-8")


def pairs_of(j: gs.Join, country: str) -> list[gs.Pair]:
    return [p for p in j.pairs if p.country == country]


def test_the_table_by_country_is_the_committed_one(j):
    assert table_bytes(j) == EXPECTED.read_bytes(), (
        "the join changed: rewrite the table with `uv run python tests/test_geo_cckp_join.py` and review its diff"
    )


def test_india_35_of_35_by_its_adm1cd_codes(j):
    india = next(c for c in j.countries if c.entity == "IND")
    assert (india.cckp_regions, india.shapes, india.joined) == (35, 35, {"adm1cd": 35})
    delhi = next(p for p in pairs_of(j, "IND") if p.cckp_code == "IND.11510")
    assert delhi.cckp_name == "Delhi" and delhi.record.attrs["ADM1CD_t"] == "IND010" and delhi.names_equal
    # Jammu and Kashmir and Ladakh are disputed areas in GAD V1, not Indian states, and CCKP has no region for them.
    assert not any("Kashmir" in (p.cckp_name or "") for p in pairs_of(j, "IND"))


def test_kenya_47_of_47_by_name_after_its_code_matches_are_refused(j, m):
    kenya = next(c for c in j.countries if c.entity == "KEN")
    assert (kenya.cckp_regions, kenya.shapes, kenya.unjoined, kenya.unmatched) == (47, 47, [], [])
    # CCKP numbers Kenya's counties in its own order: 45 of its codes name another county's record and are declared
    # rejected; the 2 whose record happens to bear the same name match by code.
    assert kenya.joined == {"name": 45, "adm1cd": 2}
    rejected = [d for d in m.declared if d.cckp_code.startswith("KEN.") and d.decision == "reject"]
    assert len(rejected) == 45
    uasin = next(p for p in pairs_of(j, "KEN") if p.cckp_code == "KEN.1331")
    assert uasin.cckp_name == "Uasin Gishu" and uasin.record.attrs["NAM_1"] == "Uasin Gishu" and uasin.method == "name"


def test_nigeria_36_of_37_by_name_and_abuja_by_declaration(j):
    nigeria = next(c for c in j.countries if c.entity == "NGA")
    assert (nigeria.cckp_regions, nigeria.shapes, nigeria.unjoined) == (37, 37, [])
    assert nigeria.joined == {"name": 36, "declared": 1}
    abuja = next(p for p in pairs_of(j, "NGA") if p.cckp_name == "Abuja")
    assert abuja.record.attrs["NAM_1"] == "Federal Capital Territory" and abuja.method == "declared"
    # GAD V1 writes "Akwa lbom" (a lower-case L) in NAM_1; another of its own name fields has "Akwa Ibom".
    akwa = next(p for p in pairs_of(j, "NGA") if p.cckp_name == "Akwa Ibom")
    assert akwa.record.attrs["NAM_1"] == "Akwa lbom" and akwa.method == "name"


def test_a_shared_gaul_code_takes_only_the_record_whose_name_agrees(j, m):
    # Bogotá's record carries Cundinamarca's GAUL code (and, in NAM_1_STAT, its name); CCKP lists Bogotá apart.
    cund = [p for p in pairs_of(j, "COL") if p.cckp_name == "Cundinamarca"]
    assert [(p.record.attrs["NAM_1"], p.method) for p in cund] == [("Cundinamarca", "gaul")]
    bogota = next(p for p in pairs_of(j, "COL") if p.cckp_name == "Bogotá, D.C.")
    assert bogota.record.attrs["NAM_1"] == "Bogotá, D.C." and bogota.method == "name"
    # Wisconsin is written twice in GAD V1, with the same GAUL code and name: CCKP's Wisconsin takes both.
    wis = [p for p in pairs_of(j, "USA") if p.cckp_name == "Wisconsin"]
    assert len(wis) == 2 and {p.method for p in wis} == {"gaul"}


def test_every_region_once_and_every_record_at_most_once(j, m):
    regions = {c for c in m.names if "." in c and not c.startswith("DIS.")} - set(geo.CHINA_LISTED)
    seen = Counter(p.cckp_code for p in j.pairs if p.cckp_code)
    multi = {c for c, n in seen.items() if n > 1}
    # A region takes several records only when every one bears its code and name (Wisconsin, written twice).
    for code in multi:
        assert {p.method for p in j.pairs if p.cckp_code == code} <= {"gaul", "adm1cd", "declared"}
    assert set(seen) == regions
    records = Counter(p.record.fid for p in j.pairs if p.record is not None)
    assert max(records.values()) == 1 and set(records) == {r.fid for r in m.adm1}


def test_withheld_name_rule_only_where_the_counts_differ(j):
    for c in j.countries:
        assert (c.name_rule == "withheld") == (c.cckp_regions != c.shapes), c.entity
    indonesia = next(c for c in j.countries if c.entity == "IDN")
    # CCKP's 33 provinces predate the splits of Kalimantan (2012) and Papua (2022); GAD V1 has 38.
    assert (indonesia.cckp_regions, indonesia.shapes, indonesia.name_rule) == (33, 38, "withheld")
    assert "name" not in indonesia.joined


def test_dis_units_are_left_out_by_count(m):
    names = dict(m.names)
    del names[min(c for c in names if c.startswith("DIS."))]
    with pytest.raises(gs.GeoShapesError, match="31 DIS"):
        gs.join(names, m.adm1, m.declared, m.entity_of)


def test_an_undeclared_code_match_with_another_name_stops_the_build(m):
    declared = [d for d in m.declared if d.cckp_code != "KEN.1331"]
    with pytest.raises(gs.GeoShapesError, match=r"KEN\.1331 'Uasin Gishu' matches .* names differ: declare"):
        gs.join(m.names, m.adm1, declared, m.entity_of)


def test_a_declared_row_must_still_describe_the_file(m):
    row = next(d for d in m.declared if d.cckp_code == "KEN.1331")
    changed = [dataclasses.replace(d, name="Nairobi") if d is row else d for d in m.declared]
    with pytest.raises(gs.GeoShapesError, match="record 598 is now"):
        gs.join(m.names, m.adm1, changed, m.entity_of)


def test_a_rejection_no_rule_needs_any_more_stops_the_build(m):
    # India's Delhi matches its record by code with the same name; a rejection of some other Indian record for it
    # refuses nothing.
    other = next(r for r in m.adm1 if r.attrs.get("ADM1CD_t") == "IND011")
    extra = gs.Declared("IND.11510", other.fid, "IND011", other.attrs["NAM_1"], "reject", "a test")
    with pytest.raises(gs.GeoShapesError, match="rejected pairs no code rule makes"):
        gs.join(m.names, m.adm1, [*m.declared, extra], m.entity_of)


def test_a_record_used_twice_stops_the_build(m):
    # Abuja is declared onto the Federal Capital Territory's record; declaring Lagos onto it too uses it twice.
    fct = next(r for r in m.adm1 if r.iso == "NGA" and r.attrs["NAM_1"] == "Federal Capital Territory")
    lagos = next(c for c, n in m.names.items() if c.startswith("NGA.") and n == "Lagos")
    extra = gs.Declared(lagos, fct.fid, "", "Federal Capital Territory", "accept", "a test")
    with pytest.raises(gs.GeoShapesError, match=rf"record {fct.fid} .* would be used twice"):
        gs.join(m.names, m.adm1, [*m.declared, extra], m.entity_of)


def test_an_accept_a_code_rule_already_makes_stops_the_build(m):
    # Delhi matches its record by the ADM1CD rule, the names agreeing: an accept of the same pair is not needed.
    delhi = next(r for r in m.adm1 if r.attrs.get("ADM1CD_t") == "IND010")
    extra = gs.Declared("IND.11510", delhi.fid, "IND010", "Delhi", "accept", "a test")
    with pytest.raises(gs.GeoShapesError, match=r"IND\.11510 'Delhi' and record \d+ are matched by the adm1cd rule"):
        gs.join(m.names, m.adm1, [*m.declared, extra], m.entity_of)


def test_an_accept_the_name_rule_already_makes_stops_the_build(m):
    # Lagos matches its record by name in Nigeria (37 regions, 37 shapes): an accept of the same pair is not needed.
    lagos = next(c for c, n in m.names.items() if c.startswith("NGA.") and n == "Lagos")
    rec = next(r for r in m.adm1 if r.iso == "NGA" and r.attrs["NAM_1"] == "Lagos")
    extra = gs.Declared(lagos, rec.fid, rec.attrs["ADM1CD_t"] or "", "Lagos", "accept", "a test")
    with pytest.raises(gs.GeoShapesError, match=r"the name rule matches them: the accept is no longer needed"):
        gs.join(m.names, m.adm1, [*m.declared, extra], m.entity_of)


def test_china_lists_hong_kong_macao_and_taiwan_as_places_of_their_own(j, m):
    # CCKP's units for them under China are left out (geo.CHINA_LISTED); China's 31 regions then match its 31 shapes.
    china = next(c for c in j.countries if c.entity == "CHN")
    assert (china.cckp_regions, china.shapes, china.joined, china.unjoined) == (31, 31, {"gaul": 31}, [])
    assert not {p.cckp_code for p in j.pairs} & set(geo.CHINA_LISTED)
    for e in ("HKG", "MAC", "TWN"):
        place = next(c for c in j.countries if c.entity == e)
        assert (place.cckp_regions, place.joined) == (1, {"declared": 1}), e
    renamed = {**m.names, "CHN.33364910": "Hong Kong"}
    with pytest.raises(gs.GeoShapesError, match=r"as geo\.CHINA_LISTED declares"):
        gs.join(renamed, m.adm1, m.declared, m.entity_of)


def test_the_philippines_17_of_17_on_the_world_banks_2013_shapes(j):
    philippines = next(c for c in j.countries if c.entity == "PHL")
    assert (philippines.cckp_regions, philippines.shapes, philippines.joined) == (17, 17, {"declared": 17})
    # V1 names record 1988 ARMM in NAM_1 and Bangsamoro (BARMM) in P_NAME_1; its shape predates the 2019 plebiscite,
    # as Region 12's does (see the reasons in the declared pairs).
    barmm = next(p for p in pairs_of(j, "PHL") if p.cckp_code == "PHL.1961")
    assert barmm.cckp_name == "Bangsamoro Autonomous Region in Muslim Mindanao"
    assert barmm.record.attrs["P_NAME_1"] == "Bangsamoro Autonomous Region In Muslim Mindanao (BARMM)"
    assert {p.record.attrs["GEOM_SRCE"] for p in pairs_of(j, "PHL")} == {"UN SALB"}


def test_the_entity_table_holds_every_region_matched(m):
    paths = Paths.default()
    inputs = gs.load_inputs(paths)
    sha = inputs.snaps[f"{gs.CCKP}/{gs.NAMES_ARTIFACT}"].sha256
    regions, _ = gs.cckp_regions(m.names)
    gs.check_region_entities(paths, sha, regions, m.entity_of)
    with pytest.raises(gs.GeoShapesError, match="was built from"):
        gs.check_region_entities(paths, "0" * 64, regions, m.entity_of)
    # Hong Kong's unit under China is not an entity of China.
    with pytest.raises(gs.GeoShapesError, match=r"not regions of their country in entities.csv: \['CHN.33364910'\]"):
        gs.check_region_entities(paths, sha, {**regions, "CHN.33364910": "Hong Kong, SAR"}, m.entity_of)


def test_two_code_rules_pointing_at_different_records_stop_the_build(m):
    # A copy of Goa's record carrying Delhi's GAUL codes and name: the GAUL rule then points at it while the ADM1CD
    # rule points at Delhi's own record.
    goa = next(r for r in m.adm1 if r.attrs.get("ADM1CD_t") == "IND011")
    forged = dataclasses.replace(goa, attrs={**goa.attrs, "GAUL_0": 115, "GAUL_1": 10, "NAM_1": "Delhi"})
    adm1 = [forged if r is goa else r for r in m.adm1]
    with pytest.raises(gs.GeoShapesError, match="the gaul rule gives records"):
        gs.join(m.names, adm1, m.declared, m.entity_of)


if __name__ == "__main__":  # rewrite the committed table from the current snapshots
    _paths = Paths.default()
    _inputs = gs.load_inputs(_paths)
    EXPECTED.write_bytes(table_bytes(gs.matching(_paths, _inputs, gs.read_layers(_inputs)).join()))
    print(f"wrote {EXPECTED}")

"""FAOSTAT World Census of Agriculture (WCAD): holdings in total and by land-size class, per country and census.

Fixtures are byte-exact slices of the real WCAD snapshot (a266d08687d4…, 2026-10-08), cut by
tests/fixtures/faostat/make_zip_fixture.py: the rows of one area for the item/element pairs used (India, Ecuador,
Benin, the United States, Cambodia, FAO's area 351 "China", Czechoslovakia) and the whole flag codebook. Their sidecars
are checked by test_faostat_emissions.py with every other tests/fixtures/faostat/*/ sidecar. Slices hold fewer rows
than the full file, so the catalogue's FileRows is checked against the sidecar's data_rows_total.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.food import faostat_wcad as w
from envdash.transforms.food.faostat_bulk import FaostatBulkError, catalogue_entry, read_flags

FIXTURES = Path(__file__).parent / "fixtures" / "faostat"
ART = FIXTURES / "world-census-agriculture"
CATALOGUE = FIXTURES / "datasets-catalogue" / "54b055217bee.json"
SLICES = ("india", "ecuador", "benin", "usa", "cambodia", "china-group", "czechoslovakia")


def _lines(*names: str) -> list[bytes]:
    out: list[bytes] = []
    for i, name in enumerate(names):
        lines = (ART / f"a266d08687d4.{name}.csv").read_bytes().splitlines(keepends=True)
        out += lines if i == 0 else lines[1:]
    return out


def _flags() -> dict[str, str]:
    return read_flags((ART / "a266d08687d4.flags.csv").read_bytes(), w.FLAGS_MEMBER)


def _parsed(lines=None) -> w.Parsed:
    return w.parse(w.read(lines if lines is not None else _lines(*SLICES)), _flags())


def _by(obs):
    return {(o.entity, o.dims.get("land-size"), o.period): o for o in obs}


def test_total_holdings_per_country_and_census():
    p = _parsed()
    by = _by(p.total)
    # As printed: India 146,453,741 holdings in the 2015/16 census (WCA 2020 round), flag A.
    india = by[("IND", None, "2015/2016")]
    assert india.value == 146_453_741
    assert india.note == "WCA 2020 round, census 2015/16. FAO flag A: Official figure."
    assert by[("IND", None, "1976/1977")].note.startswith("WCA 1980 round, census 1976/77.")
    # Two censuses in one round (United States, 2017 and 2022) are two observations.
    assert by[("USA", None, "2017")].value == 2_042_220 and by[("USA", None, "2022")].value == 1_900_487
    # A census over several years, and a split year across a century.
    assert by[("BEN", None, "2018/2021")].value == 913_415
    assert by[("ECU", None, "1999/2000")].value == 842_882
    assert by[("ECU", None, "1999/2000")].note.startswith("WCA 2000 round, census 1999/00. FAO flag A")
    assert "FAO's note: The census covered agricultural production unit (UPA)" in by[("ECU", None, "1999/2000")].note
    # No world or regional total; FAO's area 351 "China" and Czechoslovakia are left out.
    assert {o.entity for o in p.total} == {"IND", "ECU", "BEN", "USA", "KHM"}
    assert any("not assigned to mainland China (CHN)" in s for s in p.steps)
    assert any("Czechoslovakia" in s for s in p.steps)
    assert any("Nothing is added up" in s for s in p.steps)


def test_holdings_and_area_by_land_size():
    p = _parsed()
    number, area = _by(p.by_size[w.NUMBER[0]]), _by(p.by_size[w.AREA[0]])
    assert number[("IND", "0-1", "2015/2016")].value == 100_251_309
    assert number[("IND", "2-5", "1960/1961")].value == 11_547_000
    assert area[("IND", "2-5", "1960/1961")].value == 36_717_000
    assert number[("KHM", "0-1", "2013")].value == 869_493 and area[("KHM", "0-1", "2013")].value == 395_290
    assert number[("ECU", "0-1", "1999/2000")].value == 248_398
    assert {o.dims["land-size"] for o in p.by_size[w.AREA[0]]} == {"0-1", "1-2", "2-5"}


def test_census_years_become_iso_periods():
    assert w.census_period("2015/16", "201516", "x") == ("2015/2016", 2015, 2016)
    assert w.census_period("1999/00", "199900", "x") == ("1999/2000", 1999, 2000)
    assert w.census_period("2018-2021", "20182021", "x") == ("2018/2021", 2018, 2021)
    assert w.census_period("2013", "2013", "x") == ("2013", 2013, 2013)
    with pytest.raises(FaostatBulkError):
        w.census_period("2015/17", "201517", "x")
    with pytest.raises(FaostatBulkError):
        w.census_period("2021-2018", "20212018", "x")
    with pytest.raises(FaostatBulkError):
        w.census_period("2015/16", "201617", "x")


def test_refuses_renamed_items_and_nested_classes_side_by_side():
    lines = _lines("india")
    renamed = [ln.replace(b'"Holdings with land size 0-<1"', b'"Holdings with land size 0-<2"') for ln in lines]
    with pytest.raises(FaostatBulkError, match="named"):
        _parsed(renamed)
    # India 1960/61 reports 2-<5; the same row relabelled as the nested class 2-<3 would sit beside it.
    row = next(ln for ln in lines if b'"270033","Holdings with land size 2-<5","60850"' in ln and b'"196061"' in ln)
    nested = row.replace(b'"270033","Holdings with land size 2-<5"', b'"270032","Holdings with land size 2-<3"')
    with pytest.raises(FaostatBulkError, match="nested"):
        _parsed([*lines, nested])


def test_vintage_from_catalogue():
    side = json.loads((ART / "a266d08687d4.india.csv.provenance.json").read_text())
    updated, rows = catalogue_entry(CATALOGUE.read_bytes(), w.DATASET_CODE, side["url"])
    assert updated.isoformat() == "2026-04-27"
    assert rows == side["data_rows_total"] == 28_565


def test_specs_publish_no_world_total():
    specs = {t.spec.id: t.spec for t in w.transforms(Paths.default())}
    assert set(specs) == {
        "farms.faostat-wcad.holdings",
        "farms.faostat-wcad.holdings-by-land-size",
        "farms.faostat-wcad.area-by-land-size",
    }
    for s in specs.values():
        assert s.geo_coverage == "country" and s.headline_entity == "IND"


@pytest.mark.snapshot
def test_builds_from_the_snapshot():
    p = Paths.default()
    cur = snapshots.read_current(p)
    for t in w.transforms(p):
        files = {}
        for i in t.inputs:
            snap = snapshots.read_manifest(p, cur[i.key])
            assert snap is not None
            files[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
        r = t.run(files)
        validate(t, r.observations)
        assert "WLD" not in {o.entity for o in r.observations}
        assert "CHN" not in {o.entity for o in r.observations}

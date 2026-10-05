"""World Bank CCKP country temperature (ERA5) and hot days (CMIP6 hd35).

Fixtures are whole files of the wb-cckp snapshots of 2026-10-05 (tests/fixtures/wb-cckp, each under 6 kB): the global
ERA5 series and climatology, the country climatology and all twelve hd35 files. The country ERA5 series (296 kB) is
read from the real snapshot in the tests marked snapshot.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.country import cckp
from envdash.transforms.country.cckp import (
    CLIM_GLOBAL,
    HD35_INPUTS,
    NO_ENTITY,
    SCENARIOS,
    SOURCE,
    TAS_GLOBAL,
    CckpFormatError,
    Era5,
    change_observations,
    check_climatology,
    collection_of,
    entities_of,
    expect,
    hd35_observations,
    read_file,
    read_payload,
)

from support import fixture

LEFT_OUT = ["BVT", "CCK", "GUF", "MYT", "REU", "SJM", "UMI"]


def _input(artifact_id: str, raw: bytes | None = None, tmp_path=None) -> InputFile:
    """The fixture of (wb-cckp, artifact) as an InputFile, with its real URL and access date. With `raw`, the bytes
    are written to tmp_path instead (a test's own change to real bytes)."""
    path, meta = fixture(SOURCE, artifact_id)
    if raw is not None:
        path = tmp_path / f"{artifact_id}.json"
        path.write_bytes(raw)
    snap = Snapshot(
        sha256=meta["fixture_sha256"],
        bytes=meta["fixture_bytes"],
        source_id=SOURCE,
        artifact_id=artifact_id,
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    return InputFile(path, snap)


def _hd35_files() -> dict[str, InputFile]:
    return {i.key: _input(i.artifact_id) for i in HD35_INPUTS.values()}


def _transforms() -> dict[str, object]:
    return {t.spec.id: t for t in discover(Paths.default()) if t.spec.id.split(".")[1] == SOURCE}


# --- registry and declarations ------------------------------------------------------------------------------------


def test_transforms_read_only_registered_artifacts():
    src = load_registry(Paths.default()).sources[SOURCE]
    registered = {a.id for a in src.artifacts}
    ts = _transforms()
    assert set(ts) == {
        "temp.wb-cckp.era5-annual-absolute",
        "temp.wb-cckp.era5-annual-1991-2020",
        "hot-days-35c.wb-cckp.cmip6",
    }
    for t in ts.values():
        assert {i.artifact_id for i in t.inputs} <= registered
    assert len(ts["hot-days-35c.wb-cckp.cmip6"].inputs) == 12


def test_collection_is_read_from_the_url():
    _, meta = fixture(SOURCE, "cmip6-hd35-2040-2059-ssp245-p90")
    c = collection_of(meta["url"])
    assert (c.variable, c.start, c.end, c.statistic, c.scenario, c.geocode) == (
        "hd35",
        2040,
        2059,
        "p90",
        "ssp245",
        "all_countries",
    )
    with pytest.raises(CckpFormatError, match="statistic"):
        expect(c, "x", statistic="median")
    with pytest.raises(CckpFormatError, match="not a CCKP collection URL"):
        collection_of(meta["url"].replace("_annual_", "_monthly_"))


# --- hot days -----------------------------------------------------------------------------------------------------


def test_hd35_publishes_median_with_the_10_90_range_as_printed():
    obs, left_out = hd35_observations(_hd35_files())
    by = {(o.entity, o.dims["scenario"]): o for o in obs}
    # As printed in the files (the source research read the same two medians by hand on 2026-10-04).
    ind_hist, ind_245 = by[("IND", "historical")], by[("IND", "ssp245")]
    assert (ind_hist.period, ind_hist.value, ind_hist.lower, ind_hist.upper) == ("1995/2014", 77.88, 70.04, 84.89)
    assert (ind_245.period, ind_245.value, ind_245.lower, ind_245.upper) == ("2040/2059", 94.78, 78.1, 112.6)
    assert ind_hist.status == "final" and ind_245.status == "projection" and ind_245.interval == "range"
    assert by[("ARE", "historical")].value == 183.07
    assert by[("AFG", "ssp126")].value == 58.73
    # KSV is published as KOS; the seven areas without an entity are left out, never folded into another one.
    assert ("KOS", "ssp585") in by and not any(e in {"KSV", *LEFT_OUT} for e, _ in by)
    assert left_out == LEFT_OUT
    assert len({e for e, _ in by}) == 239 and len(obs) == 239 * len(SCENARIOS)


def test_hd35_passes_its_validation():
    t = _transforms()["hot-days-35c.wb-cckp.cmip6"]
    res = t.run(_hd35_files())
    validate(t, res.observations)
    assert res.changes is None
    assert res.vintage == "cmip6-x0.25 hd35, fetched 2026-10-05"
    assert "Réunion (REU)" in res.steps[-1] and "none was added to another entity" in res.steps[-1]


def test_hd35_refuses_a_file_under_the_wrong_artifact():
    files = _hd35_files()
    median = HD35_INPUTS[("ssp245", "median")].key
    files[median] = files[HD35_INPUTS[("ssp245", "p10")].key]
    with pytest.raises(CckpFormatError, match="statistic"):
        hd35_observations(files)
    files = _hd35_files()
    files[median] = files[HD35_INPUTS[("ssp585", "median")].key]
    with pytest.raises(CckpFormatError, match="scenario"):
        hd35_observations(files)


# --- entities -----------------------------------------------------------------------------------------------------


def test_codes_resolve_through_geo_with_declared_aliases_only():
    path, _ = fixture(SOURCE, "era5-tas-climatology-1991-2020-countries")
    codes = set(read_payload(path.read_bytes(), "clim"))
    mapped, left_out = entities_of(codes, "clim")
    assert mapped["KSV"] == "KOS" and mapped["IND"] == "IND" and mapped["FRA"] == "FRA"
    assert left_out == LEFT_OUT == sorted(NO_ENTITY)
    with pytest.raises(CckpFormatError, match="'XKX' has no entity"):
        entities_of(codes | {"XKX"}, "clim")


# --- ERA5 temperature ---------------------------------------------------------------------------------------------


def _global_era5() -> Era5:
    _, annual = read_file(_input(TAS_GLOBAL.artifact_id), TAS_GLOBAL.key, type="timeseries", variable="tas")
    _, clim = read_file(_input(CLIM_GLOBAL.artifact_id), CLIM_GLOBAL.key, type="climatology", start=1991)
    return Era5(
        annual={"WLD": [(int(s[:4]), v) for s, v in annual["GLOBAL"].items()]},
        climatology={"WLD": clim["GLOBAL"]["1991-07"]},
        start=1950,
        end=2025,
        left_out=[],
        vintage="test",
    )


def test_global_series_and_its_change_from_1991_2020():
    e = _global_era5()
    assert [y for y, _ in e.annual["WLD"]] == list(range(1950, 2026))
    assert dict(e.annual["WLD"])[2025] == Decimal("14.97") and e.climatology["WLD"] == Decimal("14.37")
    # Mean of the 30 printed annual values 1991-2020 is 14.373 °C against the printed 14.37.
    assert check_climatology(e) == Decimal("0.003")
    by = {o.period: o.value for o in change_observations(e)}
    assert by["2025"] == 0.6 and by["1950"] == pytest.approx(13.61 - 14.37, abs=1e-12)


def test_a_climatology_from_another_series_is_refused():
    e = _global_era5()
    shifted = Era5(e.annual, {"WLD": e.climatology["WLD"] + Decimal("0.02")}, e.start, e.end, [], "test")
    with pytest.raises(CckpFormatError, match="more than rounding"):
        check_climatology(shifted)


def test_a_missing_year_or_a_null_value_is_refused(tmp_path):
    path, _ = fixture(SOURCE, TAS_GLOBAL.artifact_id)
    raw = path.read_bytes()
    doc = json.loads(raw)
    del doc["data"]["GLOBAL"]["1990-07"]
    gap = _input(TAS_GLOBAL.artifact_id, json.dumps(doc).encode(), tmp_path)
    with pytest.raises(CckpFormatError, match="stamps"):
        read_file(gap, TAS_GLOBAL.key)
    assert b'"2025-07":14.97' in raw
    with pytest.raises(CckpFormatError, match="not a number"):
        read_payload(raw.replace(b'"2025-07":14.97', b'"2025-07":null'), "global")


def test_a_failed_api_response_is_refused():
    path, _ = fixture(SOURCE, CLIM_GLOBAL.artifact_id)
    raw = path.read_bytes()
    assert b'"status":"success"' in raw
    with pytest.raises(CckpFormatError, match="API status"):
        read_payload(raw.replace(b'"status":"success"', b'"status":"error"'), "global")


# --- full snapshots -----------------------------------------------------------------------------------------------


def _current(key: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[key]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(p, sha), snap)


@pytest.mark.snapshot
def test_full_era5_indicators():
    ts = _transforms()
    for tid in ("temp.wb-cckp.era5-annual-absolute", "temp.wb-cckp.era5-annual-1991-2020"):
        t = ts[tid]
        res = t.run({i.key: _current(i.key) for i in t.inputs})
        validate(t, res.observations)
        by = {(o.entity, o.period): o.value for o in res.observations}
        assert len(res.observations) == 240 * 76
        assert res.vintage.startswith("era5-x0.25 1950-2025, fetched ")
        if tid.endswith("absolute"):
            assert (by[("WLD", "2025")], by[("IND", "2025")], by[("KOS", "2025")]) == (14.97, 24.27, 11.75)
            assert res.changes is None
        else:
            assert (by[("WLD", "2025")], by[("IND", "2025")], by[("KOS", "2025")]) == (0.6, 0.06, 1.16)
            assert "largest difference 0.006 °C" in res.steps[3]
            assert res.changes is not None
        assert not {e for e, _ in by} & {"KSV", "GLOBAL", *LEFT_OUT}


@pytest.mark.snapshot
def test_full_country_series_matches_the_country_climatology():
    files = {i.key: _current(i.key) for i in cckp.ERA5_INPUTS}
    e = cckp.read_era5(files)
    assert e.left_out == LEFT_OUT and (e.start, e.end) == (1950, 2025)
    assert check_climatology(e) == Decimal("0.006")

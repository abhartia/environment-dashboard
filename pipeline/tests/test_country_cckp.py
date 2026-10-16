"""World Bank CCKP country temperature (ERA5) and hot days (CMIP6 hd35).

Fixtures are whole files of the wb-cckp snapshots of 2026-10-05 (tests/fixtures/wb-cckp, each under 6 kB): the global
ERA5 series and climatology, the country climatology and all twelve hd35 files; and four whole files of every country
and region (all_countries_subnationals, snapshots of 2026-10-16, about 110 kB each): hd35 1995–2014 median and
2040–2059 SSP2-4.5 median, 10th and 90th percentile. The country ERA5 series (296 kB) and the other 266 region files
are read from the real snapshots in the tests marked snapshot.
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
    SCENARIOS,
    SOURCE,
    STATISTICS,
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

# Areas once left out for want of an entity; published since envdash/geo.py EXTRA_TERRITORIES declares them.
TERRITORIES = ["BVT", "CCK", "GUF", "MYT", "REU", "SJM", "UMI"]


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
    projections = {t for t in ts if t.startswith("future.wb-cckp.")}
    assert set(ts) - projections == {
        "temp.wb-cckp.era5-annual-absolute",
        "temp.wb-cckp.era5-annual-1991-2020",
        "hot-days-35c.wb-cckp.cmip6",
    }
    assert len(projections) == 12  # tests/test_future_cckp.py (the wettest day is withheld)
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
    obs = hd35_observations(_hd35_files())
    by = {(o.entity, o.dims["scenario"]): o for o in obs}
    # As printed in the files (the source research read the same two medians by hand on 2026-10-04).
    ind_hist, ind_245 = by[("IND", "historical")], by[("IND", "ssp245")]
    assert (ind_hist.period, ind_hist.value, ind_hist.lower, ind_hist.upper) == ("1995/2014", 77.88, 70.04, 84.89)
    assert (ind_245.period, ind_245.value, ind_245.lower, ind_245.upper) == ("2040/2059", 94.78, 78.1, 112.6)
    assert ind_hist.status == "final" and ind_245.status == "projection" and ind_245.interval == "range"
    assert by[("ARE", "historical")].value == 183.07
    assert by[("AFG", "ssp126")].value == 58.73
    # KSV is published as KOS; the seven overseas territories are published as themselves.
    assert ("KOS", "ssp585") in by and ("KSV", "ssp585") not in by
    assert all((e, "ssp245") in by for e in TERRITORIES)
    assert len({e for e, _ in by}) == 246 and len(obs) == 246 * len(SCENARIOS)


def test_hd35_passes_its_validation():
    t = _transforms()["hot-days-35c.wb-cckp.cmip6"]
    res = t.run(_hd35_files())
    validate(t, res.observations)
    assert res.changes is None
    assert res.vintage == "cmip6-x0.25 hd35, fetched 2026-10-05"
    assert "Every CCKP area is published" in res.steps[-1]


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
    mapped = entities_of(codes, "clim")
    assert mapped["KSV"] == "KOS" and mapped["IND"] == "IND" and mapped["FRA"] == "FRA"
    assert all(mapped[c] == c for c in TERRITORIES)
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
    shifted = Era5(e.annual, {"WLD": e.climatology["WLD"] + Decimal("0.02")}, e.start, e.end, "test")
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
        # 240 areas before the seven overseas territories were added to the crosswalk, 76 years each.
        assert len(res.observations) == 247 * 76
        assert res.vintage.startswith("era5-x0.25 1950-2025, fetched ")
        if tid.endswith("absolute"):
            assert (by[("WLD", "2025")], by[("IND", "2025")], by[("KOS", "2025")]) == (14.97, 24.27, 11.75)
            assert res.changes is None
        else:
            assert (by[("WLD", "2025")], by[("IND", "2025")], by[("KOS", "2025")]) == (0.6, 0.06, 1.16)
            assert "largest difference 0.006 °C" in res.steps[2]
            assert res.changes is not None
        assert not {e for e, _ in by} & {"KSV", "GLOBAL"} and set(TERRITORIES) <= {e for e, _ in by}


@pytest.mark.snapshot
def test_full_country_series_matches_the_country_climatology():
    files = {i.key: _current(i.key) for i in cckp.ERA5_INPUTS}
    e = cckp.read_era5(files)
    assert set(TERRITORIES) <= set(e.annual) and (e.start, e.end) == (1950, 2025)
    assert check_climatology(e) == Decimal("0.006")


# --- every country and region (all_countries_subnationals) --------------------------------------------------------

SUBNAT = "cmip6-hd35-2040-2059-ssp245-median-subnat"
SUBNAT_FIXTURES = {
    # region artifact -> the all_countries artifact of the same collection
    "cmip6-hd35-1995-2014-historical-median-subnat": "cmip6-hd35-1995-2014-median",
    SUBNAT: "cmip6-hd35-2040-2059-ssp245-median",
    "cmip6-hd35-2040-2059-ssp245-p10-subnat": "cmip6-hd35-2040-2059-ssp245-p10",
    "cmip6-hd35-2040-2059-ssp245-p90-subnat": "cmip6-hd35-2040-2059-ssp245-p90",
}
# CCKP variable (and product) -> registered region files: 3 for 1995-2014 plus 4 periods x 3 scenarios x 3 statistics.
GRID = {"hd35": 39, "tr26": 39, "hi39": 39, "txx": 39, "rx1day": 39, "cdd": 39, "tas anomaly": 36}


def _subnational_artifacts():
    return [a for a in load_registry(Paths.default()).sources[SOURCE].artifacts if a.id.endswith("-subnat")]


def test_every_registered_cckp_url_parses():
    artifacts = load_registry(Paths.default()).sources[SOURCE].artifacts
    urls = {str(a.url) for a in artifacts}
    for a in artifacts:
        if a.id == "subnational-names":
            # The names workbook is the xlsx of one registered region file (envdash/geo.py reads its names only).
            assert a.format == "xlsx" and str(a.url).endswith("?_format=xlsx")
            assert str(a.url).replace("?_format=xlsx", "?_format=json") in urls
            continue
        collection_of(str(a.url))
    combos: dict[str, set[tuple[int, int, str, str]]] = {}
    for a in _subnational_artifacts():
        c = collection_of(str(a.url))
        assert (c.collection, c.type, c.model, c.geocode) == (
            "cmip6-x0.25",
            "climatology",
            "ensemble_all",
            "all_countries_subnationals",
        )
        key = c.variable if c.product == "climatology" else f"{c.variable} {c.product}"
        combos.setdefault(key, set()).add((c.start, c.end, c.scenario, c.statistic))
        # The id names exactly what the URL holds.
        name = "tas-anomaly" if c.product == "anomaly" else c.variable
        assert a.id == f"cmip6-{name}-{c.start}-{c.end}-{c.scenario}-{c.statistic}-subnat"
    assert {k: len(v) for k, v in combos.items()} == GRID
    futures = {
        (start, start + 19, s, st)
        for start in (2020, 2040, 2060, 2080)
        for s in ("ssp126", "ssp245", "ssp585")
        for st in STATISTICS
    }
    baseline = {(1995, 2014, "historical", st) for st in STATISTICS}
    assert combos["tas anomaly"] == futures
    assert all(combos[v] == futures | baseline for v in GRID if v != "tas anomaly")


def test_only_the_listed_variables_parse_and_count_type_products_never_do():
    assert cckp.VARIABLES == ("tas", "hd35", "tr26", "hi39", "txx", "rx1day", "cdd")
    assert not any(cckp.COUNT_TYPES.search(v) for v in cckp.VARIABLES)
    base = "https://cckpapi.worldbank.org/cckp/v1/"
    tail = "_annual_2040-2059_median_ssp245_ensemble_all_mean/all_countries_subnationals?_format=json"
    assert collection_of(f"{base}cmip6-x0.25_climatology_tas_anomaly{tail}").product == "anomaly"
    with pytest.raises(CckpFormatError, match="not a CCKP collection URL"):
        collection_of(f"{base}cmip6-x0.25_climatology_hd40_climatology{tail}")
    # The count-type products found on the API on 2026-10-15/16, refused by name whatever slot they sit in.
    for url in (
        f"{base}cmip6-x0.25_climatology_ehf2_climatologypopwgthw85exposure{tail}",
        f"{base}cmip6-x0.25_climatology_ehf2_climatologyhw85exposure{tail}",
        f"{base}pop-x0.25_climatology_popcount_climatology_annual_2040-2059_mean_ssp245_gpw-v4_rev11_mean/"
        "all_countries_subnationals?_format=json",
        f"{base}cmip6-x0.25_climatology_popwgt_climatology{tail}",
    ):
        with pytest.raises(CckpFormatError, match="count-type"):
            collection_of(url)


def test_a_file_of_every_country_and_region_reads_as_printed():
    _, data = read_file(
        _input(SUBNAT),
        SUBNAT,
        collection="cmip6-x0.25",
        variable="hd35",
        product="climatology",
        start=2040,
        end=2059,
        statistic="median",
        scenario="ssp245",
        geocode="all_countries_subnationals",
    )
    countries = {k for k in data if "." not in k}
    regions = {k for k in data if "." in k}
    assert (len(countries), len(regions)) == (246, 3527)
    assert sum(k.startswith("DIS.") for k in regions) == 32
    # Every region's prefix is a country of the same file; in hd35, Hong Kong, Macao and Taiwan have none of their own.
    assert countries - ({k.split(".")[0] for k in regions} - {"DIS"}) == {"HKG", "MAC", "TWN"}
    assert sum(k.startswith("IND.") for k in regions) == 35 and sum(k.startswith("KEN.") for k in regions) == 47
    # As printed, and as the research of 2026-10-15/16 read them from the API by hand.
    assert {k: data[k]["2040-07"] for k in ("IND", "KEN", "BRA", "NGA", "IND.11510", "USA.2593218")} == {
        "IND": Decimal("94.78"),
        "KEN": Decimal("75.44"),
        "BRA": Decimal("47.25"),
        "NGA": Decimal("134.32"),
        "IND.11510": Decimal("123.28"),
        "USA.2593218": Decimal("47.12"),
    }
    _, base = read_file(_input("cmip6-hd35-1995-2014-historical-median-subnat"), "base", scenario="historical")
    _, lo = read_file(_input("cmip6-hd35-2040-2059-ssp245-p10-subnat"), "p10", statistic="p10")
    _, hi = read_file(_input("cmip6-hd35-2040-2059-ssp245-p90-subnat"), "p90", statistic="p90")
    assert base["IND.11510"]["1995-07"] == Decimal("102.09")
    assert lo["IND.11510"]["2040-07"] <= data["IND.11510"]["2040-07"] <= hi["IND.11510"]["2040-07"]
    assert set(base) == set(lo) == set(hi) == set(data)


def test_the_national_values_equal_the_all_countries_files():
    """One CCKP collection served for every country, and for every country and region: the national values are the
    same numbers."""
    for subnat, countries in SUBNAT_FIXTURES.items():
        _, both = read_file(_input(subnat), subnat)
        _, only = read_file(_input(countries), countries)
        assert {k: v for k, v in both.items() if "." not in k} == only


def test_keys_must_be_country_or_region_codes(tmp_path):
    path, _ = fixture(SOURCE, SUBNAT)
    raw = path.read_bytes()
    assert raw.count(b'"IND.11510":') == 1 and raw.count(b'"ABW":') == 1
    bad = _input(SUBNAT, raw.replace(b'"IND.11510":', b'"IND-11510":'), tmp_path)
    with pytest.raises(CckpFormatError, match=r"1 keys are not three letters or a region code .*IND-11510"):
        read_file(bad, SUBNAT)
    world = _input(SUBNAT, raw.replace(b'"ABW":', b'"GLOBAL":'), tmp_path)
    with pytest.raises(CckpFormatError, match="all_countries_subnationals file holds GLOBAL"):
        read_file(world, SUBNAT)
    # A region code is refused in a file of countries only.
    countries = "cmip6-hd35-2040-2059-ssp245-median"
    path, _ = fixture(SOURCE, countries)
    raw = path.read_bytes()
    assert raw.count(b'"IND":') == 1
    region = _input(countries, raw.replace(b'"IND":', b'"IND.115":'), tmp_path)
    with pytest.raises(CckpFormatError, match=r"1 keys are not three letters: \['IND.115'\]"):
        read_file(region, countries)


@pytest.mark.snapshot
def test_every_region_file_reads_with_one_code_set_per_variable():
    """All 270 region files: the collection their URL names, one stamp, no null, 246 countries, 32 DIS units and one
    code set per variable. The sets differ between variables only in where Hong Kong, Macao and Taiwan sit (read
    2026-10-16): as CCKP units of China (CHN.33364910 "Hong Kong, SAR", CHN.1491879 "Macau, SAR", CHN.147295925
    "Taiwan Sheng" in CCKP's xlsx of the same collections), as their own single region, or both."""
    countries_only = set(read_file(_current(HD35_INPUTS[("ssp245", "median")].key), "countries")[1])
    sets: dict[str, set[str]] = {}
    for a in _subnational_artifacts():
        k = snapshots.key(SOURCE, a.id)
        c, data = read_file(_current(k), k)
        countries = {code for code in data if "." not in code}
        assert countries == countries_only and sum(code.startswith("DIS.") for code in data) == 32
        assert {code.split(".")[0] for code in data if "." in code} <= countries | {"DIS"}
        if c.statistic == "median":
            lo, hi = (read_file(_current(k.replace("-median-", f"-{p}-")), k)[1] for p in ("p10", "p90"))
            stamp = f"{c.start}-07"
            assert all(lo[code][stamp] <= v[stamp] <= hi[code][stamp] for code, v in data.items())
        name = f"{c.variable} {c.product}" if c.product == "anomaly" else c.variable
        assert sets.setdefault(name, set(data)) == set(data), f"{a.id} covers other areas than its variable"
    common = set.intersection(*sets.values())
    assert len(common) == 246 + 3524
    assert {v: sorted(s - common) for v, s in sets.items()} == {
        "hd35": ["CHN.147295925", "CHN.1491879", "CHN.33364910"],
        "tr26": ["CHN.147295925", "CHN.1491879", "CHN.33364910"],
        "hi39": ["CHN.147295925", "CHN.1491879", "CHN.33364910", "TWN.147296925"],
        "txx": ["CHN.147295925", "CHN.1491879", "CHN.33364910", "TWN.147296925"],
        "rx1day": [
            "CHN.147295925",
            "CHN.1491879",
            "CHN.33364910",
            "HKG.33364910",
            "MAC.1491879",
            "TWN.147296925",
        ],
        "cdd": ["CHN.1491879", "CHN.33364910", "HKG.33364910", "MAC.1491879", "TWN.147296925"],
        "tas anomaly": ["HKG.33364910", "MAC.1491879", "TWN.147296925"],
    }

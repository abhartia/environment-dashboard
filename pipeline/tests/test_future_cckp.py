"""World Bank CCKP projections of seven measures by country and by region
(envdash/transforms/future/cckp_projections.py).

Fixtures are whole files of the wb-cckp snapshots of 2026-10-16 (tests/fixtures/wb-cckp): four files of every country
and region (hd35 1995–2014 median; 2040–2059 SSP2-4.5 median, 10th and 90th percentile, about 110 kB each), and the
twelve hd35 files of every country of 2026-10-05 that the existing hd35 indicator reads. The other 266 region files
are read from the real snapshots in the tests marked snapshot.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from envdash import geo, snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.country import cckp
from envdash.transforms.country.cckp import SOURCE, CckpFormatError, read_file
from envdash.transforms.future import cckp_projections as fp

from support import fixture

HD35 = next(m for m in fp.MEASURES if m.variable == "hd35")
SUBNAT = {
    ("historical", 1995, "median"): "cmip6-hd35-1995-2014-historical-median-subnat",
    ("ssp245", 2040, "median"): "cmip6-hd35-2040-2059-ssp245-median-subnat",
    ("ssp245", 2040, "p10"): "cmip6-hd35-2040-2059-ssp245-p10-subnat",
    ("ssp245", 2040, "p90"): "cmip6-hd35-2040-2059-ssp245-p90-subnat",
}
IDS = {
    f"future.wb-cckp.{k}-{level}"
    for k in (
        "hot-days-35c",
        "hot-nights-26c",
        "heat-index-39c-days",
        "hottest-day",
        "wettest-day",
        "longest-dry-spell",
        "warming",
    )
    for level in ("countries", "regions")
}


def _input(artifact_id: str) -> InputFile:
    path, meta = fixture(SOURCE, artifact_id)
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


def _values(key: tuple[str, int, str]) -> fp.Values:
    artifact = SUBNAT[key]
    _, data = read_file(_input(artifact), artifact, variable="hd35", scenario=key[0], start=key[1], statistic=key[2])
    return {code: next(iter(series.values())) for code, series in data.items()}


@pytest.fixture(scope="module")
def window() -> fp.Files:
    """hd35 2040–2059 under SSP2-4.5 from the three region fixtures: one window of the 13 a build reads."""
    values = {k: _values(k) for k in SUBNAT if k[0] == "ssp245"}
    codes = frozenset(values[("ssp245", 2040, "median")])
    return fp.Files(HD35, (("ssp245", 2040, 2059),), values, codes, "test")


def _transforms() -> dict[str, object]:
    return {t.spec.id: t for t in discover(Paths.default()) if t.spec.id.startswith("future.wb-cckp.")}


# --- declarations -------------------------------------------------------------------------------------------------


def test_fourteen_indicators_read_only_registered_files():
    registered = {a.id for a in load_registry(Paths.default()).sources[SOURCE].artifacts}
    ts = _transforms()
    assert set(ts) == IDS
    for tid, t in ts.items():
        warming = ".warming-" in tid
        assert len(t.inputs) == (36 if warming else 39)
        assert {i.artifact_id for i in t.inputs} <= registered
        assert all(i.artifact_id.endswith("-subnat") for i in t.inputs)
        countries = tid.endswith("-countries")
        s = t.spec
        assert s.geo_coverage == ("country" if countries else "subnational")
        assert (s.headline_entity, s.headline_dims) == ("IND" if countries else "IND.11510", (("scenario", "ssp245"),))
        assert [v.id for v in s.dimensions[0].values] == (
            ["ssp126", "ssp245", "ssp585"] if warming else ["historical", "ssp126", "ssp245", "ssp585"]
        )
        assert "not weighted by where people live" in s.scope.geography
        assert s.display.decimals == (1 if s.unit.code == "degC" else 0)
        assert (s.scope.baseline is not None) == warming
    labels = {v.id: v.label for v in ts["future.wb-cckp.hot-days-35c-countries"].spec.dimensions[0].values}
    assert labels == {
        "historical": "Model simulation of 1995–2014, not observations",
        "ssp126": "SSP1-2.6, low emissions",
        "ssp245": "SSP2-4.5, middle emissions",
        "ssp585": "SSP5-8.5, very high emissions",
    }
    # Exceptions to the national check are declared only where it failed on 2026-10-16.
    assert set(fp.NATIONAL_EXCEPTIONS) == {"cdd", "rx1day", "tas"}
    assert {k: len(v[1]) for k, v in fp.NATIONAL_EXCEPTIONS.items()} == {"cdd": 19, "rx1day": 63, "tas": 23}


# --- one window from the fixtures ---------------------------------------------------------------------------------


def test_one_window_publishes_median_and_range_as_printed(window):
    fp.check_codes(window.codes, "hd35")
    fp.check_ranges(window.values, "hd35")
    fp.check_national(window)
    countries = fp.countries_of(window)
    regions = fp.regions_of(window, countries)
    assert (len(countries), len(regions)) == (246, 3492)
    assert countries["KSV"] == "KOS" and "KSV.750081" in regions
    assert not [c for c in regions if c.startswith("DIS.") or c in geo.CHINA_LISTED]
    assert {p: sum(c.startswith(f"{p}.") for c in regions) for p in ("IND", "KEN", "BRA")} == {
        "IND": 35,
        "KEN": 47,
        "BRA": 31,
    }
    obs = fp.observations(window, countries) + fp.observations(window, {c: c for c in regions})
    by = {o.entity: o for o in obs}
    # As printed, and as the research of 2026-10-15/16 read them from the API by hand.
    assert (by["IND"].value, by["IND"].lower, by["IND"].upper) == (94.78, 78.1, 112.6)
    assert (by["KEN"].value, by["BRA"].value, by["NGA"].value) == (75.44, 47.25, 134.32)
    assert (by["IND.11510"].value, by["USA.2593218"].value) == (123.28, 47.12)
    assert (by["KEN.13344"].value, by["KEN.13320"].value) == (162.43, 0.0)  # Turkana, Nairobi
    o = by["IND.11510"]
    assert (o.period, o.status, o.interval, o.dims) == ("2040/2059", "projection", "range", {"scenario": "ssp245"})
    baseline = _values(("historical", 1995, "median"))
    assert baseline["IND.11510"] == Decimal("102.09")


def test_country_rows_equal_the_existing_hd35_indicator(window):
    """The existing hot-days-35c.wb-cckp.cmip6 (CCKP's all_countries files) and the new country indicator (its
    all_countries_subnationals files) publish the same numbers for the cells both have."""
    old = cckp.hd35_observations({i.key: _input(i.artifact_id) for i in cckp.HD35_INPUTS.values()})
    new = fp.observations(window, fp.countries_of(window))
    old_by = {(o.entity, o.period, o.dims["scenario"]): o for o in old}
    assert len(new) == 246
    for o in new:
        prev = old_by[(o.entity, o.period, o.dims["scenario"])]
        assert (o.value, o.lower, o.upper, o.status, o.interval) == (
            prev.value,
            prev.lower,
            prev.upper,
            prev.status,
            prev.interval,
        )
    baseline = _values(("historical", 1995, "median"))
    assert {o.entity: o.value for o in old if o.dims["scenario"] == "historical"} == {
        e: float(baseline[c]) for c, e in fp.countries_of(window).items()
    }


def test_a_national_value_outside_its_regions_stops_the_build(window):
    median = dict(window.values[("ssp245", 2040, "median")])
    india = [v for c, v in median.items() if c.startswith("IND.")]
    assert min(india) <= median["IND"] <= max(india)
    pushed = replace(window, values={**window.values, ("ssp245", 2040, "median"): {**median, "IND": max(india) + 1}})
    assert set(fp.national_offenders(pushed.values)) == {"IND"}
    with pytest.raises(CckpFormatError, match=r"national value of 1 countries .*IND \(ssp245 2040 median"):
        fp.check_national(pushed)
    # Within the tolerance of rounding (half the last printed digit, twice) it passes.
    edge = {**median, "IND": max(india) + Decimal("0.01")}
    fp.check_national(replace(window, values={**window.values, ("ssp245", 2040, "median"): edge}))
    # A country with one region must equal it: Guadeloupe and its one region, GLP.100100.
    assert [c for c in median if c.startswith("GLP.")] == ["GLP.100100"] and median["GLP"] == median["GLP.100100"]
    glp = {**median, "GLP.100100": median["GLP"] + Decimal("0.02")}
    with pytest.raises(CckpFormatError, match=r"\['GLP \(ssp245 2040 median"):
        fp.check_national(replace(window, values={**window.values, ("ssp245", 2040, "median"): glp}))


def test_a_declared_exception_that_no_longer_fails_stops_the_build(window, monkeypatch):
    monkeypatch.setitem(fp.NATIONAL_EXCEPTIONS, "hd35", ("test", frozenset({"IND"})))
    with pytest.raises(CckpFormatError, match=r"declares \['IND'\].*remove them"):
        fp.check_national(window)


def test_codes_and_ranges_that_do_not_fit_stop_the_build(window):
    codes = window.codes
    with pytest.raises(CckpFormatError, match="31 DIS"):
        fp.check_codes(codes - {"DIS.990011"}, "hd35")
    with pytest.raises(CckpFormatError, match=r"not a country of the same file: \['IND\."):
        fp.check_codes(codes - {"IND"}, "hd35")
    lo = dict(window.values[("ssp245", 2040, "p10")])
    lo["IND.11510"] = Decimal("200")
    with pytest.raises(CckpFormatError, match=r"median outside the 10th-90th percentile.*IND\.11510"):
        fp.check_ranges({**window.values, ("ssp245", 2040, "p10"): lo}, "hd35")


def test_a_region_that_is_not_an_entity_stops_the_build(window):
    countries = fp.countries_of(window)
    moved = replace(window, codes=window.codes - {"IND.11510"} | {"IND.99999"})
    with pytest.raises(CckpFormatError, match=r"IND\.99999 is not in pipeline/geo/entities\.csv"):
        fp.regions_of(moved, countries)
    # A region code whose entity belongs to another country.
    with pytest.raises(CckpFormatError, match="not a region of PAK"):
        fp.regions_of(window, {**countries, "IND": "PAK"})


# --- every file (snapshots) ---------------------------------------------------------------------------------------


def _current(key: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[key]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(p, sha), snap)


@pytest.fixture(scope="module")
def built():
    out = {}
    for tid, t in _transforms().items():
        res = t.run({i.key: _current(i.key) for i in t.inputs})
        validate(t, res.observations)
        out[tid] = res
    return out


@pytest.mark.snapshot
def test_every_indicator_builds_with_its_counts(built):
    regions = {m.key: fp.MIN_REGIONS[m.variable] for m in fp.MEASURES}
    for m in fp.MEASURES:
        combos = 12 if m.key == "warming" else 13
        c = built[f"future.wb-cckp.{m.key}-countries"].observations
        r = built[f"future.wb-cckp.{m.key}-regions"].observations
        assert len(c) == 246 * combos and len({o.entity for o in c}) == 246
        assert len(r) == regions[m.key] * combos and len({o.entity for o in r}) == regions[m.key]
        assert {o.status for o in c if o.dims["scenario"] == "historical"} <= {"final"}
        assert {o.status for o in c if o.dims["scenario"] != "historical"} == {"projection"}
        assert {o.period for o in r} == ({"1995/2014"} if combos == 13 else set()) | {
            "2020/2039",
            "2040/2059",
            "2060/2079",
            "2080/2099",
        }
        ents = {o.entity for o in r}
        assert not {e for e in ents if e.startswith("DIS.")} and not ents & set(geo.CHINA_LISTED)
    assert regions == {
        "hot-days-35c": 3492,
        "hot-nights-26c": 3492,
        "heat-index-39c-days": 3493,
        "hottest-day": 3493,
        "wettest-day": 3495,
        "longest-dry-spell": 3495,
        "warming": 3495,
    }


@pytest.mark.snapshot
def test_known_values_from_every_file(built):
    def at(tid: str, entity: str, period: str, scenario: str) -> tuple[float, float, float]:
        (o,) = [
            o for o in built[tid].observations if (o.entity, o.period, o.dims["scenario"]) == (entity, period, scenario)
        ]
        return o.value, o.lower, o.upper  # type: ignore[return-value]

    hd = "future.wb-cckp.hot-days-35c-"
    assert at(hd + "countries", "IND", "2040/2059", "ssp245") == (94.78, 78.1, 112.6)
    assert at(hd + "countries", "IND", "1995/2014", "historical") == (77.88, 70.04, 84.89)
    assert at(hd + "countries", "KEN", "2040/2059", "ssp245")[0] == 75.44
    assert at(hd + "countries", "BRA", "2040/2059", "ssp245")[0] == 47.25
    assert at(hd + "regions", "IND.11510", "2040/2059", "ssp245")[0] == 123.28
    assert at(hd + "regions", "IND.11510", "1995/2014", "historical") == (102.09, 90.22, 114.87)
    # rx1day lists Taiwan twice; only its own region is published (geo.CHINA_LISTED).
    assert at("future.wb-cckp.wettest-day-regions", "TWN.147296925", "2040/2059", "ssp245")[0] == 123.49
    for m in fp.MEASURES:
        for level in ("countries", "regions"):
            res = built[f"future.wb-cckp.{m.key}-{level}"]
            assert res.vintage.startswith(f"cmip6-x0.25 {m.variable} {m.product}, fetched 2026-10-16")
            assert ("Declared exceptions" in res.steps[1]) == (m.variable in fp.NATIONAL_EXCEPTIONS)


@pytest.mark.snapshot
def test_country_rows_equal_the_existing_hd35_indicator_in_every_cell(built):
    t = {t.spec.id: t for t in discover(Paths.default())}["hot-days-35c.wb-cckp.cmip6"]
    old = t.run({i.key: _current(i.key) for i in t.inputs}).observations
    new = {
        (o.entity, o.period, o.dims["scenario"]): o for o in built["future.wb-cckp.hot-days-35c-countries"].observations
    }
    shared = [o for o in old if (o.entity, o.period, o.dims["scenario"]) in new]
    # Every cell of the old indicator: 1995–2014 and 2040–2059 under its three scenarios.
    assert len(shared) == len(old) == 246 * 4
    for o in shared:
        n = new[(o.entity, o.period, o.dims["scenario"])]
        assert (n.value, n.lower, n.upper, n.status, n.interval) == (o.value, o.lower, o.upper, o.status, o.interval)

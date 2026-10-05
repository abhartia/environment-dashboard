"""WGMS AMCE glacier transforms (envdash/transforms/ice/wgms_amce.py).

Fixtures: global.csv and README.md, each whole, from the wgms-amce-2026-02-10.zip snapshot, cut by
tests/fixtures/wgms-amce/make_zip_fixture.py. They sit one directory lower than make_fixture.py's, so the two sidecar
checks of test_fixtures_provenance.py are repeated here with the zip-aware cutter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.ice import wgms_amce as wgms

FIXTURES = Path(__file__).parent / "fixtures" / "wgms-amce"
SIDECARS = sorted(FIXTURES.glob("*/*.provenance.json"))
VERSION = "2026-02-10"


def _fixture(member: str) -> bytes:
    side = next(s for s in SIDECARS if json.loads(s.read_text())["member"] == member)
    return side.with_name(side.name.removesuffix(".provenance.json")).read_bytes()


def _years():
    return wgms.read_global(_fixture("global.csv"))


def _transform(indicator_id: str):
    return next(t for t in wgms.transforms(Paths.default()) if t.spec.id == indicator_id)


# --- fixtures ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == wgms.SOURCE
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open" and src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(FIXTURES))
    from make_zip_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    artifact, member = parse_command(meta["command"])
    assert artifact == meta["artifact_id"]
    sliced, _ = cut(raw, member)
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]


# --- parsing -------------------------------------------------------------------------------------------------------


def test_annual_and_cumulative_as_printed():
    years = _years()
    assert [y.year for y in years] == list(range(1976, 2026))
    annual = {o.period: o for o in wgms.observations(years, "gt", "gt_sigma")}
    cumulative = {o.period: o for o in wgms.observations(years, "gt_cumsum", "gt_cumsum_sigma")}
    sea = {o.period: o for o in wgms.observations(years, "mmsle_cumsum", "mmsle_cumsum_sigma")}
    assert annual["1976"].value == 12.432
    assert (annual["2025"].value, annual["2025"].lower, annual["2025"].upper) == (-408.101, -475.324, -340.878)
    assert cumulative["2025"].value == -9583.132 and sea["2025"].value == 26.436
    assert all(o.interval == "1sigma" and o.entity == "WLD" for o in annual.values())


def test_values_agree_with_wgms_summary_of_this_version():
    # "Glaciers lost 408 ± 132 Gt of mass during the hydrological year 2025" and "Since 1975, glacier mass loss has
    # totalled 9,583 ± 1,211 Gt" (Nature Reviews Earth & Environment, 7 April 2026). Their ± are 1.96 sigma.
    y = {r.year: r for r in _years()}[2025]
    assert round(y.d("gt")) == -408 and round(y.d("gt_cumsum")) == -9583
    assert round(float(y.d("gt_sigma")) * 1.96) == 132 and round(float(y.d("gt_cumsum_sigma")) * 1.96) == 1211


def test_cumulative_must_be_the_running_sum():
    raw = _fixture("global.csv").replace(
        b"2025,651590.19,-0.629,0.305,-14.101,-408.101", b"2025,651590.19,-0.629,0.305,-14.101,-418.101", 1
    )
    with pytest.raises(wgms.WgmsFormatError, match="running sum"):
        wgms.read_global(raw)


def test_readme_must_define_the_columns_and_carry_the_doi():
    readme = _fixture("README.md")
    wgms.check_readme(readme, VERSION)
    with pytest.raises(wgms.WgmsFormatError, match="wgms-amce-2025-02"):
        wgms.check_readme(readme, "2025-02")
    with pytest.raises(wgms.WgmsFormatError, match=r"global\.csv section"):
        wgms.check_readme(readme.replace(b"1-sigma uncertainty of `gt`", b"uncertainty of `gt`", 1), VERSION)


def test_sea_level_publisher_check():
    t = _transform("sea-level-contribution.wgms-amce.glaciers-cumulative")
    obs = wgms.observations(_years(), "mmsle_cumsum", "mmsle_cumsum_sigma")
    validate(t, obs)
    [outcome] = run_checks(t, {wgms.SOURCE: VERSION}, obs)
    assert outcome.status == "pass"


def test_version_from_url():
    assert wgms.version_of("https://wgms.ch/downloads/wgms-amce-2026-02-10.zip") == VERSION
    with pytest.raises(wgms.WgmsFormatError):
        wgms.version_of("https://wgms.ch/downloads/wgms-amce-latest.zip")


@pytest.mark.snapshot
def test_full_release_builds_all_three():
    paths = Paths.default()
    sha = snapshots.read_current(paths)[wgms.ZIP.key]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    for t in wgms.transforms(paths):
        result = t.run({wgms.ZIP.key: InputFile(Path(snapshots.cache_path(paths, sha)), snap)})
        validate(t, result.observations)
        assert result.vintage == VERSION
        assert all(c.status == "pass" for c in run_checks(t, {wgms.SOURCE: VERSION}, result.observations))

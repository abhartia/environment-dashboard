"""SEI Emissions Inequality Dashboard: share of world consumption CO2 by income group
(envdash/transforms/emissions/sei_inequality.py).

The fixture is a byte-exact cut of the real Historical Global Shares API response (CC BY 4.0): the 127 records of each
of 1990, 2022 and 2023, cut by tests/fixtures/sei-emissions-inequality/make_json_fixture.py. It sits one directory lower
than make_fixture.py's, so the two sidecar checks of test_fixtures_provenance.py are repeated here with the JSON cutter.
The response is one line of JSON, so a line slice could not hold a readable part of it.
"""

from __future__ import annotations

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import canonical, snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.emissions import sei_inequality as sei
from envdash.validate import validate_all

from support import exported

FIXTURES = Path(__file__).parent / "fixtures" / "sei-emissions-inequality"
SIDECARS = sorted(FIXTURES.glob("*/*.provenance.json"))
ID = "co2-share.sei-inequality.income-groups-global"


def _raw() -> bytes:
    (side,) = [s for s in SIDECARS if json.loads(s.read_text())["artifact_id"] == "global-percentile-shares"]
    return side.with_name(side.name.removesuffix(".provenance.json")).read_bytes()


def _edited(edit) -> bytes:
    """The fixture's records, changed by `edit` (a function of the parsed document), to show what is refused."""
    doc = json.loads(_raw())
    edit(doc)
    return json.dumps(doc).encode()


def _shares(obs) -> dict[tuple[str, str], float]:
    return {(o.dims["group"], o.period): o.value for o in obs}


# --- fixtures ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == sei.SOURCE
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open" and src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(FIXTURES))
    from make_json_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    artifact, years = parse_command(meta["command"])
    assert artifact == meta["artifact_id"]
    sliced, _ = cut(raw, years)
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]


# --- parsing and groups --------------------------------------------------------------------------------------------


def test_slices_partition_each_year():
    by_year = sei.read_slices(_raw())
    assert sorted(by_year) == [1990, 2022, 2023]
    for slices in by_year.values():
        assert len(slices) == 127
        assert slices[0].lower == 0 and slices[-1].upper == 100
        assert [s.lower for s in slices[99:]][:2] == [Decimal("99"), Decimal("99.1")]
        assert slices[-1].lower == Decimal("99.999")


def test_group_shares_add_the_slices_exactly():
    by_year = sei.read_slices(_raw())
    shares = _shares(sei.group_shares(by_year))
    # Sums of the EmissionShare strings in the fixture, times 100.
    assert shares[("top-10", "2023")] == 47.07544857094307
    assert shares[("top-1", "2023")] == 16.549954271160725
    assert shares[("bottom-50", "2023")] == 8.419959966084065
    assert shares[("top-10", "1990")] == 51.54104139587493
    assert shares[("top-1", "1990")] == 14.491619690149705
    assert shares[("bottom-50", "1990")] == 8.693080083916344
    assert shares[("top-10", "2022")] == 48.992907074468484
    assert shares[("top-1", "2022")] == 16.83069592664831
    assert shares[("bottom-50", "2022")] == 7.959763477732884
    # The records of p99p99.1 ... p99.999p100 are exactly the top 1%; the top 1% is inside the top 10%.
    for year in ("1990", "2022", "2023"):
        assert shares[("top-1", year)] < shares[("top-10", year)]
    top1 = [s for s in by_year[2023] if s.lower >= 99]
    assert len(top1) == 28 and sum(s.upper - s.lower for s in top1) == 1


def test_a_gap_in_the_years_is_refused():
    # The fixture holds 1990, 2022 and 2023 only; the API serves every year, so the transform refuses this response.
    with pytest.raises(sei.SeiFormatError, match="have gaps"):
        sei.check_years(sei.read_slices(_raw()))


def test_a_missing_slice_is_refused():
    def drop(doc):
        doc["records"] = [r for r in doc["records"] if not (r["Year"] == "2023" and r["PercentileLabel"] == "p95p96")]

    with pytest.raises(sei.SeiFormatError, match="does not start where the last ended"):
        sei.read_slices(_edited(drop))


def test_a_width_that_does_not_match_its_label_is_refused():
    def widen(doc):
        doc["records"][0]["PercentileValue"] = "0.02"

    with pytest.raises(sei.SeiFormatError, match="PercentileValue"):
        sei.read_slices(_edited(widen))


def test_a_changed_elasticity_is_refused():
    def change(doc):
        for r in doc["records"]:
            r["Elasticity"] = "0.82"

    with pytest.raises(sei.SeiFormatError, match="Elasticity"):
        sei.read_slices(_edited(change))


def test_shares_that_do_not_add_to_one_are_refused():
    def inflate(doc):
        doc["records"][0]["EmissionShare"] = "0.5"

    with pytest.raises(sei.SeiFormatError, match="add up to"):
        sei.read_slices(_edited(inflate))


def test_2023_is_left_out_as_a_different_basis():
    # SEI's 2023 national inputs are territorial, 1990-2022 consumption-based: the series ends at 2022.
    by_year = sei.read_slices(_raw())
    kept = sei.consumption_years(by_year)
    assert sorted(kept) == [1990, 2022] and sei.LAST_CONSUMPTION_YEAR == 2022
    shares = _shares(sei.group_shares(kept))
    assert {p for _, p in shares} == {"1990", "2022"}
    # The break the cut avoids: the top-10% share falls from 48.99% to 47.08% between the two bases.
    full = _shares(sei.group_shares(by_year))
    assert round(full[("top-10", "2022")], 2) == 48.99 and round(full[("top-10", "2023")], 2) == 47.08


def test_a_response_without_the_last_consumption_year_is_refused():
    by_year = sei.read_slices(_raw())
    with pytest.raises(sei.SeiFormatError, match="last consumption-based year"):
        sei.consumption_years({y: v for y, v in by_year.items() if y != 2022})


def test_description_says_what_is_counted():
    (t,) = sei.transforms(Paths.default())
    assert "1990 to 2022" in t.spec.description and "not tonnes per person" in t.spec.description
    assert "territorial" in t.spec.description


def test_transform_declares_its_registered_input():
    (t,) = sei.transforms(Paths.default())
    assert t.spec.id == ID and t.spec.kind == "derived"
    src = load_registry(Paths.default()).sources[sei.SOURCE]
    assert t.inputs == (sei.SHARES,) and sei.SHARES.artifact_id in {a.id for a in src.artifacts}
    assert t.spec.scope.lulucf == "excluded"
    assert [v.id for v in t.spec.dimensions[0].values] == ["top-10", "top-1", "bottom-50"]


# --- the full real response (snapshot cache) ----------------------------------------------------------------------


def _current_file() -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[snapshots.key(sei.SOURCE, sei.SHARES.artifact_id)]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(p, sha), snap)


@pytest.mark.snapshot
def test_every_year_from_the_real_response():
    (t,) = sei.transforms(Paths.default())
    result = t.run({sei.SHARES.key: _current_file()})
    validate(t, result.observations)
    shares = _shares(result.observations)
    assert len(shares) == 3 * 33
    assert {p for _, p in shares} == {str(y) for y in range(1990, 2023)}
    # The same 2022 values as the fixture, which holds that year's records unchanged; 2023 is left out.
    assert shares[("top-10", "2022")] == 48.992907074468484
    assert ("top-10", "2023") not in shares
    assert (
        result.vintage == "1990-2022 consumption-based years of the 1990-2023 historical series, retrieved 2026-10-04"
    )
    assert any("left out 2023" in s for s in result.steps)
    assert result.changes is not None


@pytest.mark.snapshot
def test_build_exports_publicly(tmp_paths):
    real = Paths.default()
    paths = tmp_paths.with_(cache=real.cache)
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{sei.SOURCE}.yaml", paths.sources)
    paths.snapshot_manifests.mkdir(parents=True)
    k = sei.SHARES.key
    sha = snapshots.read_current(real)[k]
    shutil.copy(snapshots.manifest_path(real, sha), snapshots.manifest_path(paths, sha))
    snapshots.set_current(paths, {k: sha})
    reg = load_registry(paths)
    report = build_and_export(paths, reg, [t for t in discover(paths) if t.spec.id == ID])
    assert [o.state for o in report.outcomes] == ["built"], [o.reason for o in report.outcomes]
    ind = exported(paths.public_indicators / f"{ID}.json")
    assert ind["licence_class"] == "open"
    assert ind["latest"]["dims"] == {"group": "top-10"} and ind["latest"]["period"] == "2022"
    assert "Calculated by Environment Dashboard from Stockholm Environment Institute data" in ind["attribution"]
    assert "Changes: emission shares of income slices added up" in ind["attribution"]
    assert (paths.public_indicators / f"{ID}.csv").exists()
    assert validate_all(paths, reg) == []

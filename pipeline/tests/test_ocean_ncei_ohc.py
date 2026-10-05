"""NOAA NCEI ocean heat content transforms (envdash/transforms/ocean/ncei_ohc.py), on real fixtures.

Fixtures (tests/fixtures/ncei-ocean-heat/, each with its .provenance.json sidecar): the whole files
yearly/h22-w0-2000m.dat, yearly/h22-w0-700m.dat and pentad/pent_h22-w0-2000m.dat as fetched on 2026-10-05
(Last-Modified 6 July 2026). Each is given to the transform with the committed snapshot manifest of the same bytes,
which holds the Last-Modified header the vintage is read from.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.ocean import ncei_ohc
from envdash.transforms.ocean.ncei_ohc import NceiOhcFormatError, read_rows, vintage_of

from support import fixture

SOURCE = "ncei-ocean-heat"
IDS = {
    "ohc.ncei.yearly-0-2000m": "world-0-2000m-yearly",
    "ohc.ncei.yearly-0-700m": "world-0-700m-yearly",
    "ohc.ncei.pentadal-0-2000m": "world-0-2000m-pentadal",
}


def _input(artifact_id: str) -> InputFile:
    path, meta = fixture(SOURCE, artifact_id)
    snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
    assert snap is not None and snap.artifact_id == artifact_id
    return InputFile(path=path, snapshot=snap)


def _run(indicator_id: str):
    t = next(t for t in ncei_ohc.transforms(Paths.default()) if t.spec.id == indicator_id)
    result = t.run({f"{SOURCE}/{IDS[indicator_id]}": _input(IDS[indicator_id])})
    validate(t, result.observations)
    return result


def test_transforms_declare_registered_inputs():
    paths = Paths.default()
    ts = {t.spec.id: t for t in ncei_ohc.transforms(paths)}
    assert set(ts) == set(IDS)
    artifacts = {a.id for a in load_registry(paths).sources[SOURCE].artifacts}
    for tid, t in ts.items():
        assert [i.key for i in t.inputs] == [f"{SOURCE}/{IDS[tid]}"]
        assert IDS[tid] in artifacts
        assert t.spec.unit.code == "1e22J" and t.spec.scope.baseline and "World Ocean Atlas" in t.spec.scope.baseline


def test_yearly_0_2000m_values_and_standard_errors():
    r = _run("ohc.ncei.yearly-0-2000m")
    by = {o.period: o for o in r.observations}
    assert r.vintage == "2026-07-06" and r.date_published == "2026-07-06"
    assert [o.period for o in r.observations] == [str(y) for y in range(2005, 2026)]
    # File rows "2005.500  10.171   0.835" and "2025.500  32.533   0.267".
    assert by["2005"].value == 10.171 and (by["2005"].lower, by["2005"].upper) == (9.336, 11.006)
    assert by["2025"].value == 32.533 and (by["2025"].lower, by["2025"].upper) == (32.266, 32.8)
    assert {(o.entity, o.interval, o.status) for o in r.observations} == {("WLD", "1sigma", "final")}
    # The research verifier's reading: 2025 is the highest level in the file, 2.217 x 10^22 J above 2024, while
    # 2017 (+2.790) had a larger one-year gain.
    assert max(r.observations, key=lambda o: o.value).period == "2025"
    assert round(by["2025"].value - by["2024"].value, 3) == 2.217
    assert round(by["2017"].value - by["2016"].value, 3) == 2.790


def test_yearly_0_700m_runs_from_1955():
    r = _run("ohc.ncei.yearly-0-700m")
    obs = r.observations
    assert len(obs) == 71 and obs[0].period == "1955" and obs[-1].period == "2025"
    assert obs[0].value == -3.201 and obs[-1].value == 22.845
    assert (obs[-1].lower, obs[-1].upper) == (22.67, 23.02)


def test_pentadal_periods_are_five_year_ranges():
    r = _run("ohc.ncei.pentadal-0-2000m")
    obs = r.observations
    assert len(obs) == 67
    # "  1957.5  -9.303   2.025" is 1955-1959; "  2023.5  29.480   0.187" is 2021-2025 (registry note: 29.480).
    assert (obs[0].period, obs[0].value) == ("1955/1959", -9.303)
    assert (obs[-1].period, obs[-1].value, obs[-1].lower, obs[-1].upper) == ("2021/2025", 29.48, 29.293, 29.667)
    assert obs[1].period == "1956/1960"


def test_refuses_a_changed_layout():
    path, _ = fixture(SOURCE, "world-0-2000m-yearly")
    raw = path.read_text(encoding="ascii")
    with pytest.raises(NceiOhcFormatError, match="first line"):
        read_rows(raw.replace("WOse", "WOsd", 1), pentadal=False, name="h22-w0-2000m.dat")
    with pytest.raises(NceiOhcFormatError, match=r"not <year>\.500"):
        read_rows(raw.replace("2025.500", "2025.250"), pentadal=False, name="h22-w0-2000m.dat")
    with pytest.raises(NceiOhcFormatError, match="characters"):
        read_rows(raw.replace("  32.533", " 32.533"), pentadal=False, name="h22-w0-2000m.dat")
    with pytest.raises(NceiOhcFormatError, match="middle of five years"):
        read_rows(raw, pentadal=True, name="h22-w0-2000m.dat")


def test_vintage_needs_last_modified():
    assert vintage_of("Mon, 06 Jul 2026 23:21:40 GMT") == "2026-07-06"
    f = _input("world-0-2000m-yearly")
    t = next(t for t in ncei_ohc.transforms(Paths.default()) if t.spec.id == "ohc.ncei.yearly-0-2000m")
    bare = InputFile(path=f.path, snapshot=f.snapshot.model_copy(update={"last_modified": None}))
    with pytest.raises(NceiOhcFormatError, match="Last-Modified"):
        t.run({f"{SOURCE}/world-0-2000m-yearly": bare})

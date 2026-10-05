"""NOAA GML methane and nitrous oxide, Law Dome CO2 spline and the Bereiter CO2 composite reader, on real fixtures.

Fixtures (tests/fixtures/<source>/, each with its .provenance.json sidecar):
- noaa-gml-trends-ch4-n2o-sf6: ch4_annmean_gl.csv and n2o_annmean_gl.csv, whole files (version 2026-09).
- law-dome-2k: Law_Dome_GHG_2000years.xlsx, the whole file (a zip cannot be cut by lines; fixture sha256 = full sha256).
- bereiter-2015-co2: the whole file (51,875 bytes, sha256 40c9c175ab75...), so the composite's maximum is tested on
  every real sample.
"""

from __future__ import annotations

import itertools
import json
from datetime import date
from pathlib import Path

import pytest

from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, discover, validate
from envdash.transforms.air.bereiter_co2 import (
    BereiterFormatError,
    Sample,
    contribution_date,
    preindustrial_max,
    read_composite,
)
from envdash.transforms.air.law_dome_co2 import COLLECTIONS, LawDomeFormatError, collection_of, read_spline
from envdash.transforms.air.noaa_ch4_n2o import CH4, N2O, NoaaGhgFormatError, parse_annual_global

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(source_id: str, artifact_id: str) -> tuple[Path, dict]:
    """The fixture file cut from (source, artifact) and its provenance sidecar (copied from tests/support.py)."""
    for side in sorted(FIXTURES.glob(f"{source_id}/*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == artifact_id:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(f"no fixture for {source_id}/{artifact_id}")


def input_file(source_id: str, artifact_id: str) -> InputFile:
    """A fixture as the InputFile a transform receives, with its real URL and access date."""
    path, meta = fixture(source_id, artifact_id)
    snap = Snapshot(
        sha256=meta["fixture_sha256"],
        bytes=meta["fixture_bytes"],
        source_id=source_id,
        artifact_id=artifact_id,
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    return InputFile(path=path, snapshot=snap)


def run_transform(indicator_id: str, *inputs: tuple[str, str]):
    t = next(t for t in discover(Paths.default()) if t.spec.id == indicator_id)  # type: ignore[arg-type]
    files = {f"{s}/{a}": input_file(s, a) for s, a in inputs}
    result = t.run(files)
    validate(t, result.observations)
    return result


# --- NOAA GML methane and nitrous oxide --------------------------------------------------------------------------


def test_ch4_annual_global_one_sigma_bounds_and_preliminary_last_year():
    path, _ = fixture("noaa-gml-trends-ch4-n2o-sf6", "ch4-annmean-gl")
    obs, created = parse_annual_global(path.read_text(), CH4)
    assert f"{created:%Y-%m}" == "2026-09"
    assert len(obs) == 42
    assert (obs[0].period, obs[0].value, obs[0].lower, obs[0].upper) == ("1984", 1644.84, 1644.24, 1645.44)
    last = obs[-1]
    # File row "2025,1935.94,0.48"
    assert (last.period, last.value, last.lower, last.upper) == ("2025", 1935.94, 1935.46, 1936.42)
    assert last.interval == "1sigma" and last.status == "preliminary"
    assert {o.status for o in obs[:-1]} == {"final"}
    assert {o.entity for o in obs} == {"WLD"}


def test_n2o_annual_global_values():
    path, _ = fixture("noaa-gml-trends-ch4-n2o-sf6", "n2o-annmean-gl")
    obs, created = parse_annual_global(path.read_text(), N2O)
    assert f"{created:%Y-%m}" == "2026-09"
    assert len(obs) == 25
    assert (obs[0].period, obs[0].value) == ("2001", 316.36)
    last = obs[-1]
    # File row "2025,338.85,0.02"
    assert (last.period, last.value, last.lower, last.upper) == ("2025", 338.85, 338.83, 338.87)
    assert last.status == "preliminary"


def test_ch4_transform_vintage_and_validation():
    r = run_transform("ch4.noaa-gml.annual-global", ("noaa-gml-trends-ch4-n2o-sf6", "ch4-annmean-gl"))
    assert r.vintage == "2026-09" and r.date_published == "2026-09-05"
    assert r.changes is None


def test_n2o_refuses_a_file_of_the_other_gas():
    path, _ = fixture("noaa-gml-trends-ch4-n2o-sf6", "ch4-annmean-gl")
    with pytest.raises(NoaaGhgFormatError, match="N2O expressed"):
        parse_annual_global(path.read_text(), N2O)


def test_ch4_refuses_file_without_its_stated_uncertainty_rule():
    path, _ = fixture("noaa-gml-trends-ch4-n2o-sf6", "ch4-annmean-gl")
    raw = path.read_text().replace("taken in\n# quadrature", "combined\n# somehow")
    with pytest.raises(NoaaGhgFormatError, match="re-read"):
        parse_annual_global(raw, CH4)


# --- Law Dome CO2 spline ------------------------------------------------------------------------------------------


def test_law_dome_spline_years_and_values():
    path, _ = fixture("law-dome-2k", "law-dome-ghg-2000years")
    obs = read_spline(path.read_bytes(), "11/2018")
    assert len(obs) == 1996 - 154 + 1
    assert [o.period for o in obs[:2]] == ["0154", "0155"] and obs[-1].period == "1996"
    by = {o.period: o.value for o in obs}
    # Sheet "Splines fits": row 5 "154, 278.18106", row 1847 "1996, 359.38354" (cells as printed by Excel).
    assert by["0154"] == 278.18106
    assert by["1996"] == 359.38354
    assert all(o.entity == "LAWDOME" and o.lower is None for o in obs)


def test_law_dome_transform_version_from_collection():
    r = run_transform("co2.law-dome.2k", ("law-dome-2k", "law-dome-ghg-2000years"))
    assert r.vintage == "v3" and r.date_published == "2024-09-04"
    assert "0154 to 1996" in r.steps[1]


def test_law_dome_unknown_collection_or_last_update_stops():
    with pytest.raises(LawDomeFormatError, match="not in COLLECTIONS"):
        collection_of("https://data.csiro.au/dap/ws/v2/collections/99999/data/1")
    assert collection_of("https://data.csiro.au/dap/ws/v2/collections/63432/data/53592973") == COLLECTIONS["63432"]
    path, _ = fixture("law-dome-2k", "law-dome-ghg-2000years")
    with pytest.raises(LawDomeFormatError, match="LAST UPDATE"):
        read_spline(path.read_bytes(), "01/2026")


# --- Bereiter et al. 2015 composite (years before 1950) ----------------------------------------------------------

SERIES = "co2.bereiter-2015.800k"
MAXIMUM = "co2.bereiter-2015.800k.max-before-1000bp"


def test_bereiter_reader_keeps_ages_as_printed():
    path, meta = fixture("bereiter-2015-co2", "composite")
    assert meta["fixture_sha256"] == meta["full_sha256"]
    samples = read_composite(path.read_text())
    assert len(samples) == 1901
    first, last = samples[0], samples[-1]
    # File rows "-51.03\t368.02\t0.06" (first) and "805668.87\t207.29\t2.20" (last).
    assert (str(first.age_bp), str(first.co2_ppm), str(first.sigma_ppm)) == ("-51.03", "368.02", "0.06")
    assert (str(last.age_bp), str(last.co2_ppm), str(last.sigma_ppm)) == ("805668.87", "207.29", "2.20")
    assert contribution_date(path.read_text()) == "2015-02-04"


def test_bereiter_series_is_dated_by_age_oldest_first():
    r = run_transform(SERIES, ("bereiter-2015-co2", "composite"))
    obs = r.observations
    assert len(obs) == 1901 and r.vintage == "2015-02-04" and r.date_published == "2015-02-04"
    assert all(o.period is None and o.age_bp is not None and o.entity == "ANT_ICECORES" for o in obs)
    assert (obs[0].age_bp, obs[0].value, obs[0].lower, obs[0].upper) == (805668.87, 207.29, 205.09, 209.49)
    assert (obs[-1].age_bp, obs[-1].value, obs[-1].lower, obs[-1].upper) == (-51.03, 368.02, 367.96, 368.08)
    assert {o.interval for o in obs} == {"1sigma"}
    assert all(a.age_bp > b.age_bp for a, b in itertools.pairwise(obs))  # type: ignore[operator]
    assert r.changes is None


def test_bereiter_maximum_before_1000_years_bp():
    r = run_transform(MAXIMUM, ("bereiter-2015-co2", "composite"))
    (o,) = r.observations
    # File row "335102.31\t298.60\t3.00": the research note's awk scan found the same maximum.
    assert (o.age_bp, o.value, o.lower, o.upper, o.interval) == (335102.31, 298.6, 295.6, 301.6, "1sigma")
    assert "1,679 samples" in r.steps[1] and "298.60 ppm at 335102.31" in r.steps[1]
    assert r.changes  # a selection, so the modified credit line applies


def test_bereiter_maximum_refuses_a_tie_and_needs_old_samples():
    path, _ = fixture("bereiter-2015-co2", "composite")
    samples = read_composite(path.read_text())
    top, _ = preindustrial_max(samples)
    twin = Sample(top.age_bp + 1, top.co2_ppm, top.sigma_ppm)
    with pytest.raises(BereiterFormatError, match="share the maximum"):
        preindustrial_max([*samples, twin])
    with pytest.raises(BereiterFormatError, match="no sample older"):
        preindustrial_max([s for s in samples if s.age_bp < 1000])


def test_bereiter_reader_refuses_a_changed_age_unit():
    path, _ = fixture("bereiter-2015-co2", "composite")
    raw = path.read_text().replace("Time_Unit: cal yr BP", "Time_Unit: yr b2k")
    with pytest.raises(BereiterFormatError, match="re-read"):
        read_composite(raw)


def test_bereiter_builds_and_exports_with_age_bp(tmp_paths, tmp_path):
    """Through the real build: the contract carries the ages, the CSV has age_bp, validate passes."""
    import shutil

    from envdash.export import build_and_export
    from envdash.registry import load_registry
    from envdash.validate import validate_all

    from support import REPO_ROOT, load_fixture_snapshot

    shutil.copy(REPO_ROOT / "pipeline" / "sources" / "bereiter-2015-co2.yaml", tmp_paths.sources)
    load_fixture_snapshot(tmp_paths, "bereiter-2015-co2", "composite")
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id in (SERIES, MAXIMUM)]
    report = build_and_export(tmp_paths, reg, ts)
    assert report.ok, [(o.id, o.reason) for o in report.failed]
    ind = json.loads((tmp_paths.public_indicators / f"{SERIES}.json").read_text())
    assert ind["time_basis"] == "years-before-1950"
    assert ind["latest"] == {
        "age_bp": -51.03,
        "dims": {},
        "entity": "ANT_ICECORES",
        "period": None,
        "status": "final",
        "value": 368.02,
    }
    mx = json.loads((tmp_paths.public_indicators / f"{MAXIMUM}.json").read_text())
    assert (mx["latest"]["age_bp"], mx["latest"]["value"]) == (335102.31, 298.6)
    assert mx["attribution"].startswith("Calculated by Environment Dashboard from Bereiter et al. (2015)")
    csv = (tmp_paths.public_indicators / f"{SERIES}.csv").read_text().splitlines()
    assert "# Provenance and processing: https://environmentdashboard.org/data/co2/bereiter-2015/800k" in csv
    header = csv.index("indicator_id,entity,period,value,lower,upper,interval,status,note,missing_reason,age_bp")
    assert csv[header + 1] == "co2.bereiter-2015.800k,ANT_ICECORES,,207.29,205.09,209.49,1sigma,final,,,805668.87"
    catalog = json.loads((tmp_paths.data / "v1" / "catalog.json").read_text())
    assert {e["id"]: e["time_basis"] for e in catalog["indicators"]} == {
        SERIES: "years-before-1950",
        MAXIMUM: "years-before-1950",
    }
    assert validate_all(tmp_paths, reg) == []

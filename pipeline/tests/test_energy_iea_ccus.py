"""IEA CCUS Projects Database: capture capacity and projects, counted as the IEA's explorer counts them
(envdash/transforms/energy/iea_ccus.py).

The fixture is the whole explorer data file of 26 March 2026 (81,098 bytes).
"""

from __future__ import annotations

import json

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.energy import iea_ccus as ccus

from support import fixture


def _file() -> InputFile:
    path, meta = fixture(ccus.SOURCE, ccus.PROJECTS.artifact_id)
    snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
    assert snap is not None
    return InputFile(path, snap)


def _run(i: int):
    t = ccus.transforms(Paths.default())[i]
    result = t.run({ccus.PROJECTS.key: _file()})
    validate(t, result.observations)
    return t, result


def test_operating_capacity_by_sector():
    t, result = _run(0)
    assert t.spec.id == ccus.OPERATING
    by = {o.dims["sector"]: o.value for o in result.observations}
    # Operational capture, full chain and CCU projects with capacity above zero: 67 projects.
    assert by["all"] == 62.534
    assert by["dac"] == 0.021
    assert by["natural-gas-processing"] == 37.603
    assert "chemicals" not in by  # no operating project in this sector in this file
    assert {o.period for o in result.observations} == {"2026-03-26"}
    assert result.vintage == "CCUS Projects Database, file of 2026-03-26"


def test_status_chart_is_cumulative_by_start_year():
    t, result = _run(1)
    assert t.spec.id == ccus.BY_STATUS
    by = {(o.dims["status"], o.period): o for o in result.observations}
    assert by[("operational", "2026")].value == 62.534 and by[("operational", "2026")].status == "final"
    assert by[("under-construction", "2026")].value == 15.843
    assert by[("under-construction", "2030")].value == 52.054
    assert by[("planned", "2030")].value == 262.342
    assert by[("planned", "2035")].value == 310.871 and by[("planned", "2035")].status == "projection"


def test_project_counts_follow_the_same_rule():
    _, result = _run(2)
    by = {(o.dims["status"], o.period): o.value for o in result.observations}
    assert by[("operational", "2026")] == 67
    assert by[("under-construction", "2035")] == 44
    # 198 planned capture projects start by 2035; two more (2040 and 2050) are in no column, as in the explorer.
    assert by[("planned", "2035")] == 198


def test_transport_and_storage_are_not_capture():
    projects = ccus.read_projects(_file().path.read_bytes())
    storage = [p for p in projects if p.project_type in ("T&S", "Storage")]
    assert storage and all(p.sector == "CO2 T&S" for p in storage)
    obs = ccus.operating_by_sector(projects, "2026-03-26")
    assert "CO2 T&S" not in {o.dims["sector"] for o in obs}


def test_an_unknown_project_type_stops_the_build():
    doc = json.loads(_file().path.read_bytes())
    doc[0]["projectType"] = "Industrial hub"
    with pytest.raises(ccus.IeaCcusFormatError, match="Industrial hub"):
        ccus.read_projects(json.dumps(doc).encode())


def test_the_version_is_the_files_last_modified_date():
    assert ccus.vintage_of("Thu, 26 Mar 2026 10:35:32 GMT") == "2026-03-26"
    with pytest.raises(ccus.IeaCcusFormatError, match="Last-Modified"):
        ccus.vintage_of(None)

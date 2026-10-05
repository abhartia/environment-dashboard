"""EFFIS burnt area for the EU27 and UCPM (envdash/transforms/impacts/effis_burned_area.py).

Fixtures are the three whole EFFIS responses of 5 October 2026 (estimates-eu 872 bytes, estimates-ucpm 879 bytes,
areas-of-interest 7,071 bytes; CC BY 4.0). Expected values are those files' own numbers; the EU27 2025 total of
1,034,552 ha is also the sum of the EU countries in EFFIS's 2025 overview (registry comment of 4 October 2026).
"""

from __future__ import annotations

import json
import shutil
from datetime import date

import pytest

from envdash import geo
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.impacts import effis_burned_area as effis

from support import fixture, load_fixture_snapshot

ID = "burned-area.effis.europe-annual"


def _bytes(artifact: str) -> bytes:
    return fixture("effis", artifact)[0].read_bytes()


def _paths(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / "effis.yaml", tmp_paths.sources / "effis.yaml")
    for artifact in ("estimates-eu", "estimates-ucpm", "areas-of-interest"):
        load_fixture_snapshot(tmp_paths, "effis", artifact)
    return tmp_paths


def test_transform_reads_registered_artifacts():
    src = load_registry(Paths.default()).sources["effis"]
    (t,) = effis.transforms(Paths.default())
    assert {i.artifact_id for i in t.inputs} <= {a.id for a in src.artifacts}
    assert src.licence_class == "open"


def test_membership_is_effis_own_list():
    areas = effis.parse_areas(_bytes("areas-of-interest"))
    assert areas["EU"] == geo.EU27_MEMBERS
    assert len(areas["UCPM"]) == 43 and areas["UCPM"] == effis.UCPM_MEMBERS
    assert areas["UCPM"] > geo.EU27_MEMBERS
    assert not {"CHE", "GBR", "AND", "XKO"} & areas["UCPM"]
    effis.check_membership(areas)


def test_changed_membership_stops_the_build():
    rows = json.loads(_bytes("areas-of-interest"))
    rows = [r for r in rows if not (r["aoi_code"] == "UCPM" and r["iso3"] == "ISL")]
    with pytest.raises(effis.EffisFormatError, match=r"membership of UCPM: added \[\], removed \['ISL'\]"):
        effis.check_membership(effis.parse_areas(json.dumps(rows).encode()))


def test_estimates_and_year_to_date():
    accessed = date(2026, 10, 5)
    eu = effis.parse_estimates(_bytes("estimates-eu"), accessed, "estimates-eu")
    assert (eu[0].year, eu[0].ba) == (2006, 207205)
    assert {r.year: r.ba for r in eu}[2025] == 1_034_552
    assert eu[-1].year == 2026
    obs = effis.observations("EU27", eu, accessed)
    assert all(o.status == "final" and o.note is None for o in obs[:-1])
    assert obs[-1].status == "preliminary" and "Year to date" in obs[-1].note and "2026-10-05" in obs[-1].note
    # The same bytes read as if fetched in 2025 hold a year after the fetch date: refused, never relabelled.
    with pytest.raises(effis.EffisFormatError, match="after the fetch date"):
        effis.parse_estimates(_bytes("estimates-eu"), date(2025, 12, 31), "estimates-eu")


def test_null_burnt_area_is_refused():
    rows = json.loads(_bytes("estimates-ucpm"))
    rows[3]["ba"] = None
    with pytest.raises(effis.EffisFormatError, match="2009: ba is None"):
        effis.parse_estimates(json.dumps(rows).encode(), date(2026, 10, 5), "estimates-ucpm")


def test_built_from_fixtures(tmp_paths):
    paths = _paths(tmp_paths)
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id == ID]
    out = build_and_export(paths, reg, ts).outcomes[0]
    assert out.state == "built", out.reason
    ind = out.indicator
    assert ind.licence_class == "open"
    by = {(o.entity, o.period): o for o in ind.observations}
    assert by[("EU27", "2025")].value == 1_034_552 and by[("EU27", "2025")].status == "final"
    assert by[("UCPM", "2025")].value == 1_976_699
    assert by[("EU27", "2026")].status == by[("UCPM", "2026")].status == "preliminary"
    assert ind.latest.entity == "EU27" and ind.latest.period == "2026" and ind.latest.status == "preliminary"
    assert {o.entity for o in ind.observations} == {"EU27", "UCPM"}
    assert all(by[("UCPM", p)].value >= by[("EU27", p)].value for (e, p) in by if e == "EU27")
    assert "Iceland" in ind.scope.geography and "Switzerland" in ind.scope.geography
